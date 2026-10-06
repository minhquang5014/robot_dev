# Server hội thoại cho robot: xiaozhi_server.py (Groq STT + LLM, xAI TTS).
# Deploy: `fly deploy` trong thư mục server/ (xem README.md, mục Deploy lên Fly.io).
FROM python:3.12-slim

WORKDIR /app
# Wheel của av, numpy, webrtcvad-wheels đã kèm sẵn libopus/ffmpeg — không cần apt.
# sounddevice chỉ dùng cho test_voice.py --record trên máy cá nhân, bỏ qua ở đây.
COPY requirements.txt .
RUN grep -v '^sounddevice' requirements.txt > /tmp/req.txt && \
    pip install --no-cache-dir -r /tmp/req.txt

COPY audio.py pipeline.py xiaozhi_server.py ./

ENV PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=8000
EXPOSE 8000
CMD ["python", "xiaozhi_server.py"]
