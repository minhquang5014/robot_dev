"""
Codec Opus va phat hien nguoi noi dut cau, cho server xiaozhi.

Firmware noi chuyen bang Opus THO 16 kHz mono khung 60 ms (Protocol-Version 1,
websocket_protocol.cc). Module nay lo hai chieu:

  - thiet bi -> server : OpusDecoder  -> PCM 16 kHz de dua cho STT
  - server -> thiet bi : OpusEncoder  -> goi Opus 60 ms de phat ra loa

Dung PyAV vi no keo theo ffmpeg co san libopus, co wheel Windows, khong phai
tu cai libopus roi chi duong dan DLL nhu opuslib.

Hai cai bay da vap phai khi dung PyAV, ghi lai keo quen:

  1. Encoder mac dinh cho khung 20 ms (frame_size 320). Firmware doi 60 ms.
     Phai dat options={"frame_duration": "60"} TRUOC khi open() thi frame_size
     moi thanh 960.
  2. Decoder libopus luon chay trong o 48 kHz. Dat ctx.sample_rate = 16000
     KHONG co tac dung — giai ma 1 giay tieng ra 47040 mau chu khong phai
     16000. Phai cho qua AudioResampler.
"""

import logging
import os
import time
import wave

import numpy as np

log = logging.getLogger("xz.audio")

SAMPLE_RATE = 16000
FRAME_MS = 60
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000      # 960
# Tan so tieng server gui XUONG. Board nay phat o 24 kHz; gui 16 kHz thi firmware
# phai tu doi tan so va bao "resampling may cause distortion" (log 06/10/2026).
OUT_RATE = 24000
VAD_FRAME_MS = 30                                   # webrtcvad chi nhan 10/20/30
VAD_FRAME_SAMPLES = SAMPLE_RATE * VAD_FRAME_MS // 1000


class OpusDecoder:
    """Goi Opus tho -> PCM int16 mono 16 kHz."""

    def __init__(self):
        import av
        self._av = av
        self.ctx = av.codec.CodecContext.create("libopus", "r")
        self.ctx.sample_rate = SAMPLE_RATE
        self.ctx.format = "s16"
        self.ctx.layout = "mono"
        self.ctx.open()
        # Bay so 2: khong co cai nay thi ra 48 kHz.
        self.rs = av.audio.resampler.AudioResampler(
            format="s16", layout="mono", rate=SAMPLE_RATE)

    def decode(self, packet: bytes) -> np.ndarray:
        out = []
        try:
            for fr in self.ctx.decode(self._av.Packet(packet)):
                for g in self.rs.resample(fr):
                    out.append(g.to_ndarray().reshape(-1))
        except Exception as e:
            # Mot goi hong khong duoc lam sap ca luot noi.
            log.debug("bo qua goi Opus hong: %s", e)
            return np.zeros(0, np.int16)
        return np.concatenate(out) if out else np.zeros(0, np.int16)


class OpusEncoder:
    """PCM int16 mono -> goi Opus 60 ms."""

    def __init__(self, bitrate: int = 24000, rate: int = SAMPLE_RATE):
        import av
        self._av = av
        self.rate = rate
        self.frame = rate * FRAME_MS // 1000
        ctx = av.codec.CodecContext.create("libopus", "w")
        ctx.sample_rate = rate
        ctx.format = "s16"
        ctx.layout = "mono"
        ctx.bit_rate = bitrate
        # Bay so 1. "voip" thay vi "audio" vi day la giong noi.
        ctx.options = {"frame_duration": str(FRAME_MS), "application": "voip"}
        ctx.open()
        self.ctx = ctx
        self._pts = 0
        self._tail = np.zeros(0, np.int16)

    def encode(self, pcm: np.ndarray) -> list:
        """Nhan PCM dai bao nhieu cung duoc, tra ve cac goi 60 ms tron ven.

        Phan du duoc giu lai cho lan goi sau — TTS tra ve tung mau khong chia
        het cho 960, neu moi lan deu dem 0 cho du thi cau noi se bi ram rap.
        """
        buf = np.concatenate([self._tail, pcm]) if len(self._tail) else pcm
        pkts = []
        i = 0
        while i + self.frame <= len(buf):
            pkts += self._one(buf[i:i+self.frame])
            i += self.frame
        self._tail = buf[i:].copy()
        return pkts

    def flush(self) -> list:
        """Goi khi het cau: dem im lang cho du khung cuoi roi dong encoder."""
        pkts = []
        if len(self._tail):
            pad = np.zeros(self.frame - len(self._tail), np.int16)
            pkts += self._one(np.concatenate([self._tail, pad]))
            self._tail = np.zeros(0, np.int16)
        try:
            for p in self.ctx.encode(None):
                pkts.append(bytes(p))
        except Exception:
            pass
        return pkts

    def _one(self, chunk: np.ndarray) -> list:
        fr = self._av.AudioFrame.from_ndarray(
            np.ascontiguousarray(chunk).reshape(1, -1), format="s16", layout="mono")
        fr.sample_rate = self.rate
        fr.pts = self._pts
        self._pts += self.frame
        return [bytes(p) for p in self.ctx.encode(fr)]


