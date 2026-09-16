"""
Thu duong ong voice -> voice ma KHONG can ESP32.

    python server/test_voice.py --record 4        # thu am tu micro may tinh
    python server/test_voice.py --in cauhoi.wav   # dung file co san
    python server/test_voice.py --text "Chao cau" # bo qua STT, thu nhanh LLM+TTS
    python server/test_voice.py --chat            # noi chuyen lien tuc, co nho ngu canh
    python server/test_voice.py --models          # xem Groq con nhung model nao

Muc dich: xac nhan API key chay duoc, nghe thu giong tieng Viet, va do do tre
that truoc khi dung server WebSocket.
"""

import argparse
import io
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


def report(turn: pipeline.Turn):
    print()
    print(f"  Nghe được : {turn.transcript}")
    print(f"  Cảm xúc   : {turn.emotion}")
    print(f"  Trả lời   : {turn.reply}")
    print()
    print(f"  STT   {turn.ms_stt:>6} ms")
    print(f"  LLM   {turn.ms_llm:>6} ms")
    print(f"  TTS   {turn.ms_tts:>6} ms")
    print(f"  {'-' * 14}")
    # Duoi 1500ms thi con giong sinh vat; tren 2500ms nghe nhu treo may.
    mark = "tốt" if turn.ms_total < 1500 else ("chậm" if turn.ms_total > 2500 else "tạm được")
    print(f"  TỔNG  {turn.ms_total:>6} ms   ({mark})")
    print()


def main():
    p = argparse.ArgumentParser(description="Thu pipeline voice->voice cho robot")
    p.add_argument("--in", dest="infile", help="File am thanh dau vao (wav/mp3/m4a)")
    p.add_argument("--record", type=float, metavar="GIAY", help="Thu am tu micro")
    p.add_argument("--text", help="Bo qua STT, dua thang cau nay cho LLM")
    p.add_argument("--chat", action="store_true", help="Noi chuyen lien tuc, nho ngu canh")
    p.add_argument("--models", action="store_true", help="Liet ke model Groq con song")
    p.add_argument("--no-play", action="store_true", help="Khong tu phat cau tra loi")
    args = p.parse_args()

    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    os.makedirs(OUT_DIR, exist_ok=True)

    try:
        if args.models:
            for m in pipeline.list_models():
                print(m)
            return

        # Nhanh nhanh nhat: bo qua STT.
        if args.text:
            t0 = time.perf_counter()
            emotion, reply, _ = pipeline.think(args.text)
            ms_llm = int((time.perf_counter() - t0) * 1000)
            out = os.path.join(OUT_DIR, "reply.mp3")
            t0 = time.perf_counter()
            pipeline.text_to_speech(reply, out)
            ms_tts = int((time.perf_counter() - t0) * 1000)
            report(pipeline.Turn(transcript=args.text, emotion=emotion, reply=reply,
                                 ms_llm=ms_llm, ms_tts=ms_tts))
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
                turn = pipeline.run_turn(wav, os.path.join(OUT_DIR, f"reply_{n}.mp3"), history)
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

        turn = pipeline.run_turn(src, os.path.join(OUT_DIR, "reply.mp3"))
        report(turn)
        if not args.no_play:
            play(turn.audio_path)

    except pipeline.PipelineError as e:
        sys.exit(f"\nLoi: {e}")
    except KeyboardInterrupt:
        print("\nThoát.")


if __name__ == "__main__":
    main()
