"""
Server noi dung giao thuc xiaozhi, de ESP32 goi vao thay cho api.tenclass.net.

Mot luot tron ven: thiet bi gui Opus -> VAD thay nguoi noi dut cau -> STT ->
LLM -> TTS -> ma hoa Opus -> gui nguoc xuong loa.

Cam xuc di TRUOC tieng noi. `pipeline.run_turn_stream` goi `on_emotion` ngay
khi bat duoc tag o dau cau LLM (do duoc ~477ms, som hon tieng noi nua giay),
server day luon `{"type":"llm","emotion":...}` xuong de mat OLED doi ngay.
Khong cai nay thi robot dung im vai giay roi moi phan ung — bi che la "giat
lag" du tong do tre y het.

Hai endpoint tren cung mot cong:
    POST/GET /xiaozhi/ota/   firmware hoi khi khoi dong -> tra ve dia chi WebSocket
    GET      /xiaozhi/firmware/xiaozhi.bin  tai firmware de nang cap qua WiFi
    GET      /xiaozhi/v1/    WebSocket: hello, listen, audio Opus

Giao thuc doc tu firmware (xiaozhi-esp32/main):
  - ota.cc:151-190      chi tra "websocket" (khong "mqtt") thi firmware dung WebSocket.
                        Khong tra "activation" thi firmware bo qua buoc kich hoat.
  - protocols/websocket_protocol.cc
                        header Authorization / Protocol-Version / Device-Id / Client-Id,
                        hello -> doi server hello toi da 10 giay, Protocol-Version 1 thi
                        goi binary la Opus tho, 16 kHz mono, khung 60 ms.
  - protocols/protocol.cc  listen start/stop/detect, abort.

    python server/xiaozhi_server.py                    # thu tren may ca nhan, chi 127.0.0.1
    python server/xiaozhi_server.py --host 0.0.0.0     # tren VPS, de ESP32 goi vao

Chay that tren may chu tu xa (VPS/Oracle). KHONG mo cong hay dung tunnel tren
may cong ty — do la di vong tuong lua cua ho.
"""

import argparse
import asyncio
import contextlib
import hmac
import json
import logging
import os
import struct
import time
import uuid

import numpy as np
from aiohttp import WSMsgType, web

from dotenv import load_dotenv

import audio
import pipeline

log = logging.getLogger("xz")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "out", "ws_sessions")

# Firmware cong offset (phut) vao timestamp roi dat lam gio he thong.
TIMEZONE_OFFSET_MIN = 7 * 60


def _public_base(request: web.Request) -> str:
    """Dia chi cong khai ma ESP32 dung de goi lai.

    Dat sau reverse proxy co TLS (Caddy, nginx...) thi Host la ten mien cong khai
    va X-Forwarded-Proto la https — tu suy ra duoc. Dat PUBLIC_BASE_URL neu proxy
    khong chuyen tiep hai header do.
    """
    env = os.environ.get("PUBLIC_BASE_URL", "").strip()
    if env:
        return env.rstrip("/")
    proto = request.headers.get("X-Forwarded-Proto", request.scheme)
    return f"{proto}://{request.host}"


# ---- Nang cap qua WiFi (OTA) --------------------------------------------
#
# Firmware hoi POST /xiaozhi/ota/ kem phien ban dang chay. Tra ve khoa
# "firmware" co version MOI HON thi no tu tai .bin ve, ghi sang phan vung app
# con trong roi khoi dong lai (main/ota.cc). Khong tra khoa do thi khong bao
# gio nang cap — truoc 11/10/2026 server co tinh bo di.
#
# CHI chay duoc tren board 16MB: bang phan vung partitions/v2/16m.csv co hai
# khe ota_0/ota_1. Board ESP32 4MB cu chi co mot phan vung factory, va hai khe
# cung khong nhet vua 4MB — OTA tren no la bat kha thi.
FIRMWARE_PATH = os.environ.get("FIRMWARE_PATH", "firmware/xiaozhi.bin")

# Ma chip trong esp_image_header_t. Nap nham ban ESP32 vao S3 thi bootloader
# tu tu choi, nhung chan ngay o day thi khoi ton 2.5MB bang thong moi lan.
CHIP_IDS = {0x0000: "esp32", 0x0002: "esp32s2", 0x0005: "esp32c3",
            0x0009: "esp32s3", 0x000D: "esp32c6", 0x0010: "esp32p4"}


