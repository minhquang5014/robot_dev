"""
Duong ong voice -> voice cho robot: STT -> LLM -> TTS.

Tach rieng khoi phan mang de sau nay server WebSocket that goi lai duoc y
nguyen cac ham nay, khong phai viet lai. Test_voice.py la nguoi dung dau tien.

Hai cach dung:
  - Dong bo  : run_turn()          -> doi xong ca cau roi moi co file mp3.
  - Streaming: run_turn_stream()   -> async generator, nhan chunk MP3 ngay khi
                                      EdgeTTS gui ve. Server that dung cach nay.
"""

import asyncio
import logging
import os
import re
import time
from dataclasses import dataclass, field

import requests

log = logging.getLogger("pipeline")

GROQ_BASE = "https://api.groq.com/openai/v1"

# Danh sach emotion ma firmware hieu duoc, lay tu
# xiaozhi-esp32/main/boards/espressif/esp-vocat/assets/360_360/emote.json
# Gui ten ngoai danh sach nay thi thiet bi im lang roi ve neutral.
VALID_EMOTIONS = {
    "neutral", "happy", "laughing", "funny", "loving", "embarrassed",
    "confident", "delicious", "sad", "crying", "sleepy", "silly", "angry",
    "surprised", "shocked", "thinking", "winking", "relaxed", "confused",
}

# Model hay tu bia ten cam xuc tu nhien hon danh sach tren. Do ngay 17/09/2026:
# 1/4 cau chao tra ve [excited] -> truoc day bi am tham doi thanh neutral.
# Quy ve ten gan nghia nhat thay vi vut di.
EMOTION_ALIASES = {
    "excited": "happy", "joyful": "happy", "cheerful": "happy", "glad": "happy",
    "smile": "happy", "smiling": "happy", "grateful": "happy",
    "laugh": "laughing", "giggle": "laughing",
    "love": "loving", "affectionate": "loving", "caring": "loving", "warm": "loving",
    "shy": "embarrassed", "blush": "embarrassed", "awkward": "embarrassed",
    "proud": "confident", "determined": "confident",
    "yummy": "delicious", "hungry": "delicious",
    "unhappy": "sad", "lonely": "sad", "disappointed": "sad", "sorry": "sad",
    "cry": "crying", "tearful": "crying",
    "tired": "sleepy", "bored": "sleepy",
    "playful": "silly", "goofy": "silly",
    "mischievous": "winking", "wink": "winking",
    "mad": "angry", "annoyed": "angry", "grumpy": "angry",
    "amazed": "surprised", "curious": "surprised",
    "scared": "shocked", "afraid": "shocked", "fear": "shocked",
    "wondering": "thinking", "pondering": "thinking",
    "calm": "relaxed", "chill": "relaxed", "peaceful": "relaxed",
    "puzzled": "confused", "worried": "confused",
}

SYSTEM_PROMPT = """
Bạn là một robot để bàn nhỏ, tên là Mơ. Bạn nói tiếng Việt.

Luật bắt buộc:
1. Bắt đầu MỌI câu trả lời bằng đúng MỘT tag cảm xúc trong ngoặc vuông. CHỈ được
   dùng một trong các từ sau, không tự đặt từ khác: {emotions}
2. Sau tag là câu trả lời, TỐI ĐA 2 CÂU ngắn. Ngắn gọn như thú cưng, không giảng giải.
   Không chèn thêm tag nào nữa ở giữa câu.
3. Xưng "tớ", gọi người đối diện là "cậu". Giọng trẻ con, vui vẻ, tò mò.
4. Luôn trả lời bằng tiếng Việt CÓ DẤU đầy đủ, không dùng tiếng Anh.
   Không dùng emoji, không markdown.
   Câu trả lời sẽ được đọc thành tiếng, chữ không dấu sẽ bị đọc sai hoàn toàn.
5. Phản ứng đúng vào điều cậu ấy vừa nói, mỗi lần một kiểu khác nhau.
   Ví dụ bên dưới chỉ minh hoạ ĐỊNH DẠNG, tuyệt đối không chép lại nội dung.

Ví dụ định dạng:
[surprised] Ơ, thật hả? Kể tớ nghe tiếp đi!
[sleepy] Tớ buồn ngủ díp cả mắt rồi nè.
"""

# Model reasoning dot token suy nghi an BEN TRONG max_tokens. De 150 thi
# reasoning an sach, content tra ve chuoi rong va finish_reason = "length".
REASONING_MODEL_HINTS = ("gpt-oss",)


