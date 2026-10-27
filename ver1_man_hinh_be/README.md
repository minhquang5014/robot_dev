# robot_dev — Trợ lý giọng nói xiaozhi trên ESP32

Môi trường làm việc cho ESP32 + mic I2S + khuếch đại I2S, chạy firmware
[xiaozhi-esp32](https://github.com/78/xiaozhi-esp32) (MIT) đã tuỳ chỉnh.

## Phần cứng

| Linh kiện | Chi tiết |
|---|---|
| MCU | ESP32-S3-WROOM-1 **N16R8** — 16MB flash, 8MB PSRAM (octal) |
| Mic | INMP441 (I2S) |
| Khuếch đại | MAX98357A (I2S) + loa 4–8Ω |
| Màn hình | OLED SSD1306 128x64 (I2C) |
| Chân robot | 4 servo SG90/MG90S (2 hông + 2 cổ chân) |

Trước 11/10/2026 dự án chạy ESP32-D0WD-V3 4MB **không có PSRAM**. Đổi sang S3 vì
hai lý do: con cũ chết chip USB-serial (cắm 5 lần không lên cổng COM nào), và
PSRAM là điều kiện bắt buộc để chạy wake word trên chip. Board cũ vẫn còn trong
repo ở `main/boards/bread-compact-esp32/`.

### Sơ đồ đấu nối

```
INMP441         ESP32-S3        MAX98357A       ESP32-S3
  VDD    ->      3V3              VIN     ->      5V
  GND    ->      GND              GND     ->      GND
  L/R    ->      GND              DIN     ->      GPIO7
  WS     ->      GPIO4            BCLK    ->      GPIO15
  SCK    ->      GPIO5            LRC     ->      GPIO16
  SD     ->      GPIO6            GAIN    ->      GND (12dB)
                                  SD      ->      để trống
OLED SSD1306    ESP32-S3          +/-     ->      loa 4-8Ω
  VCC    ->      3V3
  GND    ->      GND          Nút BOOT (GPIO0, có sẵn) = bắt đầu/dừng hội thoại
  SDA    ->      GPIO41       GPIO38 = giả lập câu đánh thức
  SCL    ->      GPIO42       GPIO47 = bộ đàm, giữ để nói

Hông trái	GPIO13
Hông phải	GPIO14
Cổ chân trái	GPIO21
Cổ chân phải	GPIO12
```

Tất cả GND chung.

Bản vẽ minh hoạ: [ESP32-S3 Robot Wiring Diagram.png](ESP32-S3%20Robot%20Wiring%20Diagram.png).
Đường dây từ linh kiện tới chân S3 trong ảnh khớp sơ đồ trên, nhưng **lấy sơ đồ chữ
ở trên làm chuẩn** vì ảnh có lỗi:

- Ô "Lưu ý khi hàn dây" ghi servo dùng 3.3V — **sai**, servo dùng 5V nguồn riêng (xem dưới).
- Bảng "Tóm tắt kết nối" lỗi chữ: mic `WS → GPIO45` (đúng là **GPIO4**), `GPIO0 → 3V3`;
  amp `DIN → 5V7`, `LRC → GPIO` thiếu số (đúng: DIN GPIO7, LRC GPIO16).
- Ảnh mic là module electret, không phải INMP441. Servo chỉ vẽ dây tín hiệu, thiếu dây nguồn.
- Nút GPIO38 / GPIO47 chỉ vẽ một dây — chân còn lại của nút nối **GND**.

**Servo phải có nguồn 5V riêng**, chỉ chung mát với board. Lấy từ chân 5V của
DevKitC-1 thì lúc servo giật sẽ kéo sụt cả đường nguồn của S3. Và `MAX98357A VIN`
nối thẳng VBUS không qua ổn áp nào — nên cắm USB qua hub hay cáp kém là tiếng loa
nhỏ hẳn đi. Hàn tụ ~1000 µF sát chân VIN của amp.

**Chân không dùng được trên S3**, khác hẳn ESP32 cũ nên đừng chép sơ đồ cũ sang:

| Chân | Lý do |
|---|---|
| GPIO22–25 | không tồn tại trên S3 (nhảy từ 21 sang 26) |
| GPIO26–32 | SPI flash |
| GPIO33–37 | PSRAM octal của bản R8 |
| GPIO19, 20 | USB D−/D+ |
| GPIO0, 3, 45, 46 | strapping |
| GPIO43, 44 | UART0 (console) |

GPIO12 là chân strapping trên **ESP32 cũ** nhưng **không phải** trên S3, nên ở đây
dùng được cho servo.

### Nguồn pin

| Linh kiện | Chi tiết |
|---|---|
| Pin | LiPo 1 cell **3,7V 3000 mAh**, có mạch bảo vệ (PCM) — mảnh mạch nhỏ dưới băng dính vàng ở đầu pin |
| Sạc + tăng áp | Module Type-C **FM5324GA** (25 x 20 mm): sạc pin qua Type-C, tăng 3,7V lên 5V |
| Công tắc | **Từ 3A trở lên** (ví dụ bập bênh KCD1). Gạt mini SS12D00 / MSK12C02 chỉ 0,3-0,5A — nóng, sụt áp |

```
Pin (+) đỏ ──[CÔNG TẮC ≥3A]── B+ ┐
Pin (−) đen ──────────────────── B− ┤  FM5324GA   5V  ──┬─► ESP32-S3 chân 5V
                                    │             GND ──┼─► GND chung (mọi thứ)
             nút nhấn nhả ── K ─────┘  [Type-C] = sạc   ├─► MAX98357A VIN  (+ tụ 1000 µF)
             (chân kia xuống GND)                       └─► 4 servo dây đỏ (+ tụ 1000 µF)
```

**Chưa chắc chân nào là B+ / B−.** Nhìn ảnh module thì hai miếng hàn cạnh TRÁI (ký hiệu
"□" và "+") là pin, cạnh DƯỚI ("+" và "5V") là ngõ ra — nhưng phải đo trước khi hàn,
ngược cực pin là cháy: cắm Type-C (chưa nối pin), miếng ra ~4,2V là B+, miếng ra ~5V là
ngõ ra; B− thông mạch với GND của ngõ ra.

**Công tắc đặt trên dây đỏ của pin** chứ không phải ở ngõ ra 5V: khi bật tăng áp, module
ăn điện liên tục, ngắt ở ngõ ra thì robot tắt nhưng pin vẫn bị rút. Cái giá: **tắt công
tắc thì không sạc được** — nhớ bật lên khi cắm sạc.

#### Chân K (bật / tắt ngõ ra 5V) — đo ngày 16/10/2026

| Thử | Kết quả |
|---|---|
| Cắm pin, chưa làm gì | Ngõ ra ~3,8V = điện áp pin lọt qua cuộn cảm + diode, **tăng áp chưa chạy** |
| Chạm K xuống GND một cái | Lên **5V** |
| **Hàn cứng K xuống GND** | Giữ 5V được vài phút rồi **tụt xuống 1,6V** — chip hiểu K bị giữ mãi là "nhấn giữ = tắt", tụ ngõ ra xả dần qua đồng hồ đo |

→ **Không hàn cứng K xuống GND.** Dùng K làm nút nguồn (nút nhấn nhả, giống sạc dự phòng):
nhấn một cái để bật. Lúc thử trên chỉ có đồng hồ đo làm tải (gần như 0 mA) — có robot
làm tải (ESP32-S3 ~100 mA trở lên) thì nhiều khả năng mạch không tự tắt. **CHƯA kiểm
chứng:** cắm robot, nhấn K, để chạy 15 phút xem có tự tắt không.

#### Nếu có robot làm tải mà vẫn tự tắt — ESP32 giữ cho mạch thức (CHƯA làm)

Đừng để ESP32 *chờ thấy điện yếu rồi mới* kéo K: ESP32 lấy điện từ chính module này, lúc
tăng áp tắt thì ngõ ra tụt về ≤3,8V, ổn áp 3,3V trên board không đủ đầu vào nên chip sụt áp
và reset trước khi kịp phản ứng. Thay vào đó **nhấn K ngắn theo nhịp, mỗi ~15-20 giây**, để
mạch không bao giờ tự tắt.

Phải thử trước: chạm K xuống GND **thật nhanh (dưới nửa giây) trong lúc đang có 5V** — nếu
5V vẫn giữ thì cách này dùng được; nếu chip hiểu là bật/tắt thì không dùng được.

**Nối THẲNG, không cần transistor.** Chân K lúc nghỉ đo được **0,8V** (17/10/2026) — thấp hơn
3,3V nên nối thẳng vào GPIO không hại gì ESP32:

```
ESP32-S3 GPIO2 ─────── chân K của FM5324GA
```

- Đặt GPIO2 ở chế độ **open-drain**: chỉ có hai trạng thái — kéo xuống GND hoặc thả nổi,
  không bao giờ ra 3,3V. Kéo **xuống 0** ~200 ms rồi thả = một lần "nhấn nút".
- **Đừng** cho GPIO2 ra mức cao: đẩy 3,3V vào K (bình thường 0,8V) là cãi nhau với mạch
  trong chip sạc.
- Lúc ESP32 khởi động GPIO2 mặc định thả nổi nên không bị "nhấn nhầm".
- GPIO2 đang trống trên board S3 (soát với `bread-compact-s3-otto/config.h`).

**Dây K: nhấn theo nhịp chạy chắc chắn; có cần hay không thì CHƯA chốt** — đo ngày
26/10/2026 trên ESP32 WROOM chạy pin, sketch `test/fm_keepalive` (tự ghi log vào flash):

| Thử | Kết quả |
|---|---|
| ESP32 nhấn K mỗi 15 s (200 ms) | giữ 5V **33,2 phút liền**, 132 lần nhấn, 4,93-5,08V (TB 5,04V), không mất điện lần nào |
| Không nhấn K, ESP32 làm tải (WiFi quét định kỳ, ~100 mA) | lần 1 tắt, ngõ ra tụt ~1,5V — nhưng **có thể do chạm tay vào mạch**. Lần 2 đang chạy, **chưa đọc được log** (máy không thấy cổng USB của board) |

→ Chắc chắn: nhấn ngắn khi đang bật **không** làm tắt (chip không hiểu là bật/tắt), nên
firmware robot nhấn K theo nhịp là an toàn. Chưa chắc: không nhấn thì mạch có tự tắt khi có
tải không — đọc log lần 2 rồi mới chốt. Board ESP32 cũ (WROOM) dùng GPIO18 vì không ra chân
TX2/RX2; trên board cũ GPIO18 trùng `LAMP_GPIO`, lắp vào robot thì phải dời một trong hai.

**Cắm USB lúc đang chạy pin làm board reset liên tục** (log đầy `POWERON_RESET`) — hai nguồn 5V
đè nhau. Rút pin trước khi cắm USB.

**Đo điện áp pin — tuỳ chọn, có thể bỏ.** Chỉ để báo pin yếu lên OLED; không có thì robot vẫn
chạy, hết pin thì tắt phụt (mạch bảo vệ của pin ngắt ~3,0V, vẫn an toàn). 4 đèn LED trên
module báo mức pin thay được. Nếu muốn làm:

```
5V ──[10 kΩ]──┬──[10 kΩ]── GND
              └── ESP32-S3 GPIO1 (ADC)
```

Chân ADC của ESP32 chỉ đọc tới ~3V, nối thẳng 5V là hỏng. Hai điện trở bằng nhau chia đôi:
5V đọc ra 2,5V, trong code nhân 2. Đọc ~1,9V (tức 3,8V) = tăng áp đã tắt. Rút ~0,25 mA
liên tục; thêm tụ 100 nF từ điểm giữa xuống GND cho số đọc ổn định.

#### Nút nguồn (kế hoạch, CHƯA làm)

```
                 ┌──── ESP32-S3 GPIO2   (firmware tự nhấn 200 ms mỗi 15 s, open-drain)
FM5324GA K ──────┤
                 └──── NÚT NHẤN ──── GND (người dùng bấm)
```

- Nút và GPIO2 nối **song song**: cả hai chỉ kéo K xuống GND, GPIO2 open-drain không bao giờ
  đẩy điện lên, nên không xung đột.
- **Bật:** robot tắt thì ESP32 không có điện để tự nhấn — người dùng bấm nút một cái, mạch FM
  bật 5V, ESP32 khởi động rồi tự nhấn giữ mạch thức (firmware `InitializePowerKey()`).
- **Tắt:** hàn cứng K xuống GND thì vài phút sau mạch tắt, nên nhiều khả năng **giữ nút lâu**
  là tắt — một nút làm cả bật lẫn tắt. Chưa đo phải giữ bao lâu.
- **Cắm sạc:** nhiều module loại này tự bật 5V khi có nguồn Type-C — nếu FM5324GA cũng vậy thì
  hết pin chỉ cần cắm sạc là robot sống lại. Chưa thử.

Robot tự tắt khi chạy pin lâu: đo ngay điện áp hai dây pin. ≥3,7V = mạch FM tự tắt (firmware
chưa nhấn K — bản 27/10 mới có, chưa nạp được vì mạng công ty chặn registry Espressif).
≤3,0V = hết pin, mạch bảo vệ của pin ngắt — đúng và an toàn, cắm sạc.

Cần thử: (1) nạp firmware có nhấn K, chạy pin ~1 giờ; (2) cắm sạc lúc robot đang tắt; (3) giữ
K xuống GND 2 / 3 / 5 giây xem bao lâu thì tắt.

#### Đèn LED khi sạc

Cắm sạc thấy sáng 3/4 đèn dù pin đang ~3,0V là bình thường: lúc có dòng sạc, điện áp ở cực
pin bị đẩy cao hơn mức thật nên đèn báo dư. Muốn biết thật thì rút sạc, để nghỉ 10-15 phút
rồi đo ở hai dây pin (đầy ~4,1-4,2V).

Sạc bằng cục sạc MacBook (USB-C PD) an toàn: không xin thì PD chỉ cấp 5V. Nếu cáp C-to-C
cắm vào không sạc là module thiếu điện trở 5,1 kΩ ở chân CC — dùng cáp USB-A sang C với cục
sạc thường.

#### Pin 3000 mAh có đủ dòng không

Robot kéo tới ~2A ở 5V khi 4 servo cùng giật. Tăng áp lên 5V nên phía pin chịu dòng gấp
~1,6 lần: **pin phải xả ~3,2A**. Pin 3000 mAh dù chỉ xả 1C cũng đã ~3A, nên nhiều khả năng
đủ — nhưng **mạch bảo vệ (PCM) có ngưỡng ngắt quá dòng riêng**, có loại ngắt ở ~3A. Chưa
biết chỉ số xả (C) và ngưỡng PCM của pin này. Thử: cho robot nhảy cả bài trong lúc đang nói;
tắt hoặc reset giữa chừng là PCM đang ngắt.

Ước tính thời gian chạy (chưa đo): 3000 mAh x 3,7V ≈ 11 Wh, qua tăng áp còn ~9 Wh ở 5V →
đứng nghe (~150 mA) **khoảng 10-12 giờ**, nói và đi nhiều **khoảng 3 giờ**.

**Cắm USB nạp code khi đang chạy pin:** hai nguồn 5V có thể đè nhau. Tắt công tắc pin
trước khi cắm USB, hoặc nạp qua WiFi (OTA).

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

4. **Đánh thức bằng tên "Sophia"** — `CONFIG_SR_WN_WN9_SOPHIA_TTS=y`.

   Thay cho `CONFIG_ALWAYS_LISTENING` cũ (rảnh ~5 giây là tự mở hội thoại). Chế độ
   cũ làm robot trả lời **mọi** câu nó nghe được và gửi tiếng lên server 100% thời
   gian; giờ nằm im cho tới khi nghe đúng tên.

   Vì sao là "Sophia": model WakeNet đóng gói sẵn trong `esp-sr` có 75 cái, lọc bỏ
   tiếng Trung còn 39 — **không có tiếng Việt**. Trong nhóm tên nữ, "Sophia" là cái
   **duy nhất gọi trống được**; mọi tên khác đều buộc kèm "Hey"/"Hi" (Hey Ivy,
   Hi Fairy…). Muốn đúng tên tiếng Việt thì phải đặt model riêng của Espressif.

   Ba thứ phải khớp nhau nếu đổi tên: model trong `sdkconfig`, chuỗi
   `WakeWordInvoke` trong board `.cc`, và `ROBOT_NAME`/`WAKE_PATTERN` trong
   `server/pipeline.py`.

   **Luồng:** nằm chờ ở Idle, không gửi gì lên mạng — mic chỉ chạy vào
   `[VAD(WebRTC)] -> [WakeNet]` trong chip. Nghe thấy tên → giữ lại đoạn tiếng đó
   (`CONFIG_SEND_WAKE_WORD_DATA=y`, thiếu nó thì bản ghi không chứa tên và bộ lọc
   tên phía server loại sạch mọi lượt) → mở kênh, gửi Opus 60 ms → server quyết
   định lượt kết thúc → trả lời → **về lại Idle**.

   Lưu ý có **hai VAD làm hai việc khác nhau**: cái trong chip chỉ để gác WakeNet
   cho đỡ tốn điện; cái trên server mới quyết định người nói đã dứt câu chưa.

   Cái giá: phải gọi tên **mỗi lượt**, không nói tiếp được. Cửa sổ 20 giây hỏi tiếp
   không cần gọi tên (`WAKE_WINDOW_S` trong `xiaozhi_server.py`) vì thế thành vô
   dụng — thiết bị về Idle ngay nên không gửi gì lên trong quãng đó.

   Hai mắt xích đã phải vá để wake word thật sự gác được, vì bật model thôi chưa đủ:
   `application.cc` nhận `tts stop` chỉ về Idle khi chế độ là `ManualStop`, còn
   `AutoStop` thì quay lại Listening; và chế độ `AutoStop` nghĩa là thiết bị chờ
   server báo hết lượt, mà server lại huỷ lượt rỗng trong im lặng — nay gửi cặp
   `tts start`+`stop` rỗng (`ket_thuc_luot`) để báo.

5. **Server tự host** — `CONFIG_OTA_URL` trỏ về `https://xiaozhi-esp32-server.fly.dev/xiaozhi/ota/`
   thay vì `api.tenclass.net`. Không cần đăng ký mã trên xiaozhi.me nữa.

6. **Nâng cấp qua WiFi (OTA)** — chỉ chạy được từ khi sang board 16MB.

   Bảng `partitions/v2/16m.csv` có hai khe `ota_0`/`ota_1`. Board 4MB cũ chỉ có một
   phân vùng `factory`, và hai khe cũng **không nhét vừa** 4MB — nên OTA trên nó là
   bất khả thi, không phải chuyện cấu hình.

   Firmware vốn đã có sẵn code OTA; phần thiếu là server không trả khoá `firmware`.
   Quy trình phát hành xem `server/firmware/.gitkeep`. Server đọc phiên bản và mã
   chip **thẳng từ file `.bin`** nên không có tệp phụ nào để lệch.

   Firmware chỉ hỏi OTA **một lần lúc khởi động** (`application.cc`, `CheckNewVersion`),
   không có hẹn giờ định kỳ — muốn nâng cấp thì bấm reset.

## Cài môi trường (macOS, không cần sudo)

```bash
# ESP-IDF v6.1 — xiaozhi yêu cầu >= 6.0.1, KHÔNG chạy trên 5.x
git clone -b v6.1 --recursive --depth 1 --shallow-submodules \
    https://github.com/espressif/esp-idf.git ~/esp/esp-idf
cd ~/esp/esp-idf && ./install.sh esp32s3

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
idf.py set-target esp32s3    # chỉ lần đầu
idf.py build
idf.py -p /dev/cu.usbserial-XXXX flash monitor
```

> **Đường dẫn repo không được có dấu cách.** Với đường dẫn kiểu `~/Documents/2. Py/...`
> bước link hỏng: `ld: cannot find Py/2.Raw/19.: No such file or directory` — thư viện
> prebuilt của `esp_audio_codec` bị cắt đôi ở dấu cách. Clone vào chỗ khác, ví dụ `~/esp/robot_dev`.

Sau khi nạp, thiết bị phát hotspot `Xiaozhi-XXXX`. Nối điện thoại vào, mở
`http://192.168.4.1` để khai báo WiFi (chỉ 2.4GHz). Với server trong `server/`
thì thiết bị tự nói chuyện luôn, không cần đăng ký mã tại xiaozhi.me.

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

**[`server/`](server/README.md) — server duy nhất của repo**, tự viết, deploy lên Fly.io
bằng `fly deploy` ngay trong thư mục đó. Groq Whisper + `qwen3.8-27b` + xAI TTS, tiếng
gửi xuống 24 kHz đúng tần số loa, có lọc câu ảo giác cho chế độ luôn nghe.
**Điều khiển chân bằng giọng nói** qua MCP: LLM gắn tag động tác ngay sau tag cảm
xúc (`[joyful][dance]`), server gửi `tools/call self.otto.action` xuống firmware
**trước** TTS. Cố ý không dùng function calling của LLM vì thêm một vòng gọi API
và hay vỡ khi stream.

**Điều khiển bằng chữ từ máy tính** — `server/say.py`, khỏi phải nói:

```bash
python say.py "nhảy một điệu đi"   # y như vừa nói: LLM -> cảm xúc + động tác + TTS
python say.py --do dance           # bắn thẳng động tác, KHÔNG qua LLM, không tốn TTS
python say.py --do walk --steps 4
python say.py --liet-ke            # 15 động tác hợp lệ
```

`--do` mới là thứ dùng khi thử dáng đi: phải lặp cùng một lệnh hàng chục lần, mà
mỗi lượt qua LLM là một lần gọi Groq (bản miễn phí chỉ 20 STT/phút).

Hai endpoint này (`/xiaozhi/say`, `/xiaozhi/do`) mở một cửa điều khiển ra Internet
nên **có mật khẩu**: header `Authorization: Bearer`, đặt bằng
`fly secrets set XZ_CTRL_TOKEN=...` chứ không ghi vào `fly.toml` (tệp đó nằm trong
git). Không đặt secret thì hai cửa **đóng** (503) chứ không mở toang. `say.py` tự
đọc mật khẩu từ `server/.env`.

Trước 06/10/2026 repo còn `fly-server/`: bọc [xiaozhi-esp32-server](https://github.com/xinnan-tech/xiaozhi-esp32-server)
(dự án cộng đồng, đủ MCP) kèm bản vá. Đã bỏ vì chậm (đo 06/10: ~15 s tới câu trả lời đầu)
và hay dính mặc định tiếng Trung. Xem lại trong lịch sử git nếu cần.

**Đổi server không cần nạp lại firmware.** Firmware đọc `ota_url` lưu trong NVS trước,
trống mới dùng `CONFIG_OTA_URL` (`main/ota.cc:48-55`). Đặt được qua trang cấu hình WiFi
`http://192.168.4.1`, tab nâng cao.

#### Bộ miễn phí, có tiếng Việt

> **Groq không phải Grok.** Hai công ty khác nhau. **Grok** là LLM của xAI, trả tiền.
> **Groq** là công ty phần cứng suy luận, nổi tiếng vì tốc độ, và free tier rất rộng.
> Nhầm hai cái này là mất tiền oan.

| Tầng | Chọn | Hạn mức miễn phí |
|---|---|---|
| STT | Groq `whisper-large-v3-turbo` | 2.000 req/ngày, 28.800 giây audio/ngày |
| LLM | Groq `qwen/qwen3.8-27b` | ~1.000 req/ngày, **8.000 token/phút** |
| TTS | EdgeTTS, `vi-VN-HoaiMyNeural` / `vi-VN-NamMinhNeural` | Không giới hạn thực tế |

Tổng chi phí **$0/tháng**, không cần thẻ tín dụng. Groq tương thích chuẩn OpenAI nên
cắm thẳng vào khe LLM. Chỗ siết thật là **token/phút** chứ không phải request/ngày:
mỗi lượt ~700 token, tức trần khoảng 11 lượt/phút — robot để bàn thì thoải mái.

> **Groq gỡ model theo thời gian.** Bản trước của README này khuyến nghị
> `llama-3.1-8b-instant`; đến 16/09/2026 model đó đã bị gỡ. Chạy
> `python server/test_voice.py --models` trước khi tin bất kỳ tên model nào ở đây.
> Số đo và so sánh các model: [server/README.md](server/README.md).

**Đừng dùng FunASR cho tiếng Việt** — nó tối ưu cho tiếng Trung. Muốn chạy STT
hoàn toàn cục bộ thì dùng faster-whisper.

Nếu cần suy luận mạnh hơn, **Grok (xAI) cắm được thẳng vào khe LLM** vì API chat của
họ đúng chuẩn OpenAI. Grok cũng có STT/TTS riêng (`https://api.x.ai/v1/tts`,
$4.20 / 1 triệu ký tự ~ 5000 lượt đối đáp) nhưng server dùng danh sách provider cố
định **không có xAI**, nên hai phần đó phải tự viết adapter.

**LiveKit không hợp ở đây.** Nó là hạ tầng WebRTC + điều phối agent, bản thân không
phải nhà cung cấp STT. ESP32 nói giao thức riêng của xiaozhi chứ không phải WebRTC,
nên ghép vào là phải viết cầu nối hai giao thức mà chẳng được gì thêm.

#### Đặt server ở đâu

ESP32 chỉ mở kết nối **đi ra** (y như nó đang gọi `api.tenclass.net`), nên:

- **VPS có IP công cộng — dễ nhất.** Mạng nhà hay mạng ESP32 đang bám không cần cấu
  hình gì. Oracle Cloud Always Free cho 4 nhân ARM / 24GB vĩnh viễn là quá đủ, nhược
  điểm là nhiều khu vực hay hết chỗ ARM, phải thử lại nhiều lần.
  **Trên VPS thì vẫn phải mở cổng server**, và với Oracle là mở ở **cả hai chỗ**:
  security list của VCN, và iptables bên trong máy (image Ubuntu của Oracle chặn sẵn).
  Thiếu một trong hai là ESP32 báo không kết nối được.
- **Máy ở nhà — vướng mạng.** Chỉ chạy khi ESP32 **cùng mạng LAN**, hoặc bạn mở được
  port ra ngoài. Nếu ESP32 đang bám hotspot điện thoại hay máy in thì gần như chắc
  chắn không mở port được. Đây là lựa chọn khó hơn, không phải dễ hơn.
- **Máy công ty — đừng.** Mở cổng hay dựng tunnel (cloudflared, ngrok…) trên máy do
  công ty quản lý là đi vòng tường lửa của họ, IT theo dõi đúng loại việc này. Dùng
  máy công ty để sửa code, nạp firmware qua USB, đọc log là đủ; server đặt trên VPS.

#### Với robot kiểu thú cưng thì tối ưu cái gì

Thứ quyết định "dễ thương" không nằm ở kích cỡ model:

- **Độ trễ ăn đứt độ thông minh.** Trả lời ngốc nghếch sau 0,8 giây dễ thương hơn hẳn
  câu sâu sắc sau 4 giây — im lặng 4 giây trông như treo máy. Đó là lý do chọn Groq.
- **Câu trả lời phải ngắn.** Thú cưng không thuyết trình. Ép system prompt giới hạn
  1–2 câu: vừa nhanh, vừa đáng yêu, vừa đỡ tốn TTS.
- **Tính cách nằm ở system prompt.** Model vừa phải với prompt nhân vật viết kỹ sống
  động hơn model lớn trả lời trung tính. Đây là chỗ đáng bỏ công nhất mà lại miễn phí.
- **Model nhỏ nhất chưa chắc nhanh nhất.** Trên Groq tốc độ phụ thuộc phần cứng họ phục
  vụ, không phụ thuộc kích cỡ. Đo 17/09/2026: `allam-2-7b` (nhỏ nhất) trung vị 419 ms
  và nói tiếng Việt hỏng, còn `qwen3.8-27b` trung vị 362 ms và nói tốt.
- **Giọng đọc quan trọng ngang nội dung.** EdgeTTS chỉnh được tốc độ và cao độ; nói
  nhanh hơn một chút thường nghe trẻ trung, hợp kiểu robot cute.

### Chưa kiểm chứng

- Server tự viết trong `server/` chưa được ESP32 thật gọi vào — mới qua thiết bị giả lập.
- Chưa tự đăng ký Oracle Cloud Always Free nên không dám hứa lấy được máy ARM ngay.
- Hạn mức Groq ở bảng trên lấy từ header trả về khi chạy thật, nhưng chưa chạy đủ
  lâu để chạm trần ngày.
- Đổi server **không** cứu được chuyện thiếu wake word — đó là giới hạn phần cứng.

## Hạn chế đã biết

Không có PSRAM nên **không dùng được wake word** (`USE_ESP_WAKE_WORD` cần
`IDF_TARGET_ESP32 && SPIRAM`) và **không có AEC** (`USE_AUDIO_PROCESSOR` cần S3/P4 +
PSRAM). Chế độ luôn nghe (tuỳ chỉnh 4) thay cho wake word nhưng trả lời mọi câu nghe được,
và robot không nghe trong lúc đang nói. Muốn gọi tên mới tỉnh hoặc ngắt lời bằng giọng thì
cần module có PSRAM, phổ biến nhất là ESP32-S3.
