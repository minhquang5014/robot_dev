#!/bin/sh
# Tạo data/.config.yaml trước khi chạy server (xiaozhi-server bắt buộc có file này).
# Ưu tiên: file đã có (volume) > secret XIAOZHI_CONFIG > cấu hình mẫu + key từ secret GROQ_API_KEY.
set -e
mkdir -p data tmp
if [ ! -s data/.config.yaml ]; then
  if [ -n "$XIAOZHI_CONFIG" ]; then
    printf '%s\n' "$XIAOZHI_CONFIG" > data/.config.yaml
    echo "[entrypoint] data/.config.yaml tạo từ secret XIAOZHI_CONFIG"
  else
    sed -e "s|__GROQ_API_KEY__|${GROQ_API_KEY:-missing-groq-key}|" \
        /opt/fly-config.example.yaml > data/.config.yaml
    [ -n "$GROQ_API_KEY" ] || echo "[entrypoint] CẢNH BÁO: thiếu secret GROQ_API_KEY"
    echo "[entrypoint] data/.config.yaml tạo từ cấu hình mẫu + GROQ_API_KEY"
  fi
fi
exec "$@"