@dataclass
class Turn:
    """Ket qua mot luot noi, kem thoi gian tung chang de soi do tre."""
    transcript: str = ""
    emotion: str = "neutral"
    emotion_raw: str = ""      # tag nguyen van LLM tra ve, de biet co bi quy doi
    reply: str = ""
    audio_path: str = ""
    ms_stt: int = 0
    ms_llm: int = 0
    ms_tts: int = 0
    ms_tts_first: int = 0      # streaming: TTS mat bao lau moi co chunk dau
    ms_first_audio: int = 0    # streaming: tu luc bat dau den chunk audio dau
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
    """Bóc tag [happy] o dau cau. Tra ve (emotion, phan con lai, tag nguyen van).

    Truoc day tag la va quen tag deu am tham ve neutral, nhin ket qua khong
    phan biet duoc voi truong hop model chu dong chon neutral. Gio ghi log.
    """
    m = re.match(r"\s*\[([a-zA-Z_]+)\]\s*(.*)", raw, flags=re.DOTALL)
    if not m:
        log.warning("LLM quen tag cam xuc: %r", raw[:60])
        return "neutral", _strip_stray_tags(raw), ""
    tag = m.group(1).lower()
    body = _strip_stray_tags(m.group(2))
    if tag in VALID_EMOTIONS:
        return tag, body, tag
    if tag in EMOTION_ALIASES:
        log.info("Tag cam xuc [%s] -> %s", tag, EMOTION_ALIASES[tag])
        return EMOTION_ALIASES[tag], body, tag
    log.warning("Tag cam xuc la [%s], khong co trong danh sach -> neutral", tag)
    return "neutral", body, tag


def _strip_stray_tags(text: str) -> str:
    """Bo moi tag [...] con sot lai giua cau.

    Model nho doi khi chen them tag o giua ("... cau sao roi? [laughing] To dang
    cho keo"). Khong loc thi TTS se doc to chu "laughing" ra loa.
    """
    return re.sub(r"\s*\[[a-zA-Z_]+\]\s*", " ", text).strip()


_VN_CHARS = set("àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡ"
                "ùúụủũưừứựửữỳýỵỷỹđ")


def _looks_vietnamese(text: str) -> bool:
    """Cau tieng Viet tu 3 tu tro len gan nhu luon co it nhat mot chu co dau.

    Do ngay 17/09/2026: qwen tra ve "[d] Oh my, that sounds delicious!" 1/10
    lan — giong doc tieng Viet ma doc cau tieng Anh thi nghe rat te.
    """
    words = re.findall(r"\w+", text)
    return len(words) < 3 or any(set(w.lower()) & _VN_CHARS for w in words)


def think(transcript: str, history: list = None, model: str = None,
          reasoning_effort: str = None) -> tuple:
    """Tra ve (emotion, reply, history_moi, tag_nguyen_van)."""
    model = model or os.environ.get("LLM_MODEL", "qwen/qwen3.8-27b")
    history = list(history or [])
    is_reasoning = any(h in model for h in REASONING_MODEL_HINTS)

    # Voi gpt-oss, reasoning_effort "low" ha trung vi tu 1927ms xuong 723ms.
    extra = {}
    effort = reasoning_effort or os.environ.get("REASONING_EFFORT", "low")
    if effort and is_reasoning:
        extra["reasoning_effort"] = effort

    messages = [
        {"role": "system",
         "content": SYSTEM_PROMPT.format(emotions=", ".join(sorted(VALID_EMOTIONS)))},
        *history,
        {"role": "user", "content": transcript},
    ]

    # Hoi lai toi da 1 lan neu cau tra loi khong phai tieng Viet. Chi ton them
    # ~360ms o dung nhung luot hong, luot binh thuong khong mat gi.
    for attempt in (1, 2):
        r = requests.post(
            f"{GROQ_BASE}/chat/completions",
            headers={**_groq_headers(), "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": messages,
                "temperature": 0.8,   # co tinh cach mot chut, dung nhat nheo
                # 400 du cho reasoning lan 2 cau tra loi. Model thuong chi can
                # 150: 2 cau ngan ~60 token, tran nay chan model lan man.
                "max_tokens": 400 if is_reasoning else 150,
                **extra,
            },
            timeout=60,
        )
        if r.status_code != 200:
            raise PipelineError(f"LLM that bai ({r.status_code}): {r.text[:300]}")

        raw = r.json()["choices"][0]["message"]["content"] or ""
        emotion, reply, tag = _split_emotion(raw)
        if _looks_vietnamese(reply):
            break
        log.warning("LLM tra loi khong phai tieng Viet (lan %d): %r", attempt, raw[:60])

    history.append({"role": "user", "content": transcript})
    history.append({"role": "assistant", "content": raw})
    return emotion, reply, history, tag


# Endpoint EdgeTTS mien phi thinh thoang tra ve NoAudioReceived du tham so dung
# y nguyen. Do ngay 16/09/2026 voi 48 lan goi: hong 31%, KHONG lien quan do dai
# cau hay tham so pitch/rate — that bai di theo tung DOT, co luc hong 5/6 lan
# lien tiep roi tu nhien tot lai. Vi vay retry phai gian thua ra.
# (Ngay 17/09/2026 do lai 13 lan tren mang khac: 13/13 thanh cong.)
TTS_MAX_ATTEMPTS = 4


def _tts_params(voice, rate, pitch) -> tuple:
    return (voice or os.environ.get("TTS_VOICE", "vi-VN-HoaiMyNeural"),
            rate or os.environ.get("TTS_RATE", "+10%"),
            pitch or os.environ.get("TTS_PITCH", "+15Hz"))