def _doc_mo_ta_app(path: str) -> tuple:
    """(phien ban, ten chip) doc tu chinh file .bin, hoac (None, None).

    Phien ban nam san trong esp_app_desc_t nen khong can tep phu ghi kem —
    hai noi la co ngay hai so lech nhau. Bo cuc: esp_image_header_t 24 byte
    (chip_id o offset 12), segment header 8 byte, roi esp_app_desc_t o offset
    32 voi magic 0xABCD5432 va version[32] o offset 16 cua no.
    """
    try:
        with open(path, "rb") as f:
            d = f.read(144)
    except OSError:
        return None, None
    if len(d) < 144:
        return None, None
    if struct.unpack("<I", d[32:36])[0] != 0xABCD5432:
        log.warning("OTA: %s khong phai anh ung dung ESP (thieu magic)", path)
        return None, None
    chip = CHIP_IDS.get(struct.unpack("<H", d[12:14])[0])
    ver = d[48:80].split(b"\x00")[0].decode("utf-8", "replace").strip()
    return (ver or None), chip


async def handle_firmware(request: web.Request) -> web.StreamResponse:
    if not os.path.isfile(FIRMWARE_PATH):
        raise web.HTTPNotFound(text="khong co firmware")
    log.info("OTA: thiet bi dang tai firmware (%d byte)", os.path.getsize(FIRMWARE_PATH))
    return web.FileResponse(FIRMWARE_PATH,
                            headers={"Content-Type": "application/octet-stream"})


async def handle_ota(request: web.Request) -> web.Response:
    body = await request.text()
    try:
        info = json.loads(body) if body else {}
    except ValueError:
        info = {}
    app = info.get("application") or {}

    base = _public_base(request)
    ws_url = base.replace("https://", "wss://", 1).replace("http://", "ws://", 1) + "/xiaozhi/v1/"

    # Khong co "mqtt", khong co "activation": firmware dung WebSocket va bo qua
    # buoc kich hoat.
    ra = {
        "server_time": {"timestamp": int(time.time() * 1000),
                        "timezone_offset": TIMEZONE_OFFSET_MIN},
        "websocket": {"url": ws_url, "token": os.environ.get("XZ_TOKEN", "")},
    }

    ver, chip = _doc_mo_ta_app(FIRMWARE_PATH)
    ghi_chu = ""
    if ver:
        ra["firmware"] = {"version": ver, "url": base + "/xiaozhi/firmware/xiaozhi.bin"}
        ghi_chu = " | co ban %s (%s)" % (ver, chip or "chip la")
    log.info("OTA %s | Device-Id=%s | dang chay=%s%s",
             request.method, request.headers.get("Device-Id"), app.get("version"), ghi_chu)

    return web.json_response(ra)


DUMP_OPUS = os.environ.get("XZ_DUMP_OPUS", "").strip() not in ("", "0", "false")

# dB cong vao tieng TTS truoc khi ma hoa (audio.boost). 12 dB chi an toan NHO
# co TTS_HPF_HZ cat trầm ben duoi — bo cat di ma giu 12 thi dinh cham tran, re
# ngay. Xem bang do trong boost() o audio.py.
GAIN_DB = float(os.environ.get("TTS_GAIN_DB", "12"))
# Cat tieng TTS duoi tan so nay TRUOC khi tang gain. Loa nho gan nhu khong phat
# duoc phan tram, no chi chiem cho tran. Do 07/10/2026 sau Opus, trong dai >300 Hz
# (loa nghe duoc): +6 dB khong cat -28,0 dBFS; cat 300 Hz + 12 dB -24,2 dBFS
# (to hon 3,8 dB), 1 mau cham 0.99 trong 5,8 s. 0 = khong cat.
TTS_HPF_HZ = float(os.environ.get("TTS_HPF_HZ", "300"))

# Che do goi ten. Luon nghe ma tra loi MOI cau thi o van phong no tra loi ca
# nguoi khac (log 08/10: phan lon 20 luot la nguoi khac noi chuyen). Gio phai
# co ten robot (pipeline.ROBOT_NAME) trong cau, tru khi robot vua noi xong chua qua WAKE_WINDOW_S giay —
# de hoi tiep khong phai goi ten lai. WAKE_REQUIRED=0 de tat.
WAKE_REQUIRED = os.environ.get("WAKE_REQUIRED", "1").strip() not in ("0", "false", "")
WAKE_WINDOW_S = float(os.environ.get("WAKE_WINDOW_S", "20"))