# Tran cua bo han bien, KHONG phai 1.0. Opus la codec co ton that: tin hieu
# ra co the vot cao hon tin hieu vao mot chut. Ep sat 1.0 thi cai vot do cham
# tran va nghe RE. Chua lai ~0.7 dB headroom la het.
#
# Do ngay 06/10/2026, cau "Xin chao, to la Mo...", dem so mau cham tran SAU
# khi ma hoa Opus roi giai ma lai — tuc dung thu thiet bi nghe:
#
#     gain   tran 1.00        tran 0.92
#      4 dB   0 mau           0 mau    rms -14.1
#      6 dB   1 mau           0 mau    rms -12.1   <-- dang dung
#      8 dB  18 mau           7 mau    rms -10.4
#     10 dB 114 mau          42 mau    rms  -8.6   <-- muc cu, chinh la cho re
#
# Tieng xAI goc dinh -4.8 dBFS, SACH, khong mot mau nao cham tran. Toan bo
# tieng re la do minh khuech dai qua tay roi nen vao bo han bien.
KNEE = 0.6
CEIL = 0.92


def boost(pcm: np.ndarray, gain_db: float) -> np.ndarray:
    """Keo to tieng TTS ma khong re. Tung mau mot nen dung duoc ngay tren
    luong streaming, khong phai doi het cau.

    Do 06/10/2026: tieng xAI dinh chi -7,1 dBFS, trung binh -20,4 dBFS — nho
    han han server tenclass tren cung loa. Duoi 0.7 giu tuyen tinh, tren do
    be cong mem (tanh) ve 1.0 thay vi cat cut.
    """
    if gain_db <= 0 or not len(pcm):
        return pcm
    x = pcm.astype(np.float32) / 32768.0 * (10 ** (gain_db / 20.0))
    a = np.abs(x)
    over = a > KNEE
    x[over] = np.sign(x[over]) * (KNEE + (CEIL - KNEE) *
                                  np.tanh((a[over] - KNEE) / (CEIL - KNEE)))
    return (np.clip(x, -CEIL, CEIL) * 32767).astype(np.int16)


