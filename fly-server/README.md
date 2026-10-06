# fly-server — server hội thoại chạy trên Fly.io

Dùng [xiaozhi-esp32-server](https://github.com/xinnan-tech/xiaozhi-esp32-server) (bản
cộng đồng, đủ Opus + VAD + ASR + LLM + TTS + MCP) thay vì tự viết, kèm một bản vá nhỏ.
Đã chạy thật với ESP32 trong repo này (firmware 2.5.0, không PSRAM) ngày 22/09/2026:
OTA → WebSocket → nghe → trả lời tiếng Việt.

```
ESP32 ──OTA https──> xiaozhi-esp32-server.fly.dev/xiaozhi/ota/
      ──WebSocket──> wss://xiaozhi-esp32-server.fly.dev:8443/xiaozhi/v1/
                     VAD Silero → Groq Whisper → Groq qwen3.8-27b → EdgeTTS (vi-VN-HoaiMyNeural)
```

| File | Việc |
|---|---|
| `Dockerfile` | Clone upstream ở commit `788f5301` (đã test), áp `xiaozhi-server.patch`, dựng trên image nền `server-base` |
| `xiaozhi-server.patch` | Các sửa đổi với upstream (xem dưới) |
| `config.example.yaml` | Cấu hình ghi đè: tiếng Việt, Groq, luôn nghe, lọc ảo giác. **Không chứa key** |
| `entrypoint.sh` | Tạo `data/.config.yaml` lúc khởi động, thay `__GROQ_API_KEY__` bằng Fly secret |
| `fly.toml` | 2 cổng: 443 → 8003 (OTA/vision), 8443 → 8000 (WebSocket). 1GB RAM, tự dừng khi không có kết nối |

## Deploy

```bash
cd fly-server
fly launch --no-deploy --copy-config      # lần đầu; đổi `app` trong fly.toml nếu tên đã có người dùng
fly secrets set GROQ_API_KEY=gsk_...
fly deploy
curl https://<app>.fly.dev/xiaozhi/ota/   # phải thấy "OTA接口运行正常" + địa chỉ wss
```

Đổi tên app thì sửa cả `websocket` / `vision_explain` trong `config.example.yaml` và
`CONFIG_OTA_URL` trong `xiaozhi-esp32/sdkconfig`.

Chỉ đổi tính cách / giọng / model: sửa `config.example.yaml` rồi `fly deploy`,
**không cần nạp lại ESP32**.

## Bản vá (`xiaozhi-server.patch`)

1. **ASR OpenAI-compatible nhận thêm tham số** (`core/providers/asr/openai.py`):
   - `language: vi` — ép tiếng Việt, câu ngắn không bị đoán nhầm ngôn ngữ.
   - `prompt` — gợi ý từ vựng cho Whisper (tên robot, "Alo").
   - `hallucination_phrases` — bỏ các câu Whisper bịa ra từ tiếng ồn.
2. **`enable_exit_intent: false`** (`plugin_executor.py`) — tắt công cụ "thoát hội thoại"
   mà upstream luôn nạp. Xem lỗi 2 bên dưới.

## Luôn nghe

Không có PSRAM thì không có wake word, nên firmware trong repo này thêm
`CONFIG_ALWAYS_LISTENING` (`main/application.cc`): đang rảnh ~5 giây là tự mở hội thoại,
rớt kết nối thì tự nối lại (chờ 5, 10, 20, 40, rồi 60 giây). Bấm BOOT khi đang nghe để
tạm dừng, bấm lại để nghe tiếp. Phía server đặt `close_connection_no_voice_time` = 1 năm
để không tự ngắt khi im lặng.

Cái giá: server chạy liên tục khi robot còn cắm điện, và robot trả lời **mọi** câu nó
nghe được (người khác nói, TV). Không có AEC nên khi robot đang nói thì không nghe.

## Lỗi đã gặp

**1. Whisper bịa câu cuối video YouTube từ tiếng ồn.** Chế độ luôn nghe liên tục gửi
đoạn chỉ có tiếng ồn, Whisper trả về `Cảm ơn các bạn đã theo dõi và hẹn gặp lại.`,
`Hãy subscribe cho kênh Ghiền Mì Gõ Để không bỏ lỡ những video hấp dẫn`. Tái hiện được
bằng file 3 giây nhiễu trắng. `no_speech_prob` của Groq trả **0** cho chính đoạn nhiễu
đó nên **không lọc theo xác suất được** — phải lọc theo cụm từ + nâng ngưỡng VAD
(0.5 → 0.65).

**2. Câu ảo giác "hẹn gặp lại" kích hoạt công cụ thoát.** LLM hiểu là người dùng chào
tạm biệt, gọi `handle_exit_intent`, server đóng kết nối. Câu chào tạm biệt của công cụ
viết cứng tiếng Trung (`再见`) nên EdgeTTS giọng Việt cũng lỗi. Robot nối lại, nghe nhiễu,
lặp lại. Sửa bằng `enable_exit_intent: false`.

**3. Câu đáp đánh thức dựng sẵn là file âm thanh tiếng Trung** (`我在这里哦！`). Tắt bằng
`enable_wakeup_words_response_cache: false`.

**4. `data/.config.yaml` không có trong image** (bị `.gitignore`/`.dockerignore`) → server
crash lúc khởi động, Fly restart 10 lần rồi bỏ. `entrypoint.sh` tạo file này.

## Số đo — 22/09/2026, server Singapore, gọi từ Việt Nam

| Chặng | Đo được |
|---|---|
| LLM `gpt-oss-20b`, token đầu | 0,9–1,3 s |
| LLM `qwen3.8-27b`, token đầu | 0,3 s |
| EdgeTTS, một câu, gọi từ server | **3,7–11 s** |
| EdgeTTS, gọi từ Mac ở Việt Nam | 5–8 s |
| Từ lúc có chữ đến tiếng đầu tiên (5 câu) | 4,5–21 s |
| RAM server rảnh / 10 kết nối | ~145 MB / ~175 MB |

EdgeTTS hôm nay chậm hơn hẳn số đo 0,7 s ngày 17/09 trong `server/README.md` — khớp với
nhận định nó hỏng/chậm **theo đợt**. Đổi LLM sang qwen không làm tổng nhanh hơn vì TTS
chiếm gần hết thời gian. `xiaozhi-esp32-server` dùng EdgeTTS **không streaming**; muốn
nhanh ổn định cần nhà cung cấp TTS chính thức (Azure có cùng giọng HoaiMy, gói miễn phí
500k ký tự/tháng) — chưa làm.

## Chưa kiểm chứng

- Số robot "luôn nghe" chạy cùng lúc trên 1 CPU dùng chung: ước tính 3–5, **chưa đo** bằng
  audio thật (đo 10 kết nối chỉ gửi chữ).
- VLLM `qwen/qwen3.8-27b` cho tính năng nhìn ảnh: chưa thử, board này không có camera.
- Qwen trả lời sai ngày ("thứ Năm 23 tháng 4" vào thứ Ba 22/09) — chưa tìm hiểu biến
  `{{current_time}}` có được thay vào prompt không.
