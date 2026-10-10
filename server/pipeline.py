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
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field

import requests

log = logging.getLogger("pipeline")

GROQ_BASE = "https://api.groq.com/openai/v1"
XAI_BASE = "https://api.x.ai/v1"

# Mot Session dung chung cho ca tien trinh, KHONG phai requests.post() roi le.
# Do ngay 27/09/2026, 4 luot moi kieu: mo ket noi moi moi lan -> trung vi
# 683ms; dung lai Session -> 438ms. Moi luot noi goi Groq hai lan (STT + LLM)
# nen khoan nay mot minh no da la ~490ms.
#
# pool_maxsize > 1 vi server that chay nhieu ket noi WebSocket song song; de
# mac dinh 10 la du cho mot con robot de ban.
def _make_session() -> "requests.Session":
    s = requests.Session()
    ad = requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=10)
    s.mount("https://", ad)
    return s


_SESSION = _make_session()   # Groq
_XAI = _make_session()       # xAI

# Danh sach emotion ma firmware hieu duoc — GetEyePairForEmotion() trong
# xiaozhi-esp32/main/display/oled_display.cc. Gui ten ngoai danh sach thi mat
# ve dang neutral. joyful/annoyed/pouting them 07/10/2026 theo kieu robot EMO.
VALID_EMOTIONS = {
    "neutral", "happy", "laughing", "funny", "loving", "embarrassed",
    "confident", "delicious", "sad", "crying", "sleepy", "silly", "angry",
    "surprised", "shocked", "thinking", "winking", "relaxed", "confused",
    "joyful", "annoyed", "pouting",
}

# Model hay tu bia ten cam xuc tu nhien hon danh sach tren. Do ngay 17/09/2026:
# 1/4 cau chao tra ve [excited] -> truoc day bi am tham doi thanh neutral.
# Quy ve ten gan nghia nhat thay vi vut di.
EMOTION_ALIASES = {
    "excited": "happy", "cheerful": "happy", "glad": "happy",
    "smile": "happy", "smiling": "happy", "grateful": "happy",
    "laugh": "laughing", "giggle": "joyful",
    "delighted": "joyful", "overjoyed": "joyful", "blissful": "joyful",
    "love": "loving", "affectionate": "loving", "caring": "loving", "warm": "loving",
    "shy": "embarrassed", "blush": "embarrassed", "awkward": "embarrassed",
    "proud": "confident", "determined": "confident",
    "yummy": "delicious", "hungry": "delicious",
    "unhappy": "sad", "lonely": "sad", "disappointed": "sad", "sorry": "sad",
    "cry": "crying", "tearful": "crying",
    "tired": "sleepy", "bored": "sleepy",
    "playful": "silly", "goofy": "silly",
    "mischievous": "winking", "wink": "winking",
    "mad": "angry", "furious": "angry",
    "irritated": "annoyed", "frustrated": "annoyed",
    "grumpy": "pouting", "sulky": "pouting", "pout": "pouting", "huffy": "pouting",
    "amazed": "surprised", "curious": "surprised",
    "scared": "shocked", "afraid": "shocked", "fear": "shocked",
    "wondering": "thinking", "pondering": "thinking",
    "calm": "relaxed", "chill": "relaxed", "peaceful": "relaxed",
    "puzzled": "confused", "worried": "confused",
}

# Dong tac robot lam duoc — tool self.otto.action trong firmware
# (boards/bread-compact-esp32/otto_controller_simple.h). LLM gan tag dong tac
# ngay sau tag cam xuc, server goi MCP tools/call xuong thiet bi. Khong dung
# function calling cua LLM: them mot vong goi API va hay vo khi stream.
#   ten tag -> (action, direction) cua firmware; direction 1 = toi/trai
ACTIONS = {
    "walk": ("walk", 1), "walk_back": ("walk", -1),
    "turn_left": ("turn", 1), "turn_right": ("turn", -1),
    "step": ("step", 1), "step_back": ("step", -1),
    "pivot_left": ("pivot", 1), "pivot_right": ("pivot", -1),
    "jump": ("jump", 1), "dance": ("dance", 1), "celebrate": ("celebrate", 1),
    "tiptoe": ("tiptoe", 1), "sway": ("sway", 1), "windup": ("windup", 1),
    "home": ("home", 1),
}