class SpeechDetector:
    """Biet luc nao nguoi noi da dut cau.

    Che do `auto` cua firmware (application.cc:807) cu gui audio mai khong
    dung — server phai tu quyet dinh. Ghep hai dieu kien:

      - webrtcvad noi day la tieng noi, VA
      - nang luong khung vuot nguong

    Chi VAD thoi thi tieng quat, tieng go ban cung lam no bat; do ngay
    27/09/2026 VAD muc 3 coi nhieu bien do 30 la tieng noi. Nguong nang luong
    loc bot, ma van re hon nhieu so voi keo ca Silero + torch vao.
    """

    # silence_ms la nua do tre ma nguoi dung cam nhan duoc. Do tren Fly ngay
    # 06/10: tu luc NGUNG NOI den khi co tieng mat 1844ms, trong do 800ms chi
    # la ngoi cho xem co noi tiep khong. Ha xuong 350ms thi con ~1400ms.
    # Danh doi: noi ma ngap ngung giua cau se bi cat ngang. Dat bang bien moi
    # truong VAD_SILENCE_MS neu muon chinh ma khong sua code.
    def __init__(self, silence_ms: int = None, min_speech_ms: int = 300,
                 max_ms: int = 15000, energy: int = 200, aggressiveness: int = 2):
        if silence_ms is None:
            silence_ms = int(os.environ.get("VAD_SILENCE_MS", "350"))
        import webrtcvad
        self.vad = webrtcvad.Vad(aggressiveness)
        self.silence_ms = silence_ms
        self.min_speech_ms = min_speech_ms
        self.max_ms = max_ms
        self.energy = energy
        self.reset()

    def reset(self):
        self.speech_ms = 0
        self.quiet_ms = 0
        self.total_ms = 0
        self.started = False

    def feed(self, pcm: np.ndarray) -> bool:
        """Nem vao PCM (bao nhieu cung duoc). True = nguoi noi da dut cau."""
        for i in range(0, len(pcm) - VAD_FRAME_SAMPLES + 1, VAD_FRAME_SAMPLES):
            f = pcm[i:i+VAD_FRAME_SAMPLES]
            self.total_ms += VAD_FRAME_MS
            loud = float(np.abs(f.astype(np.float32)).mean()) >= self.energy
            try:
                voiced = loud and self.vad.is_speech(f.tobytes(), SAMPLE_RATE)
            except Exception:
                voiced = loud
            if voiced:
                self.speech_ms += VAD_FRAME_MS
                self.quiet_ms = 0
                if self.speech_ms >= self.min_speech_ms:
                    self.started = True
            else:
                self.quiet_ms += VAD_FRAME_MS
            if self.started and self.quiet_ms >= self.silence_ms:
                return True
            if self.total_ms >= self.max_ms:
                # Het gio. Chi coi la co cau noi neu that su nghe thay gi do.
                return self.started
        return False


class Pacer:
    """Gui goi Opus dung nhip phat, khong dua het mot luc.

    Bam theo dong ho vi-tri-phat ao thay vi sleep(0.06) moi vong: sleep cong
    don sai so, phat 10 giay la lech thay ro. Cach nay lay moc tu luc bat dau
    nen khong bao gio troi.

    `lead_ms` cho phep gui truoc mot chut de loa khong bi hut khi mang giat.
    """

    def __init__(self, lead_ms: int = 300):
        self.lead_ms = lead_ms
        self.start = None
        self.pos_ms = 0

    async def wait(self):
        import asyncio
        if self.start is None:
            self.start = time.monotonic()
        due = self.start + (self.pos_ms - self.lead_ms) / 1000.0
        delay = due - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        self.pos_ms += FRAME_MS


def write_wav(pcm: np.ndarray, path: str):
    """Ghi PCM ra WAV 16 kHz mono. Dung de nghe lai khi soi loi."""
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.astype(np.int16).tobytes())
    return path


def write_ogg(pcm: np.ndarray, path: str, bitrate: int = 24000):
    """Ghi PCM ra Ogg/Opus — ĐAY la tep dua cho STT, khong phai WAV.

    Do ngay 27/09/2026, cung 3.16 giay tieng, ba lan goi Groq moi kieu:

        WAV     118 KB  ->  trung vi 1324 ms
        Ogg     8 KB    ->  trung vi  377 ms

    Ban ghi chep ra y het nhau. Nut co chai la DUNG LUONG TAI LEN chu khong
    phai do dai tieng — cat im lang hai dau chi ha 1324 xuong 1259 ms, trong
    khi nen lai ha xuong 377 ms. Voi mot con robot ngoi sau duong mang gia
    dinh, 110 KB kia la gan mot giay.
    """
    import av
    c = av.open(path, "w", format="ogg")
    st = c.add_stream("libopus", rate=SAMPLE_RATE)
    st.bit_rate = bitrate
    try:
        st.layout = "mono"
    except Exception:
        pass
    fr = av.AudioFrame.from_ndarray(
        np.ascontiguousarray(pcm).astype(np.int16).reshape(1, -1),
        format="s16", layout="mono")
    fr.sample_rate = SAMPLE_RATE
    fr.pts = 0
    for p in st.encode(fr):
        c.mux(p)
    for p in st.encode(None):
        c.mux(p)
    c.close()
    return path