# Dang di, giong ba nut cua test/servo_test/servo_dash.py. Gui kem moi lenh
# dong tac nen chinh o fly.toml roi deploy la xong, khong phai nap lai firmware.
#   OTTO_PERIOD  chu ky walk/turn (ms)   1000 = goc Otto, 1800 = "nhip em"
#   OTTO_AMP     bien do (%)             100 = goc Otto, 70 = "nhip em"
#   OTTO_LIFT    lech tam co chan (do)   5 ~ 5mm, 10 ~ 9.6mm, 15 ~ 13mm nhac chan
GAIT = {"period": int(os.environ.get("OTTO_PERIOD", "1000")),
        "amp": int(os.environ.get("OTTO_AMP", "100")),
        "lift": int(os.environ.get("OTTO_LIFT", "5"))}


class Session:
    """Mot ket noi WebSocket: gom audio nguoi noi, chay pipeline, phat tra loi."""

    def __init__(self, device_id: str, ws: web.WebSocketResponse):
        self.id = str(uuid.uuid4())
        self.device_id = device_id
        self.ws = ws
        self.mode = "auto"
        self.listen_started = None
        self.frames = 0
        self.bytes = 0
        self.dump = None

        self.dec = audio.OpusDecoder()
        self.hpf = audio.HighPass()   # bo u tram duoi 120 Hz TRUOC VAD va STT
        self.det = audio.SpeechDetector()
        self.pcm = []                 # cac manh PCM cua luot dang nghe
        self.collecting = False
        self.history = []             # ngu canh hoi thoai, giu trong ket noi
        self.task = None              # tac vu tra loi dang chay
        self.turn = 0
        self.cleanup = []             # tep tam cua luot dang chay
        self.mcp_id = 0               # id JSON-RPC cho lenh MCP gui xuong
        self.last_spoke = 0.0         # monotonic luc robot noi xong cau gan nhat

    def accepts(self, transcript: str) -> bool:
        """Co tra loi cau nay khong (che do goi ten)."""
        if not WAKE_REQUIRED:
            return True
        if time.monotonic() - self.last_spoke < WAKE_WINDOW_S:
            return True
        return pipeline.is_addressed(transcript)

    # ---------------------------------------------------------- nghe
    def start_listen(self, mode: str):
        self.stop_listen()
        self.mode = mode or "auto"
        self.listen_started = time.monotonic()
        self.frames = 0
        self.bytes = 0
        self.pcm = []
        self.det.reset()
        self.collecting = True
        if DUMP_OPUS:
            os.makedirs(OUT_DIR, exist_ok=True)
            path = os.path.join(OUT_DIR, time.strftime("%H%M%S") + f"_{mode}.opuspkt")
            # Moi goi: 2 byte do dai (little-endian) + payload Opus.
            self.dump = open(path, "wb")
        log.info("  listen START mode=%s", mode)

    def on_audio(self, payload: bytes) -> bool:
        """True = nguoi noi vua dut cau, den luot server tra loi."""
        self.frames += 1
        self.bytes += len(payload)
        if self.dump:
            self.dump.write(struct.pack("<H", len(payload)) + payload)
        if not self.collecting:
            return False
        pcm = self.dec.decode(payload)
        if not len(pcm):
            return False
        pcm = self.hpf.process(pcm)
        self.pcm.append(pcm)
        # Che do manual: nguoi dung nha nut moi dung, khong tu doan.
        if self.mode == "manual":
            return False
        return self.det.feed(pcm)

    def take_pcm(self):
        pcm = np.concatenate(self.pcm) if self.pcm else np.zeros(0, np.int16)
        self.pcm = []
        self.collecting = False
        return pcm

    def stop_listen(self, reason: str = ""):
        self.collecting = False
        if self.dump is not None:
            self.dump.close()
            self.dump = None
        if self.listen_started is None:
            return
        secs = time.monotonic() - self.listen_started
        self.listen_started = None
        # Khung 60 ms: so goi x 0.06 phai xap xi thoi gian thuc. Lech nhieu
        # nghia la rot goi hoac khung khac 60 ms.
        log.info("  listen STOP%s: %d goi, %d byte, %.1f s thuc te, %.1f s theo so goi x 60ms",
                 f" ({reason})" if reason else "", self.frames, self.bytes, secs, self.frames * 0.06)
        # In luon so lieu VAD. Khong co dong nay thi khong biet nguong co hop
        # voi mic khong — da tung mat cong doan mo: moi luot deu dung 15.0s
        # vi cham tran max_ms, ma log cu chi noi "VAD thay dut cau".
        log.info("  VAD: %s", self.det.stats())

    async def abort(self, reason: str = ""):
        """Nguoi dung cat loi: huy tac vu tra loi dang chay."""
        t = self.task
        if t and not t.done():
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await t
            log.info("  da huy luot tra loi (%s)", reason)
        self.task = None


