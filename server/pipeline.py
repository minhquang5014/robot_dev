"""
Duong ong voice -> voice cho robot: STT -> LLM -> TTS.

Tach rieng khoi phan mang de sau nay server WebSocket that goi lai duoc y
nguyen ba ham nay, khong phai viet lai. Test_voice.py la nguoi dung dau tien.
"""

import asyncio
import os
import re
import time
from dataclasses import dataclass, field

import requests

GROQ_BASE = "https://api.groq.com/openai/v1"

# Danh sach emotion ma firmware hieu duoc, lay tu
# xiaozhi-esp32/main/boards/espressif/esp-vocat/assets/360_360/emote.json
# Gui ten ngoai danh sach nay thi thiet bi im lang roi ve neutral.
VALID_EMOTIONS = {
    "neutral", "happy", "laughing", "funny", "loving", "embarrassed",
    "confident", "delicious", "sad", "crying", "sleepy", "silly", "angry",
    "surprised", "shocked", "thinking", "winking", "relaxed", "confused",
}

SYSTEM_PROMPT = """
Bạn là một robot để bàn nhỏ, tên là Mơ. Bạn nói tiếng Việt.

Luật bắt buộc:
1. Bắt đầu MỌI câu trả lời bằng đúng MỘT tag cảm xúc trong ngoặc vuông, chọn
   một trong các từ sau: {emotions}
2. Sau tag là câu trả lời, TỐI ĐA 2 CÂU. Ngắn gọn như thú cưng, không giảng giải.
   Không chèn thêm tag nào nữa ở giữa câu.
3. Xưng "tớ", gọi người đối diện là "cậu". Giọng trẻ con, vui vẻ, tò mò.
4. Viết tiếng Việt CÓ DẤU đầy đủ. Không dùng emoji, không markdown.
   Câu trả lời sẽ được đọc thành tiếng, chữ không dấu sẽ bị đọc sai hoàn toàn.

Ví dụ:
[happy] Tớ đây! Cậu vừa đi đâu về thế?
[thinking] Hmm, cái này tớ chưa biết nữa.
"""


@dataclass
class Turn:
    """Ket qua mot luot noi, kem thoi gian tung chang de soi do tre."""
    transcript: str = ""
    emotion: str = "neutral"
    reply: str = ""
    audio_path: str = ""
    ms_stt: int = 0
    ms_llm: int = 0
    ms_tts: int = 0
    history: list = field(default_factory=list)

    @property
    def ms_total(self) -> int:
        return self.ms_stt + self.ms_llm + self.ms_tts


class PipelineError(RuntimeError):
    pass


def _groq_headers() -> dict:
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key:
        raise PipelineError(
            "Thieu GROQ_API_KEY. Copy server/.env.example thanh server/.env "
            "roi dien key vao."
        )
    return {"Authorization": f"Bearer {key}"}


def list_models() -> list:
    """Hoi Groq xem hien con nhung model nao. Groq co xoa model theo thoi gian,
    nen khi gap loi 404 model_not_found thi chay ham nay truoc khi doan mo."""
    r = requests.get(f"{GROQ_BASE}/models", headers=_groq_headers(), timeout=30)
    r.raise_for_status()
    return sorted(m["id"] for m in r.json().get("data", []))


def speech_to_text(audio_path: str, model: str = None) -> str:
    model = model or os.environ.get("STT_MODEL", "whisper-large-v3-turbo")
    with open(audio_path, "rb") as f:
        r = requests.post(
            f"{GROQ_BASE}/audio/transcriptions",
            headers=_groq_headers(),
            files={"file": (os.path.basename(audio_path), f)},
            data={
                "model": model,
                # Ep tieng Viet. Bo dong nay thi Whisper doan ngon ngu, va
                # cau tieng Viet ngan rat hay bi doan nham thanh tieng Trung.
                "language": "vi",
            },
            timeout=120,
        )
    if r.status_code != 200:
        raise PipelineError(f"STT that bai ({r.status_code}): {r.text[:300]}")
    return r.json().get("text", "").strip()


def _split_emotion(raw: str) -> tuple:
    """Bóc tag [happy] o dau cau. Tra ve (emotion, phan con lai).

    LLM 8B thinh thoang quen tag hoac bia ten la -> ve neutral thay vi no.
    """
    m = re.match(r"\s*\[([a-zA-Z_]+)\]\s*(.*)", raw, flags=re.DOTALL)
    if not m:
        return "neutral", _strip_stray_tags(raw)
    name = m.group(1).lower()
    body = _strip_stray_tags(m.group(2))
    if name not in VALID_EMOTIONS:
        return "neutral", body
    return name, body


def _strip_stray_tags(text: str) -> str:
    """Bo moi tag [...] con sot lai giua cau.

    Model nho doi khi chen them tag o giua ("... cau sao roi? [laughing] To dang
    cho keo"). Khong loc thi TTS se doc to chu "laughing" ra loa.
    """
    return re.sub(r"\s*\[[a-zA-Z_]+\]\s*", " ", text).strip()


