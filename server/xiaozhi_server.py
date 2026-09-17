"""
Server noi dung giao thuc xiaozhi, de ESP32 goi vao thay cho api.tenclass.net.

MOC 0: chi bat tay va ghi log. Chua noi AI. Muc dich la chung minh ESP32 ket
noi duoc, va thu lai goi Opus that de lam buoc giai ma sau nay.

Hai endpoint tren cung mot cong:
    POST/GET /xiaozhi/ota/   firmware hoi khi khoi dong -> tra ve dia chi WebSocket
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
import json
import logging
import os
import struct
import time
import uuid

from aiohttp import WSMsgType, web

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


async def handle_ota(request: web.Request) -> web.Response:
    body = await request.text()
    try:
        info = json.loads(body) if body else {}
    except ValueError:
        info = {}
    app = info.get("application") or {}

    base = _public_base(request)
    ws_url = base.replace("https://", "wss://", 1).replace("http://", "ws://", 1) + "/xiaozhi/v1/"
    log.info("OTA %s | Device-Id=%s | firmware=%s | tra ve ws=%s",
             request.method, request.headers.get("Device-Id"), app.get("version"), ws_url)

    return web.json_response({
        "server_time": {"timestamp": int(time.time() * 1000),
                        "timezone_offset": TIMEZONE_OFFSET_MIN},
        # Khong co "mqtt", khong co "activation", khong co "firmware":
        # firmware se dung WebSocket, bo qua kich hoat, khong doi nang cap.
        "websocket": {"url": ws_url, "token": os.environ.get("XZ_TOKEN", "")},
    })


class Session:
    """Mot ket noi WebSocket. Dem goi Opus va luu lai theo tung luot nghe."""

    def __init__(self, device_id: str):
        self.id = str(uuid.uuid4())
        self.device_id = device_id
        self.listen_started = None
        self.frames = 0
        self.bytes = 0
        self.dump = None

    def start_listen(self, mode: str):
        self.stop_listen()
        self.listen_started = time.monotonic()
        self.frames = 0
        self.bytes = 0
        os.makedirs(OUT_DIR, exist_ok=True)
        path = os.path.join(OUT_DIR, time.strftime("%H%M%S") + f"_{mode}.opuspkt")
        # Moi goi: 2 byte do dai (little-endian) + payload Opus. De buoc sau doc
        # lai tung goi ma giai ma, khong phai doan ranh gioi goi.
        self.dump = open(path, "wb")
        log.info("  listen START mode=%s -> luu goi Opus vao %s", mode, os.path.relpath(path, HERE))

    def on_audio(self, payload: bytes):
        self.frames += 1
        self.bytes += len(payload)
        if self.dump:
            self.dump.write(struct.pack("<H", len(payload)) + payload)
        if self.frames == 1:
            log.info("  goi Opus dau tien: %d byte", len(payload))

    def stop_listen(self, reason: str = ""):
        if self.dump is None:
            return
        secs = time.monotonic() - self.listen_started
        self.dump.close()
        self.dump = None
        # Khung 60 ms: so goi x 0.06 phai xap xi thoi gian thuc. Lech nhieu
        # nghia la rot goi hoac khung khac 60 ms.
        log.info("  listen STOP%s: %d goi, %d byte, %.1f s thuc te, %.1f s theo so goi x 60ms",
                 f" ({reason})" if reason else "", self.frames, self.bytes, secs, self.frames * 0.06)


async def handle_ws(request: web.Request) -> web.WebSocketResponse:
    h = request.headers
    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)

    session = Session(h.get("Device-Id", "?"))
    log.info("WS MO | Device-Id=%s | Client-Id=%s | Protocol-Version=%s | token=%s",
             h.get("Device-Id"), h.get("Client-Id"), h.get("Protocol-Version"),
             "co" if h.get("Authorization") else "khong")

    try:
        async for msg in ws:
            if msg.type == WSMsgType.BINARY:
                session.on_audio(msg.data)
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
                    # Tra dung tham so ESP32 gui len. Buoc noi TTS se doi sang
                    # tan so dau ra cua board (24 kHz) khi thuc su phat tieng.
                    "audio_params": {"format": "opus", "sample_rate": 16000,
                                     "channels": 1, "frame_duration": 60},
                }
                await ws.send_json(reply)
                log.info("  >> hello session_id=%s", session.id)
            elif kind == "listen":
                state = data.get("state")
                if state == "start":
                    session.start_listen(data.get("mode", "?"))
                elif state == "stop":
                    session.stop_listen()
                else:
                    log.info("  << listen %s", json.dumps(data, ensure_ascii=False))
            elif kind == "abort":
                log.info("  << abort %s", data.get("reason", ""))
            else:
                log.info("  << %s", json.dumps(data, ensure_ascii=False)[:200])
    finally:
        session.stop_listen("mat ket noi")
        log.info("WS DONG | Device-Id=%s", session.device_id)
    return ws


def make_app() -> web.Application:
    app = web.Application()
    app.router.add_route("*", "/xiaozhi/ota/", handle_ota)
    app.router.add_get("/xiaozhi/v1/", handle_ws)
    return app


def main():
    p = argparse.ArgumentParser(description="Server giao thuc xiaozhi (Moc 0)")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--host", default="127.0.0.1",
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
    web.run_app(make_app(), host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