async def respond(sess: Session, pcm: np.ndarray = None, text: str = None):
    """Mot luot tra loi tron ven. Chay trong task rieng de abort cat duoc.

    `text` thay cho `pcm` thi bo qua STT va coi nhu nguoi dung vua noi cau do —
    dung cho /xiaozhi/say, go chu tu may tinh thay vi phai noi.
    """
    ws = sess.ws
    sess.turn += 1
    t0 = time.monotonic()
    src = None

    if text is None:
        secs = len(pcm) / audio.SAMPLE_RATE
        log.info("  -> nghe duoc %.1f s tieng, bat dau xu ly", secs)
        os.makedirs(OUT_DIR, exist_ok=True)
        stem = os.path.join(OUT_DIR, f"{time.strftime('%H%M%S')}_turn{sess.turn}")
        # Ogg chu khong phai WAV: 8 KB thay vi 118 KB, STT tu 1324 xuong 377 ms.
        src = audio.write_ogg(pcm, stem + ".ogg")
        # Che do luon nghe tao mot tep moi luot, ke ca luot chi co tieng on.
        # Khong xoa thi o dia server day dan.
        if not DUMP_OPUS:
            sess.cleanup.append(src)
        if DUMP_OPUS:
            audio.write_wav(pcm, stem + ".wav")     # de nghe lai khi soi loi
    else:
        log.info("  -> go tu may tinh: %r", text)

    turn = pipeline.Turn()
    enc = audio.OpusEncoder(rate=audio.OUT_RATE)
    hpf = audio.HighPass(fc=TTS_HPF_HZ, sr=audio.OUT_RATE) if TTS_HPF_HZ > 0 else None
    pacer = audio.Pacer()
    started = False
    carry = b""          # byte le con du giua hai chunk HTTP

    async def on_emotion(name):
        # Day cam xuc xuong TRUOC khi co tieng. Day la ca ly do ham nay ton tai.
        await ws.send_json({"type": "llm", "text": "", "emotion": name})
        log.info("  >> llm emotion=%s  (%.0f ms)", name, (time.monotonic()-t0)*1000)

    async def on_action(name, steps=0):
        # MCP JSON-RPC thang toi tool cua firmware; khong can initialize truoc
        # (mcp_server.cc chi doi jsonrpc 2.0 + id so). Thiet bi tra loi bang
        # mot tin "mcp" — vong lap handle_ws ghi log.
        action, direction = pipeline.ACTIONS[name]
        sess.mcp_id += 1
        await ws.send_json({"session_id": sess.id, "type": "mcp", "payload": {
            "jsonrpc": "2.0", "id": sess.mcp_id, "method": "tools/call",
            "params": {"name": "self.otto.action",
                       "arguments": {"action": action, "direction": direction,
                                     "steps": steps, **GAIT}}}})
        log.info("  >> dong tac %s -> self.otto.action(%s, %d, steps=%d)  (%.0f ms)",
                 name, action, direction, steps, (time.monotonic()-t0)*1000)

    async def send_pkts(pkts):
        for p in pkts:
            await pacer.wait()
            await ws.send_bytes(p)

    try:
        gen = pipeline.run_turn_stream(turn, audio_path=src, text=text,
                                       history=sess.history,
                                       on_emotion=on_emotion, pcm=True,
                                       pcm_rate=audio.OUT_RATE, on_action=on_action,
                                       accept=sess.accepts)
        async with contextlib.aclosing(gen):
            async for chunk in gen:
                if not started:
                    started = True
                    await ws.send_json({"type": "stt", "text": turn.transcript})
                    await ws.send_json({"type": "tts", "state": "start"})
                    await ws.send_json({"type": "tts", "state": "sentence_start",
                                        "text": turn.reply})
                    log.info("  >> stt=%r", turn.transcript)
                    log.info("  >> tra loi [%s] %r", turn.emotion, turn.reply)
                # TTS tra PCM 24 kHz (pcm=True) -> ma hoa thang sang Opus.
                #
                # Chunk HTTP KHONG dam bao chan byte: mot mau int16 co the bi
                # cat doi giua hai chunk. Gap that — 3/5 luot chet voi
                # "buffer size must be a multiple of element size". Giu lai
                # byte le de ghep vao dau chunk sau.
                buf = carry + chunk
                if len(buf) % 2:
                    carry, buf = buf[-1:], buf[:-1]
                else:
                    carry = b""
                if not buf:
                    continue
                samples = np.frombuffer(buf, dtype=np.int16)
                if hpf:
                    samples = hpf.process(samples)
                samples = audio.boost(samples, GAIN_DB)
                await send_pkts(enc.encode(samples))
            await send_pkts(enc.flush())
    except pipeline.NoSpeech as e:
        # Tieng on hoac Whisper bia. Chua gui gi xuong nen thiet bi van dang o
        # trang thai nghe va se KHONG gui listen start lan nua -> server tu nghe tiep.
        log.info("  bo qua: khong phai cau noi (%r)", str(e)[:60])
        sess.start_listen(sess.mode)
        return
    except asyncio.CancelledError:
        with contextlib.suppress(Exception):
            await ws.send_json({"type": "tts", "state": "stop"})
        raise
    except Exception as e:
        log.error("  loi khi tra loi: %s: %s", type(e).__name__, e)
        with contextlib.suppress(Exception):
            if started:
                await ws.send_json({"type": "tts", "state": "stop"})
            else:
                sess.start_listen(sess.mode)
        return
    finally:
        for f in sess.cleanup:
            with contextlib.suppress(OSError):
                os.remove(f)
        sess.cleanup.clear()

    await ws.send_json({"type": "tts", "state": "stop"})
    sess.last_spoke = time.monotonic()
    sess.history = turn.history[-12:]      # giu 6 luot gan nhat
    log.info("  luot xong: STT %d | LLM %d | TTS %d ms | tieng dau %d ms | tong %.0f ms",
             turn.ms_stt, turn.ms_llm, turn.ms_tts, turn.ms_first_audio,
             (time.monotonic()-t0)*1000)