def think(transcript: str, history: list = None, model: str = None,
          reasoning_effort: str = None) -> tuple:
    """Tra ve (emotion, reply, history_moi)."""
    model = model or os.environ.get("LLM_MODEL", "qwen/qwen3.8-27b")
    history = list(history or [])

    # Chi ap dung cho ho gpt-oss. Model mac dinh (qwen) khong phai model
    # reasoning nen nhanh nay khong chay — giu lai de doi model de dang.
    # Voi gpt-oss, "low" ha trung vi tu 1927ms xuong 723ms.
    extra = {}
    effort = reasoning_effort or os.environ.get("REASONING_EFFORT", "low")
    if effort and "gpt-oss" in model:
        extra["reasoning_effort"] = effort

    messages = [
        {"role": "system",
         "content": SYSTEM_PROMPT.format(emotions=", ".join(sorted(VALID_EMOTIONS)))},
        *history,
        {"role": "user", "content": transcript},
    ]

    r = requests.post(
        f"{GROQ_BASE}/chat/completions",
        headers={**_groq_headers(), "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": messages,
            "temperature": 0.8,   # co tinh cach mot chut, dung nhat nheo
            # Model reasoning dot token suy nghi an BEN TRONG han muc nay. De
            # 150 thi reasoning an sach, content tra ve chuoi rong va
            # finish_reason = "length". 400 du cho ca suy nghi lan 2 cau tra loi.
            "max_tokens": 400,
            **extra,
        },
        timeout=60,
    )
    if r.status_code != 200:
        raise PipelineError(f"LLM that bai ({r.status_code}): {r.text[:300]}")

    raw = r.json()["choices"][0]["message"]["content"]
    emotion, reply = _split_emotion(raw)

    history.append({"role": "user", "content": transcript})
    history.append({"role": "assistant", "content": raw})
    return emotion, reply, history


async def _tts_async(text: str, out_path: str, voice: str, rate: str, pitch: str):
    import edge_tts
    await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(out_path)


# Endpoint EdgeTTS mien phi thinh thoang tra ve NoAudioReceived du tham so dung
# y nguyen. Do thuc te ngay 16/09/2026: 4/16 lan hong (25%), khong theo quy luat
# nao — cung mot cau, cung tham so, lan duoc lan khong.
# Do lai voi 48 lan goi: hong 31%, KHONG lien quan do dai cau hay tham so
# pitch/rate — that bai di theo tung DOT, co luc hong 5/6 lan lien tiep roi
# tu nhien tot lai. Vi vay retry phai gian thua ra, thu lien tiep vo ich.
TTS_MAX_ATTEMPTS = 4


def text_to_speech(text: str, out_path: str, voice: str = None,
                   rate: str = None, pitch: str = None) -> str:
    text = (text or "").strip()
    if not text:
        raise PipelineError("Khong co gi de doc — LLM tra ve chuoi rong.")

    voice = voice or os.environ.get("TTS_VOICE", "vi-VN-HoaiMyNeural")
    rate = rate or os.environ.get("TTS_RATE", "+10%")
    pitch = pitch or os.environ.get("TTS_PITCH", "+15Hz")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    last_error = None
    for attempt in range(1, TTS_MAX_ATTEMPTS + 1):
        try:
            asyncio.run(_tts_async(text, out_path, voice, rate, pitch))
            if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                return out_path
            last_error = "file rong"
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
        if attempt < TTS_MAX_ATTEMPTS:
            time.sleep(0.3 * (2 ** (attempt - 1)))

    raise PipelineError(
        f"EdgeTTS that bai sau {TTS_MAX_ATTEMPTS} lan thu ({last_error}). "
        f"Neu hong lien tuc thi kiem tra ten giong ({voice}) bang "
        "`edge-tts --list-voices`, hoac nang cap: pip install -U edge-tts"
    )


def run_turn(audio_path: str, out_path: str, history: list = None) -> Turn:
    """Chay tron mot luot voice -> voice, do thoi gian tung chang."""
    turn = Turn()

    t0 = time.perf_counter()
    turn.transcript = speech_to_text(audio_path)
    turn.ms_stt = int((time.perf_counter() - t0) * 1000)

    if not turn.transcript:
        raise PipelineError("STT tra ve chuoi rong — kiem tra lai file am thanh.")

    t0 = time.perf_counter()
    turn.emotion, turn.reply, turn.history = think(turn.transcript, history)
    turn.ms_llm = int((time.perf_counter() - t0) * 1000)

    t0 = time.perf_counter()
    turn.audio_path = text_to_speech(turn.reply, out_path)
    turn.ms_tts = int((time.perf_counter() - t0) * 1000)

    return turn