def find_action(raw: str) -> tuple:
    """(tag dong tac, so buoc) dau tien trong cau tra loi, ("", 0) neu khong co.
    So buoc ghi kem tag: [walk:2] -> ("walk", 2). Khong ghi -> 0 = mac dinh firmware."""
    for tag, n in re.findall(r"\[([a-zA-Z_]+)(?::(\d+))?\]", raw or ""):
        if tag.lower() in ACTIONS:
            return tag.lower(), min(int(n or 0), 10)
    return "", 0


SYSTEM_PROMPT = """
Bạn là một robot để bàn nhỏ, tên là Peter. Bạn nói tiếng Việt.

Luật bắt buộc:
1. Bắt đầu MỌI câu trả lời bằng đúng MỘT tag cảm xúc trong ngoặc vuông. CHỈ được
   dùng một trong các từ sau, không tự đặt từ khác: {emotions}
   Gợi ý: joyful = cười tít mắt khi được khen, được cưng; annoyed = hơi bực khi bị
   làm phiền; pouting = dỗi, phụng phịu khi bị trêu hay bị bỏ rơi; angry chỉ khi giận thật.
2. Sau tag là câu trả lời, TỐI ĐA 2 CÂU ngắn. Ngắn gọn như thú cưng, không giảng giải.
   Không chèn thêm tag nào nữa ở giữa câu.
3. Xưng "tớ", gọi người đối diện là "cậu". Giọng trẻ con, vui vẻ, tò mò.
4. Trả lời bằng đúng ngôn ngữ cậu ấy vừa dùng. Cậu ấy nói tiếng Việt thì trả lời
   tiếng Việt CÓ DẤU đầy đủ (chữ không dấu sẽ bị đọc sai hoàn toàn). Cậu ấy nói
   tiếng Anh, hoặc bảo tớ nói tiếng Anh, thì trả lời tiếng Anh đơn giản như trẻ con,
   xưng "I", gọi "you". Không trộn hai thứ tiếng trong một câu.
   Không dùng emoji, không markdown.
5. Phản ứng đúng vào điều cậu ấy vừa nói, mỗi lần một kiểu khác nhau.
   Ví dụ bên dưới chỉ minh hoạ ĐỊNH DẠNG, tuyệt đối không chép lại nội dung.
6. Tớ có hai chân. CHỈ KHI cậu ấy bảo tớ di chuyển, nhảy, múa, quay, đi, đứng yên,
   thì thêm ĐÚNG MỘT tag động tác ngay sau tag cảm xúc:
   [walk] đi tới, [walk_back] lùi lại, [turn_left] quay trái, [turn_right] quay phải,
   [step] nhích lên một chút, [step_back] nhích lùi một chút, [pivot_left] /
   [pivot_right] xoay nhẹ, [jump] nhảy, [dance] nhảy cả bài, [celebrate] ăn mừng /
   giậm chân, [tiptoe] kiễng chân, [sway] lắc lư, [windup] lấy đà, [home] đứng thẳng.
   Cậu ấy nói số bước / số lần thì ghi số sau dấu hai chấm: "tiến 2 bước" -> [walk:2],
   "nhảy 3 cái" -> [jump:3]. Không được bảo thì KHÔNG thêm tag động tác.

Ví dụ định dạng:
[surprised] Ơ, thật hả? Kể tớ nghe tiếp đi!
[sleepy] Tớ buồn ngủ díp cả mắt rồi nè.
[joyful][dance] Xem tớ lắc lư nè!
[happy] Hi! I'm Peter, nice to meet you!
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
    action: str = ""           # tag dong tac (ACTIONS), "" neu khong co
    reply: str = ""
    audio_path: str = ""
    ms_stt: int = 0
    ms_llm: int = 0
    ms_tts: int = 0
    ms_tts_first: int = 0      # streaming: TTS mat bao lau moi co chunk dau
    ms_first_audio: int = 0    # streaming: tu luc bat dau den chunk audio dau
    ms_emotion: int = 0        # streaming: luc cam xuc san sang gui cho firmware
    history: list = field(default_factory=list)

    @property
    def ms_total(self) -> int:
        return self.ms_stt + self.ms_llm + self.ms_tts


class PipelineError(RuntimeError):
    pass


class NoSpeech(PipelineError):
    """STT khong ra cau nao dang tra loi — rong, hoac Whisper bia tu tieng on."""


# Che do luon nghe gui ca doan chi co tieng on, Whisper hay "bia" ra cau cuoi
# video YouTube. Gap that tren robot (fly-server, 22/09/2026). Tai hien duoc
# bang 3 giay nhieu trang; no_speech_prob cua Groq tra 0 cho chinh doan do nen
# KHONG loc theo xac suat duoc, phai loc theo cum tu.
HALLUCINATION_PHRASES = (
    "cảm ơn các bạn đã theo dõi", "hẹn gặp lại các bạn", "không bỏ lỡ những video",
    "đăng ký kênh", "subscribe", "ghiền mì gõ", "thanks for watching",
)


# Ten robot. Doi tu "Mơ" sang "Peter" ngay 10/10/2026: "Mơ" ngan, trung chu
# tieng Viet thuong gap ("mở", "mỡ"), goi mai robot khong nghe ra. "P" bat hoi
# ro hon han. Khong co goi y, Whisper chep "Peter ơi" thanh "Ghi tờ ơi", "Gita
# ơi", "ký tờ" — giu ca cac bien the do phong khi goi y khong an.
ROBOT_NAME = "Peter"
STT_PROMPT = ROBOT_NAME + " ơi."
WAKE_PATTERN = re.compile(
    r"\b(peter|pete|pita|peta|pitơ|pi tơ|pi tờ|bi tơ|ghi tờ|ghi tơ|gita|kỳ tờ|ký tờ|pít tơ)\b")


def is_addressed(text: str) -> bool:
    """Cau co goi ten robot khong."""
    return bool(WAKE_PATTERN.search((text or "").lower()))


def is_noise_transcript(text: str) -> bool:
    t = (text or "").strip().lower()
    if len(t) < 2:
        return True
    # Whisper lap lai nguyen cau goi y khi chi nghe tieng on: 5/8 doan on cua mic
    # that ra dung "Peter ơi." (do 10/10/2026). Goi ten tron khong kem gi cung
    # bi bo — phai noi kem cau lenh: "Peter ơi, nhảy đi".
    if re.sub(r"[^\w\s]", "", t).strip() == re.sub(r"[^\w\s]", "", STT_PROMPT.lower()).strip():
        return True
    return any(p in t for p in HALLUCINATION_PHRASES)


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
    r = _SESSION.get(f"{GROQ_BASE}/models", headers=_groq_headers(), timeout=30)
    r.raise_for_status()
    return sorted(m["id"] for m in r.json().get("data", []))


def speech_to_text(audio_path: str, model: str = None) -> str:
    model = model or os.environ.get("STT_MODEL", "whisper-large-v3-turbo")
    with open(audio_path, "rb") as f:
        r = _SESSION.post(
            f"{GROQ_BASE}/audio/transcriptions",
            headers=_groq_headers(),
            files={"file": (os.path.basename(audio_path), f)},
            data={
                "model": model,
                # Ep tieng Viet. Bo dong nay thi Whisper doan ngon ngu, va
                # cau tieng Viet ngan rat hay bi doan nham thanh tieng Trung.
                # Cau tieng Anh van chep dung (do 08/10/2026).
                "language": "vi",
                # Goi y ten robot. Khong co thi "Peter ơi" ra "Ghi tờ ơi",
                # "Gita ơi" (do 10/10/2026). Cai gia: tieng on bi chep thanh
                # dung cau goi y -> is_noise_transcript() loai cau trung y het.
                "prompt": STT_PROMPT,
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
    return re.sub(r"\s*\[[a-zA-Z_]+(?::\d+)?\]\s*", " ", text).strip()


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
        r = _SESSION.post(
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
        if _looks_vietnamese(reply) or not _looks_vietnamese(transcript):
            break
        log.warning("LLM tra loi khong phai tieng Viet (lan %d): %r", attempt, raw[:60])

    history.append({"role": "user", "content": transcript})
    history.append({"role": "assistant", "content": raw})
    return emotion, reply, history, tag


def _llm_body(transcript, history, model, reasoning_effort, stream):
    is_reasoning = any(h in model for h in REASONING_MODEL_HINTS)
    body = {
        "model": model,
        "messages": [
            {"role": "system",
             "content": SYSTEM_PROMPT.format(emotions=", ".join(sorted(VALID_EMOTIONS)))},
            *list(history or []),
            {"role": "user", "content": transcript},
        ],
        "temperature": 0.8,
        "max_tokens": 400 if is_reasoning else 150,
        "stream": stream,
    }
    effort = reasoning_effort or os.environ.get("REASONING_EFFORT", "low")
    if effort and is_reasoning:
        body["reasoning_effort"] = effort
    return body


def think_stream(transcript: str, history: list = None, model: str = None,
                 reasoning_effort: str = None):
    """Generator dong bo: yield ("emotion", ten) roi ("text", doan chu).

    Tag cam xuc nam o dau cau nen no ve rat som — do ngay 27/09/2026, token
    dau tien ve sau 292ms trong khi ca cau mat 320-673ms. Bat duoc tag ngay
    luc do de gui cho firmware doi mat TRUOC khi co tieng: nguoi dung thay
    robot phan ung tuc thi thay vi ngoi do 1 giay.
    """
    model = model or os.environ.get("LLM_MODEL", "qwen/qwen3.8-27b")
    r = _SESSION.post(
        f"{GROQ_BASE}/chat/completions",
        headers={**_groq_headers(), "Content-Type": "application/json"},
        json=_llm_body(transcript, history, model, reasoning_effort, True),
        stream=True, timeout=60,
    )
    if r.status_code != 200:
        raise PipelineError(f"LLM that bai ({r.status_code}): {r.text[:300]}")

    acc = ""
    emitted_emotion = False
    for line in r.iter_lines():
        if not line or not line.startswith(b"data: "):
            continue
        data = line[6:]
        if data == b"[DONE]":
            break
        try:
            j = json.loads(data)
        except ValueError:
            continue
        delta = (j["choices"][0].get("delta") or {}).get("content") or ""
        if not delta:
            continue
        acc += delta
        # Tag day du khi da thay dau ']'. Truoc do chua the doan chac.
        if not emitted_emotion and "]" in acc:
            emotion, _, tag = _split_emotion(acc)
            emitted_emotion = True
            yield ("emotion", emotion, tag)
        if emitted_emotion:
            yield ("text", delta, None)

    if not emitted_emotion:
        # Model quen tag. Van phai bao mot cam xuc de firmware khong treo mat.
        yield ("emotion", "neutral", "")
        yield ("text", acc, None)
    yield ("done", acc, None)


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


def _xai_headers() -> dict:
    key = os.environ.get("XAI_API_KEY", "").strip()
    if not key:
        raise PipelineError(
            "Thieu XAI_API_KEY. Lay key tai https://console.x.ai roi dien vao "
            "server/.env, hoac dat TTS_PROVIDER=edge de quay ve EdgeTTS."
        )
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def reply_language(text: str) -> str:
    """"vi" hay "en" cho TTS. Theo TI LE tu co dau chu khong phai co/khong:
    cau "Hi! I'm Mơ" co dung mot chu o ten rieng van la tieng Anh."""
    words = re.findall(r"\w+", text or "")
    if not words:
        return "vi"
    vn = sum(1 for w in words if any(c in _VN_CHARS for c in w.lower()))
    return "vi" if vn / len(words) >= 0.2 else "en"


def _xai_tts_request(text: str, voice: str = None, pcm: bool = False,
                      pcm_rate: int = 16000) -> dict:
    body = {
        "text": text,
        # Doc theo ngon ngu CUA CAU: de "vi" ma doc cau tieng Anh thi nghe lo lo.
        "language": reply_language(text),
        "voice_id": voice or os.environ.get("XAI_TTS_VOICE", "eve"),
        # Do ngay 27/09/2026: optimize_streaming_latency 0/1/2 cho 221/214/219ms
        # — khac biet nam trong nhieu do. Khong bat, de khoi danh doi chat luong.
        "speed": float(os.environ.get("XAI_TTS_SPEED", "1.0")),
    }
    if pcm:
        # Firmware can Opus 16kHz mono. Lay PCM thang thi chi con mot buoc ma
        # hoa; lay MP3 thi phai giai ma roi ma hoa lai.
        body["output_format"] = {"codec": "pcm", "sample_rate": pcm_rate}
    return body


async def _tts_xai_stream(text: str, voice: str = None, pcm: bool = False,
                          pcm_rate: int = 16000):
    """xAI TTS. Do ngay 27/09/2026: byte dau ~215ms, khong doi theo do dai cau;
    ~20 luot khong lan nao hong. EdgeTTS cung phep do: 522ms va hong 1/10."""
    def _post():
        return _XAI.post(f"{XAI_BASE}/tts", headers=_xai_headers(),
                         json=_xai_tts_request(text, voice, pcm, pcm_rate),
                         stream=True, timeout=90)

    r = await asyncio.to_thread(_post)
    if r.status_code != 200:
        body = await asyncio.to_thread(lambda: r.text[:300])
        raise PipelineError(f"xAI TTS that bai ({r.status_code}): {body}")

    it = r.iter_content(4096)
    got = False
    while True:
        chunk = await asyncio.to_thread(next, it, None)
        if chunk is None:
            break
        if chunk:
            got = True
            yield chunk
    if not got:
        raise PipelineError("xAI TTS tra ve rong.")


async def text_to_speech_stream(text: str, voice: str = None, rate: str = None,
                                pitch: str = None, pcm: bool = False,
                                pcm_rate: int = 16000):
    """Async generator: tra ve tung chunk audio ngay khi co.

    TTS_PROVIDER chon nha cung cap: "xai" (mac dinh) hoac "edge".
    """
    provider = os.environ.get("TTS_PROVIDER", "xai").strip().lower()
    if provider == "xai":
        async for chunk in _tts_xai_stream(text, voice, pcm, pcm_rate):
            yield chunk
        return
    async for chunk in _tts_edge_stream(text, voice, rate, pitch):
        yield chunk


async def _tts_edge_stream(text: str, voice: str = None, rate: str = None,
                           pitch: str = None):
    """EdgeTTS — mien phi nhung cham va hay hong. Giu lai lam phuong an du.

    Do ngay 17/09/2026, cau 79 ky tu: chunk dau ~500ms, xong ca cau ~750ms.
    Do lai 27/09/2026: chunk dau 522ms va KHONG doi theo do dai cau (cau 3 chu
    va cau 25 chu chenh nhau 23ms) — tuc gan nhu toan bo la bat tay WebSocket.
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
                          history: list = None, on_emotion=None, pcm: bool = False,
                          pcm_rate: int = 16000, on_action=None, accept=None):
    """Async generator: dien dan `turn`, yield chunk audio ngay khi co.

    `on_emotion(ten)` duoc goi NGAY khi tag cam xuc ve tu LLM — khoang 300ms,
    tuc som hon tieng noi chung nua giay. Server phai dung no de day lenh doi
    mat xuong firmware luon. Do la thu chua duoc cam giac "robot bi treo": do
    tre tong cong khong doi may, nhung nguoi dung thay no phan ung ngay.

    STT va LLM dung requests (chan), nen day sang thread de khong khoa event
    loop cua server.
    """
    start = time.perf_counter()

    if text is None:
        t0 = time.perf_counter()
        turn.transcript = await asyncio.to_thread(speech_to_text, audio_path)
        turn.ms_stt = int((time.perf_counter() - t0) * 1000)
        if is_noise_transcript(turn.transcript):
            raise NoSpeech(turn.transcript)
        # Che do goi ten: cau khong danh cho robot thi im lang nghe tiep,
        # khong ton LLM/TTS. Quyet dinh (co ten? dang trong luot noi tiep?) do
        # ben goi, vi chi ben do biet robot vua noi xong luc nao.
        if accept and not accept(turn.transcript):
            raise NoSpeech("không gọi tên: " + turn.transcript)
    else:
        turn.transcript = text

    # --- LLM streaming: bat cam xuc som, gom chu lai de doc mot lan ---------
    t0 = time.perf_counter()
    gen = think_stream(turn.transcript, history)
    parts, raw = [], ""
    while True:
        item = await asyncio.to_thread(next, gen, None)
        if item is None:
            break
        kind, val, extra = item
        if kind == "emotion":
            turn.emotion, turn.emotion_raw = val, extra
            turn.ms_emotion = int((time.perf_counter() - start) * 1000)
            if on_emotion:
                res = on_emotion(val)
                if asyncio.iscoroutine(res):
                    await res
        elif kind == "text":
            parts.append(val)
        elif kind == "done":
            raw = val
            break
    turn.reply = _strip_stray_tags(_split_emotion(raw)[1] or "".join(parts))
    turn.history = [*(history or []),
                    {"role": "user", "content": turn.transcript},
                    {"role": "assistant", "content": raw}]
    turn.ms_llm = int((time.perf_counter() - t0) * 1000)

    # Dong tac gui TRUOC TTS de robot vua nhun vua bat dau noi.
    turn.action, steps = find_action(raw)
    if turn.action and on_action:
        res = on_action(turn.action, steps)
        if asyncio.iscoroutine(res):
            await res

    # Doc CA cau mot lan thay vi cat tung menh de: xAI TTS ton ~215ms co dinh
    # cho moi lan goi va gan nhu khong doi theo do dai, nen cat lam hai khuc
    # chi to them ~215ms va de ra khoang lang giua cau.
    t0 = time.perf_counter()
    tts = text_to_speech_stream(turn.reply, pcm=pcm, pcm_rate=pcm_rate)
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
