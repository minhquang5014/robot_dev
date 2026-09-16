# robot_dev — Trợ lý giọng nói xiaozhi trên ESP32

Môi trường làm việc cho ESP32 + mic I2S + khuếch đại I2S, chạy firmware
[xiaozhi-esp32](https://github.com/78/xiaozhi-esp32) (MIT) đã tuỳ chỉnh.

## Phần cứng

| Linh kiện | Chi tiết |
|---|---|
| MCU | ESP32-D0WD-V3, 4MB flash, **không có PSRAM** |
| Mic | INMP441 (I2S) |
| Khuếch đại | MAX98357A (I2S) + loa 4–8Ω |
| Màn hình | OLED SSD1306 128x64 (I2C) |

### Sơ đồ đấu nối

```
INMP441          ESP32          MAX98357A        ESP32
  VDD    ->      3V3              VIN     ->      5V
  GND    ->      GND              GND     ->      GND
  L/R    ->      GND              DIN     ->      GPIO33
  WS     ->      GPIO25           BCLK    ->      GPIO14
  SCK    ->      GPIO26           LRC     ->      GPIO27
  SD     ->      GPIO32           GAIN    ->      để trống (9dB)
                                  SD      ->      để trống
OLED SSD1306     ESP32            +/-     ->      loa 4-8Ω
  VCC    ->      3V3
  GND    ->      GND          Nút BOOT (GPIO0, có sẵn) = bắt đầu/dừng hội thoại
  SDA    ->      GPIO4        GPIO19 = giả lập câu đánh thức
  SCL    ->      GPIO15       GPIO5  = bộ đàm, giữ để nói
```

Tất cả GND chung. **Tránh GPIO12** — chân strapping, quyết định điện áp flash lúc boot.

## Tuỳ chỉnh so với xiaozhi gốc

1. **Kết nối được WiFi ẩn** — `xiaozhi-esp32/components/esp-wifi-connect/wifi_station.cc`

   Bản gốc quét WiFi rồi so khớp theo tên. Mạng ẩn không phát tên trong beacon nên
   không bao giờ khớp, thiết bị kẹt ở `No AP found` vĩnh viễn. Bản vá thêm một
   nhánh dự phòng: khi quét không ra, thử kết nối thẳng từng mạng đã lưu —
   `esp_wifi_connect()` gửi probe request có đích danh, và mạng ẩn **có** trả lời.

   Đặt trong `components/` (không sửa `managed_components/`) để không bị ghi đè
   mỗi lần trình quản lý tải lại dependency.

2. **Giao diện tiếng Việt** — `CONFIG_LANGUAGE_VI_VN=y` trong `sdkconfig`.
   Cả chữ trên màn lẫn giọng đọc. Font mặc định đã phủ đủ 39 ký tự có dấu được dùng.

3. **OLED 128x64** — `CONFIG_OLED_SSD1306_128X64=y` (mặc định của board là 128x32).

## Cài môi trường (macOS, không cần sudo)

```bash
# ESP-IDF v6.1 — xiaozhi yêu cầu >= 6.0.1, KHÔNG chạy trên 5.x
git clone -b v6.1 --recursive --depth 1 --shallow-submodules \
    https://github.com/espressif/esp-idf.git ~/esp/esp-idf
cd ~/esp/esp-idf && ./install.sh esp32

# macOS không kèm cmake/ninja cho ESP-IDF, cài vào venv của nó:
. ~/esp/esp-idf/export.sh && python -m pip install cmake ninja
```

Nếu gặp `CERTIFICATE_VERIFY_FAILED`: bản Python từ python.org thiếu chứng chỉ gốc.
Sửa bằng `python3 -m pip install --user certifi` rồi
`export SSL_CERT_FILE=$(python3 -c "import certifi;print(certifi.where())")`.

Với các sketch Arduino, cần `arduino-cli` + core `esp32:esp32`.

## Build và nạp

```bash
cd xiaozhi-esp32
. ~/esp/esp-idf/export.sh
idf.py set-target esp32      # chỉ lần đầu
idf.py build
idf.py -p /dev/cu.usbserial-XXXX flash monitor
```

Sau khi nạp, thiết bị phát hotspot `Xiaozhi-XXXX`. Nối điện thoại vào, mở
`http://192.168.4.1` để khai báo WiFi (chỉ 2.4GHz). Rồi đăng ký mã hiện trên
màn OLED tại https://xiaozhi.me.

## Script tiện ích (`scripts/`)

Copy vào `~/bin` và thêm vào PATH:

| Lệnh | Việc |
|---|---|
| `xz build \| flash \| mon \| all` | Build/nạp/xem log xiaozhi |
| `esp build \| up \| mon <thư_mục>` | Tương tự cho sketch Arduino |
| `mic-rec [--level] [-o ten.wav]` | Ghi âm từ mic về máy tính, nghe lại kiểm tra |
| `xz-wifi "Tên Mạng"` | Khai báo WiFi cho ESP32 qua hotspot của nó |

Sửa biến `PORT` / `XZ_PORT` / `MIC_PORT` trong script cho khớp cổng máy bạn.

## Sketch kiểm tra phần cứng

- `mic_record/` — đẩy PCM thô qua serial, dùng với `mic-rec` để nghe lại giọng mình
- `xz_audio_test/` — phát bíp 1kHz mỗi 5 giây (test loa) + in mức mic (test mic)

Cả hai đều dùng chân giống xiaozhi nên test xong là biết phần cứng có vấn đề không.

> **Lưu ý khi tự viết code I2S:** phải đặt `.mck_io_num = I2S_PIN_NO_CHANGE`.
> Bỏ trống thì nó mặc định thành GPIO0; kênh I2S thứ hai sẽ báo `mclk config failed`
> và `i2s_set_pin()` **thoát sớm, chưa kịp gán BCLK/LRC/DIN** — loa câm dù phần cứng tốt.

## Máy chủ

### Mặc định: máy chủ chính thức của xiaozhi

Firmware nối ra ngoài theo **hai tầng**:

1. **Kích hoạt và cấp phát** — thiết bị gọi `https://api.tenclass.net/xiaozhi/ota/`,
   địa chỉ viết cứng ở `main/Kconfig.projbuild:5` (sửa qua `CONFIG_OTA_URL`).
   Trang `xiaozhi.me` là nơi bạn đăng nhập để gán thiết bị vào tài khoản; còn
   ESP32 thì nói chuyện với `api.tenclass.net`. Cùng nhà vận hành, khác vai trò.

2. **Hội thoại** — máy chủ ở tầng 1 trả về cấu hình MQTT/WebSocket, firmware lưu
   vào NVS (`main/ota.cc:152-180`). Địa chỉ server hội thoại **không nằm trong code**
   mà do server cấp phát lúc kích hoạt.

> **Về riêng tư:** giọng nói được gửi lên máy chủ của bên vận hành xiaozhi (Trung Quốc)
> để nhận dạng và sinh câu trả lời. ESP32 chỉ thu, nén Opus và truyền đi.
> `api.tenclass.net` cũng là điểm chặn duy nhất — server đó hỏng hoặc chặn IP là
> thiết bị thành cục gạch.

### Tự host

[xiaozhi-esp32-server](https://github.com/xinnan-tech/xiaozhi-esp32-server) nói cùng
giao thức, chạy Docker. Chuyển sang chỉ cần đổi `CONFIG_OTA_URL`, không phải sửa code.
Yêu cầu tối thiểu 2 nhân / 2GB nếu chỉ gọi API ra ngoài.

Bộ **miễn phí, có tiếng Việt**:

| Tầng | Chọn | Ghi chú |
|---|---|---|
| STT | Whisper self-host (faster-whisper) | **Đừng dùng FunASR** — tối ưu cho tiếng Trung |
| LLM | Gemini free tier | Dự án ghi rõ có bậc miễn phí |
| TTS | EdgeTTS, giọng `vi-VN-HoaiMyNeural` / `vi-VN-NamMinhNeural` | Miễn phí, giọng Việt tự nhiên |

Nếu muốn chất lượng suy luận cao hơn, **Grok làm LLM là cắm vào chạy luôn** — server
nhận bất kỳ endpoint nào tương thích OpenAI, mà API chat của xAI đúng chuẩn đó.

Grok cũng có STT và TTS riêng (`https://api.x.ai/v1/tts`, $4.20 / 1 triệu ký tự —
khoảng 5000 lượt đối đáp), nhưng server dùng danh sách provider cố định **không có
xAI**, nên hai phần này phải tự viết adapter. Điểm cân bằng hợp lý: Grok cho LLM,
EdgeTTS cho TTS.

**LiveKit không hợp ở đây.** Nó là hạ tầng WebRTC + điều phối agent, bản thân không
phải nhà cung cấp STT. ESP32 nói giao thức riêng của xiaozhi chứ không phải WebRTC,
nên ghép vào là phải viết cầu nối hai giao thức mà chẳng được gì thêm.

### Chưa kiểm chứng

- Chưa thử `xiaozhi-esp32-server` với firmware 2.5.0 trong repo này; giao thức có thể đã đổi.
- **Rào cản thực tế lớn nhất là mạng:** server tự host phải cùng mạng với ESP32 hoặc
  phơi ra internet. Nếu ESP32 đang nối vào hotspot điện thoại hay máy in thì gần như
  chắc chắn không mở port được.
- Đổi server **không** cứu được chuyện thiếu wake word — đó là giới hạn phần cứng.

## Hạn chế đã biết

Không có PSRAM nên **không dùng được wake word** (`USE_ESP_WAKE_WORD` cần
`IDF_TARGET_ESP32 && SPIRAM`). Phải bấm nút để nói. Muốn rảnh tay thì cần
module có PSRAM, phổ biến nhất là ESP32-S3.