# ---- Dieu khien tu may tinh, khong phai noi ------------------------------
#
# Go chu nhanh hon noi, va khi thu dang di / dieu nhay thi phai lap lai cung
# mot cau hang chuc lan. Hai endpoint duoi cho phep lam viec do tu terminal:
#
#   POST /xiaozhi/say  {"text": "nhảy đi"}   -> y het nhu vua noi cau do:
#                                               LLM -> cam xuc + dong tac + TTS
#   POST /xiaozhi/do   {"action": "dance"}   -> ban thang dong tac xuong chan,
#                                               khong qua LLM, khong ton TTS
#
# Cai thu hai dang de thu chan nhat: khong ton luot goi Groq (gioi han 20
# STT/phut cua ban mien phi rat de cham khi thu di thu lai).
# Mat khau cho hai endpoint nay. Dat bang `fly secrets set XZ_CTRL_TOKEN=...`
# chu KHONG ghi vao fly.toml — tep do nam trong git.
#
# Khong dat bien nay thi hai endpoint DONG han, khong phai mo toang. Server
# chay cong khai tren Internet, nen mac dinh an toan phai la tu choi: quen
# dat secret ma cua van mo thi khong ai phat hien ra cho den luc muon.
CTRL_TOKEN = os.environ.get("XZ_CTRL_TOKEN", "")


