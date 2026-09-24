# Server hội thoại cho robot = xiaozhi-esp32-server (bản cộng đồng) + bản vá của repo này.
# Build: chạy `fly deploy` trong thư mục fly-server/ (xem README.md).

# Bước 1: lấy mã nguồn gốc ở đúng commit đã test, rồi áp bản vá
FROM debian:bookworm-slim AS src
ARG UPSTREAM_COMMIT=788f5301fdd60cc3a8ef74025bfeece9b82b94ce
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates patch && \
    rm -rf /var/lib/apt/lists/*
RUN git clone --filter=blob:none https://github.com/xinnan-tech/xiaozhi-esp32-server.git /src && \
    git -C /src checkout ${UPSTREAM_COMMIT}
COPY xiaozhi-server.patch /tmp/
RUN cd /src && patch -p1 < /tmp/xiaozhi-server.patch

# Bước 2: image chạy thật, dựa trên image nền có sẵn Python + thư viện
FROM ghcr.io/xinnan-tech/xiaozhi-esp32-server:server-base
COPY --from=src /src/main/xiaozhi-server .
COPY config.example.yaml /opt/fly-config.example.yaml
COPY entrypoint.sh /opt/fly-entrypoint.sh
RUN chmod +x /opt/fly-entrypoint.sh

ENTRYPOINT ["/opt/fly-entrypoint.sh"]
CMD ["python", "app.py"]