async def text_to_speech_stream(text: str, voice: str = None, rate: str = None,
                                pitch: str = None):
    """Async generator: tra ve tung chunk MP3 ngay khi EdgeTTS gui ve.

    Do ngay 17/09/2026, cau 79 ky tu: chunk dau ~500ms, xong ca cau ~750ms.
    Phat ngay chunk dau thi nguoi nghe khong phai doi ca cau.
    """
    import edge_tts

    text = (text or "").strip()
    if not text:
        raise PipelineError("Khong co gi de doc — LLM tra ve chuoi rong.")
    voice, rate, pitch = _tts_params(voice, rate, pitch)

    last_error = None
    for attempt in range(1, TTS_MAX_ATTEMPTS + 1):
        got_audio = False
        stream = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).stream()
        try:
            async for chunk in stream:
                if chunk["type"] == "audio" and chunk["data"]:
                    got_audio = True
                    yield chunk["data"]
            if got_audio:
                return
            last_error = "khong nhan duoc audio"
        except Exception as e:
            if got_audio:
                # Mot phan cau da phat ra loa. Thu lai tu dau se doc lap lai
                # doan dau, nghe con te hon — bao loi luon.
                raise PipelineError(f"EdgeTTS dut giua cau: {type(e).__name__}: {e}") from e
            last_error = f"{type(e).__name__}: {e}"
        finally:
            # Nguoi dung ngat loi giua cau thi dong websocket toi Microsoft NGAY,
            # khong phu thuoc luc nao bo don rac chay. Do ngay 17/09/2026: bo
            # dong nay thi server song lau van tu don duoc (0 canh bao) — chi
            # bao "Unclosed client session" khi tien trinh thoat ngay sau khi
            # ngat. Nen day la don dep tuong minh, khong phai va loi ro ri.
            await stream.aclose()
        if attempt < TTS_MAX_ATTEMPTS:
            log.warning("EdgeTTS lan %d that bai (%s), thu lai", attempt, last_error)
            await asyncio.sleep(0.3 * (2 ** (attempt - 1)))

    raise PipelineError(
        f"EdgeTTS that bai sau {TTS_MAX_ATTEMPTS} lan thu ({last_error}). "
        f"Neu hong lien tuc thi kiem tra ten giong ({voice}) bang "
        "`edge-tts --list-voices`, hoac nang cap: pip install -U edge-tts"
    )


async def text_to_speech_async(text: str, out_path: str, voice: str = None,
                               rate: str = None, pitch: str = None) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "wb") as f:
        async for chunk in text_to_speech_stream(text, voice, rate, pitch):
            f.write(chunk)
    return out_path


def text_to_speech(text: str, out_path: str, voice: str = None,
                   rate: str = None, pitch: str = None) -> str:
    """Ban dong bo cho CLI. Trong server async hay dung text_to_speech_async."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(text_to_speech_async(text, out_path, voice, rate, pitch))
    # asyncio.run() goi tu trong event loop dang chay se no RuntimeError.
    raise PipelineError(
        "text_to_speech() dang bi goi tu trong event loop. "
        "Dung `await text_to_speech_async(...)` hoac text_to_speech_stream()."
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
    turn.emotion, turn.reply, turn.history, turn.emotion_raw = think(turn.transcript, history)
    turn.ms_llm = int((time.perf_counter() - t0) * 1000)

    t0 = time.perf_counter()
    turn.audio_path = text_to_speech(turn.reply, out_path)
    turn.ms_tts = int((time.perf_counter() - t0) * 1000)

    return turn


async def run_turn_stream(turn: Turn, audio_path: str = None, text: str = None,
                          history: list = None):
    """Async generator: dien dan `turn`, yield chunk MP3 ngay khi co.

    turn.emotion da co truoc chunk dau tien -> server gui cam xuc de firmware
    ve mat TRUOC, roi moi day audio. STT va LLM dung requests (chan), nen day
    sang thread de khong khoa event loop cua server.
    """
    start = time.perf_counter()

    if text is None:
        t0 = time.perf_counter()
        turn.transcript = await asyncio.to_thread(speech_to_text, audio_path)
        turn.ms_stt = int((time.perf_counter() - t0) * 1000)
        if not turn.transcript:
            raise PipelineError("STT tra ve chuoi rong — kiem tra lai file am thanh.")
    else:
        turn.transcript = text

    t0 = time.perf_counter()
    turn.emotion, turn.reply, turn.history, turn.emotion_raw = await asyncio.to_thread(
        think, turn.transcript, history)
    turn.ms_llm = int((time.perf_counter() - t0) * 1000)

    t0 = time.perf_counter()
    tts = text_to_speech_stream(turn.reply)
    try:
        async for chunk in tts:
            if not turn.ms_first_audio:
                turn.ms_tts_first = int((time.perf_counter() - t0) * 1000)
                turn.ms_first_audio = int((time.perf_counter() - start) * 1000)
            yield chunk
    finally:
        # Ngat loi thi dong TTS ngay. Ben goi nen boc
        # `async with contextlib.aclosing(run_turn_stream(...))` de viec dong
        # xay ra dung luc ngat, thay vi doi bo don rac.
        await tts.aclose()
    turn.ms_tts = int((time.perf_counter() - t0) * 1000)