def _kiem_mat_khau(request: web.Request):
    """Doi header `Authorization: Bearer <mat khau>`.

    De trong header chu khong phai trong URL hay than JSON: URL hay bi ghi lai
    trong log cua proxy, con than JSON thi minh dang ghi log noi dung cau noi.
    So bang compare_digest de do dai thoi gian so sanh khong tiet lo gi.
    """
    if not CTRL_TOKEN:
        raise web.HTTPServiceUnavailable(
            text="chua dat XZ_CTRL_TOKEN tren server nen dieu khien tu xa bi khoa")
    h = request.headers.get("Authorization", "")
    gui = h[7:] if h.startswith("Bearer ") else ""
    if not hmac.compare_digest(gui, CTRL_TOKEN):
        log.warning("  tu choi dieu khien tu xa: sai mat khau (tu %s)",
                    request.headers.get("X-Forwarded-For") or request.remote)
        raise web.HTTPUnauthorized(text="sai mat khau")


SESSIONS = {}          # device_id -> Session dang ket noi


def _chon_phien(device: str = None):
    if device:
        s = SESSIONS.get(device)
        if s is None:
            raise web.HTTPNotFound(text="khong thay thiet bi %r" % device)
        return s
    if not SESSIONS:
        raise web.HTTPServiceUnavailable(text="chua co robot nao ket noi")
    if len(SESSIONS) > 1:
        raise web.HTTPConflict(
            text="co %d thiet bi, phai ghi ro 'device': %s"
                 % (len(SESSIONS), ", ".join(SESSIONS)))
    return next(iter(SESSIONS.values()))


async def handle_say(request: web.Request) -> web.Response:
    _kiem_mat_khau(request)
    try:
        d = await request.json()
    except ValueError:
        raise web.HTTPBadRequest(text="can JSON {\"text\": \"...\"}")
    text = (d.get("text") or "").strip()
    if not text:
        raise web.HTTPBadRequest(text="thieu 'text'")
    sess = _chon_phien(d.get("device"))
    if sess.task is not None:
        await sess.abort("go cau moi tu may tinh")
    sess.task = asyncio.create_task(respond(sess, text=text))

    def _done(t, _s=sess):
        _s.task = None
        if not t.cancelled() and t.exception():
            log.error("  task tra loi chet: %r", t.exception())
    sess.task.add_done_callback(_done)
    return web.json_response({"ok": True, "device": sess.device_id, "text": text})


async def handle_do(request: web.Request) -> web.Response:
    """Ban thang mot dong tac xuong chan, bo qua LLM va TTS."""
    _kiem_mat_khau(request)
    try:
        d = await request.json()
    except ValueError:
        raise web.HTTPBadRequest(text="can JSON {\"action\": \"dance\"}")
    name = (d.get("action") or "").strip().lower()
    if name not in pipeline.ACTIONS:
        raise web.HTTPBadRequest(
            text="action phai la mot trong: " + ", ".join(sorted(pipeline.ACTIONS)))
    steps = int(d.get("steps") or 0)
    sess = _chon_phien(d.get("device"))
    action, direction = pipeline.ACTIONS[name]
    sess.mcp_id += 1
    await sess.ws.send_json({"session_id": sess.id, "type": "mcp", "payload": {
        "jsonrpc": "2.0", "id": sess.mcp_id, "method": "tools/call",
        "params": {"name": "self.otto.action",
                   "arguments": {"action": action, "direction": direction,
                                 "steps": min(steps, 10), **GAIT}}}})
    log.info("  >> (tu may tinh) dong tac %s -> %s dir=%+d steps=%d",
             name, action, direction, steps)
    return web.json_response({"ok": True, "device": sess.device_id, "action": name,
                              "direction": direction, "steps": steps})


