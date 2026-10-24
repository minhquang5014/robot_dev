"""
Thu duong ong voice -> voice ma KHONG can ESP32.

    python server/test_voice.py --record 4        # thu am tu micro may tinh
    python server/test_voice.py --in cauhoi.wav   # dung file co san
    python server/test_voice.py --text "Chao cau" # bo qua STT, thu nhanh LLM+TTS
    python server/test_voice.py --chat            # noi chuyen lien tuc, co nho ngu canh
    python server/test_voice.py --models          # xem Groq con nhung model nao

    Them --stream vao --text / --in / --record / --chat de chay TTS streaming
    va do thoi diem co tieng dau tien (cai nguoi nghe thuc su cam nhan).

Muc dich: xac nhan API key chay duoc, nghe thu giong tieng Viet, va do do tre
that truoc khi dung server WebSocket.
"""

import argparse
import asyncio
import io
import logging
import os
import sys
import time

# Console Windows mac dinh la cp1252, in tieng Viet co dau la UnicodeEncodeError
# ngay giua luc chay. Ep UTF-8 truoc khi lam bat cu viec gi khac.
for _s in ("stdout", "stderr"):
    _stream = getattr(sys, _s)
    if hasattr(_stream, "buffer"):
        setattr(sys, _s, io.TextIOWrapper(_stream.buffer, encoding="utf-8",
                                          errors="replace", line_buffering=True))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
import pipeline

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")


def record(seconds: float, path: str, rate: int = 16000) -> str:
    """Thu am tu micro may tinh, 16kHz mono — dung dinh dang ESP32 se gui."""
    try:
        import numpy as np
        import sounddevice as sd
    except ImportError:
        sys.exit("Can `pip install sounddevice numpy` de dung --record.")
    import wave

    print(f"Đang thu {seconds}s... nói đi!")
    audio = sd.rec(int(seconds * rate), samplerate=rate, channels=1, dtype=np.int16)
    sd.wait()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(audio.tobytes())
    print(f"Đã lưu {path}")
    return path


def play(path: str):
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            os.system(f'afplay "{path}"')
        else:
            os.system(f'command -v mpv >/dev/null && mpv --really-quiet "{path}"')
    except Exception as e:
        print(f"(khong tu phat duoc, mo tay file {path}: {e})")


def _mark(ms: int) -> str:
    # Duoi 1500ms thi con giong sinh vat; tren 2500ms nghe nhu treo may.
    return "tốt" if ms < 1500 else ("chậm" if ms > 2500 else "tạm được")


def report(turn: pipeline.Turn):
    print()
    print(f"  Nghe được : {turn.transcript}")
    emo = turn.emotion
    if turn.emotion_raw and turn.emotion_raw != turn.emotion:
        emo += f"   (LLM viết [{turn.emotion_raw}])"
    print(f"  Cảm xúc   : {emo}")
    print(f"  Trả lời   : {turn.reply}")
    print()
    print(f"  STT   {turn.ms_stt:>6} ms")
    print(f"  LLM   {turn.ms_llm:>6} ms")
    if turn.ms_first_audio:
        print(f"  TTS   {turn.ms_tts:>6} ms   (chunk đầu sau {turn.ms_tts_first} ms)")
        print(f"  {'-' * 14}")
        print(f"  TIẾNG ĐẦU TIÊN {turn.ms_first_audio:>6} ms   ({_mark(turn.ms_first_audio)})")
        print(f"  XONG CẢ CÂU    {turn.ms_total:>6} ms")
    else:
        print(f"  TTS   {turn.ms_tts:>6} ms")
        print(f"  {'-' * 14}")
        print(f"  TỔNG  {turn.ms_total:>6} ms   ({_mark(turn.ms_total)})")
    print()


def run_stream(out_path: str, audio_path: str = None, text: str = None,
               history: list = None) -> pipeline.Turn:
    """Chay luot streaming, ghi chunk MP3 ra file ngay khi toi.

    Tren Mac chi do thoi gian roi phat file sau. Phat that su tung chunk la
    viec cua ESP32 (qua Opus), khong phai cua script nay.
    """
    turn = pipeline.Turn()

    async def go():
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with open(out_path, "wb") as f:
            async for chunk in pipeline.run_turn_stream(turn, audio_path=audio_path,
                                                        text=text, history=history):
                f.write(chunk)

    asyncio.run(go())
    turn.audio_path = out_path
    return turn


def main():
    p = argparse.ArgumentParser(description="Thu pipeline voice->voice cho robot")
    p.add_argument("--in", dest="infile", help="File am thanh dau vao (wav/mp3/m4a)")
    p.add_argument("--record", type=float, metavar="GIAY", help="Thu am tu micro")
    p.add_argument("--text", help="Bo qua STT, dua thang cau nay cho LLM")
    p.add_argument("--chat", action="store_true", help="Noi chuyen lien tuc, nho ngu canh")
    p.add_argument("--models", action="store_true", help="Liet ke model Groq con song")
    p.add_argument("--no-play", action="store_true", help="Khong tu phat cau tra loi")
    p.add_argument("--stream", action="store_true", help="TTS streaming, do tieng dau tien")
    p.add_argument("-v", "--verbose", action="store_true", help="In ca log INFO (quy doi cam xuc)")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="  [%(levelname)s] %(message)s")
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    os.makedirs(OUT_DIR, exist_ok=True)

    try:
        if args.models:
            for m in pipeline.list_models():
                print(m)
            return

        # Nhanh nhanh nhat: bo qua STT.
        if args.text:
            out = os.path.join(OUT_DIR, "reply.mp3")
            if args.stream:
                turn = run_stream(out, text=args.text)
            else:
                turn = pipeline.Turn(transcript=args.text)
                t0 = time.perf_counter()
                turn.emotion, turn.reply, _, turn.emotion_raw = pipeline.think(args.text)
                turn.ms_llm = int((time.perf_counter() - t0) * 1000)
                t0 = time.perf_counter()
                pipeline.text_to_speech(turn.reply, out)
                turn.ms_tts = int((time.perf_counter() - t0) * 1000)
            report(turn)
            if not args.no_play:
                play(out)
            return

        if args.chat:
            history = []
            n = 0
            print("Chế độ hội thoại. Ctrl+C để thoát.\n")
            while True:
                input("Enter để bắt đầu thu âm 4 giây...")
                wav = record(4, os.path.join(OUT_DIR, "in.wav"))
                n += 1
                out = os.path.join(OUT_DIR, f"reply_{n}.mp3")
                if args.stream:
                    turn = run_stream(out, audio_path=wav, history=history)
                else:
                    turn = pipeline.run_turn(wav, out, history)
                history = turn.history
                report(turn)
                if not args.no_play:
                    play(turn.audio_path)

        src = args.infile
        if args.record:
            src = record(args.record, os.path.join(OUT_DIR, "in.wav"))
        if not src:
            p.error("Can mot trong: --in, --record, --text, --chat hoac --models")
        if not os.path.exists(src):
            sys.exit(f"Không thấy file {src}")

        out = os.path.join(OUT_DIR, "reply.mp3")
        if args.stream:
            turn = run_stream(out, audio_path=src)
        else:
            turn = pipeline.run_turn(src, out)
        report(turn)
        if not args.no_play:
            play(turn.audio_path)

    except pipeline.PipelineError as e:
        sys.exit(f"\nLoi: {e}")
    except KeyboardInterrupt:
        print("\nThoát.")


if __name__ == "__main__":
    main()