async def handle_ws(request: web.Request) -> web.WebSocketResponse:
    h = request.headers
    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)

    session = Session(h.get("Device-Id", "?"), ws)
    SESSIONS[session.device_id] = session
    log.info("WS MO | Device-Id=%s | Client-Id=%s | Protocol-Version=%s | token=%s",
             h.get("Device-Id"), h.get("Client-Id"), h.get("Protocol-Version"),
             "co" if h.get("Authorization") else "khong")

    try:
        async for msg in ws:
            if msg.type == WSMsgType.BINARY:
                if session.on_audio(msg.data) and session.task is None:
                    # VAD bao nguoi noi dut cau. Chot audio roi tra loi trong
                    # task rieng de vong lap nay con nhan duoc `abort`.
                    rong = session.det.timed_out
                    session.stop_listen("het gio, khong co tieng noi" if rong
                                        else "VAD thay dut cau")
                    pcm = session.take_pcm()
                    if rong:
                        # Cham tran thoi gian ma chua he nghe thay tieng noi.
                        # Gui len STT thi Whisper bia ra cau ("Hay subscribe
                        # cho kenh..."), ton mot vong goi API va mot lan ghi
                        # dia. Nghe lai tu dau luon.
                        session.start_listen(session.mode)
                        continue
                    session.task = asyncio.create_task(respond(session, pcm))

                    def _done(t, _s=session):
                        _s.task = None
                        if not t.cancelled() and t.exception():
                            log.error("  task tra loi chet: %r", t.exception())
                    session.task.add_done_callback(_done)
                continue
            if msg.type != WSMsgType.TEXT:
                continue

            try:
                data = json.loads(msg.data)
            except ValueError:
                log.warning("  JSON hong: %r", msg.data[:120])
                continue
            kind = data.get("type")

            if kind == "hello":
                log.info("  << hello %s", json.dumps(data, ensure_ascii=False))
                reply = {
                    "type": "hello",
                    "transport": "websocket",
                    "session_id": session.id,
                    # Tan so tieng server GUI XUONG; firmware mo decoder theo so nay.
                    "audio_params": {"format": "opus", "sample_rate": audio.OUT_RATE,
                                     "channels": 1, "frame_duration": 60},
                }
                await ws.send_json(reply)
                log.info("  >> hello session_id=%s", session.id)
            elif kind == "listen":
                state = data.get("state")
                if state == "start":
                    session.start_listen(data.get("mode", "?"))
                elif state == "stop":
                    session.stop_listen("thiet bi bao stop")
                    pcm = session.take_pcm()
                    if len(pcm) and session.task is None:
                        session.task = asyncio.create_task(respond(session, pcm))

                        def _done(t, _s=session):
                            _s.task = None
                            if not t.cancelled() and t.exception():
                                log.error("  task tra loi chet: %r", t.exception())
                        session.task.add_done_callback(_done)
                else:
                    log.info("  << listen %s", json.dumps(data, ensure_ascii=False))
            elif kind == "abort":
                log.info("  << abort %s", data.get("reason", ""))
                await session.abort(data.get("reason", ""))
            else:
                log.info("  << %s", json.dumps(data, ensure_ascii=False)[:200])
    finally:
        session.stop_listen("mat ket noi")
        await session.abort("mat ket noi")
        # Chi go neu con tro toi CHINH phien nay: thiet bi noi lai truoc khi
        # phien cu kip dong thi phien moi da ghi de, go bua la mat phien song.
        if SESSIONS.get(session.device_id) is session:
            del SESSIONS[session.device_id]
        log.info("WS DONG | Device-Id=%s", session.device_id)
    return ws


def make_app() -> web.Application:
    app = web.Application()
    app.router.add_route("*", "/xiaozhi/ota/", handle_ota)
    app.router.add_get("/xiaozhi/firmware/xiaozhi.bin", handle_firmware)
    app.router.add_post("/xiaozhi/say", handle_say)
    app.router.add_post("/xiaozhi/do", handle_do)
    app.router.add_get("/xiaozhi/v1/", handle_ws)
    return app


def main():
    load_dotenv(os.path.join(HERE, ".env"))
    p = argparse.ArgumentParser(description="Server giao thuc xiaozhi")
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    p.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"),
                   help="127.0.0.1 khi thu tren may ca nhan hoac sau reverse proxy; "
                        "0.0.0.0 tren VPS de ESP32 goi thang vao")
    args = p.parse_args()

    os.makedirs(os.path.dirname(OUT_DIR), exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(message)s", datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(),
                  logging.FileHandler(os.path.join(HERE, "out", "xiaozhi_server.log"),
                                      encoding="utf-8")],
    )
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
    log.info("Server nghe tai http://%s:%d", args.host, args.port)
    log.info("TTS=%s  LLM=%s  giong=%s",
             os.environ.get("TTS_PROVIDER", "xai"),
             os.environ.get("LLM_MODEL", "qwen/qwen3.8-27b"),
             os.environ.get("XAI_TTS_VOICE", "eve"))
    web.run_app(make_app(), host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
