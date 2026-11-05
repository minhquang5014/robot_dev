# Mạch chính Otto ver2

Bo mạch custom cho robot ver2: ESP32-S3-WROOM-1 N16R8 hàn thẳng, màn ST7789
240×240 qua SPI, Otto 2 chân, loa khoang 8Ω 2W, mic INMP441.

Mở bằng KiCad 10. File dự án: `otto-ver2.kicad_pro`.

## Mạch to bao nhiêu thì còn nhét vừa thân

Đo trực tiếp trên `../3D-print/vo-than-noi-luoi-loa.stl` bằng cách quét tia
theo trục z ở từng độ cao, lấy bóng ngoài trừ đi nhựa, rồi trừ tiếp mọi vật
thể đã chiếm chỗ. Tiêu chí: hình chữ nhật phải còn **rỗng liên tục 11mm**
tính từ đáy mạch (1,6mm bo + ~10mm linh kiện cao nhất).

| Vị trí | Cao độ đáy | Lớn nhất | Diện tích |
|---|---|---|---|
| Lọt giữa hai servo | z = 8…24 | 37 × 38 mm | 1.406 mm² |
| **Nằm trên servo như nắp** | **z = 31** | **65 × 46 mm** | **2.990 mm²** |

Chọn phương án nằm trên. Ở z=31 nó cao hơn mọi thứ bên dưới: servo tới 25,
IP5306 tới 30, vách pin tới 31. Thân cao 42 nên còn đúng 11mm.

**Biên mạch lấy 64 × 45mm**, chừa 0,5mm hở mỗi cạnh so với 65 × 46 đo được.

### Các vật thể đã trừ khi đo

| Vật thể | x | y | z |
|---|---|---|---|
| Màn hình (mô-đun 40×33×5 áp sau cửa sổ) | −20…20 | −32,5…−27,5 | 5…38 |
| Loa (trên lưới thoát âm) | −12,5…12,5 | −16…−0,5 | 2…7 |
| Servo trái | −31…−19 | −18…7 | 2…25 |
| Servo phải | 19…31 | −18…7 | 2…25 |
| IP5306 | 8,5…33,5 | 11…15 | 10…30 |
| Vách pin | −13,5…34,5 | 15,5…18,5 | 2…31 |
| Pin LiPo 104058 dựng đứng | −9,5…30,5 | 18,5…28,5 | 2…60 |

Cửa sổ mặt trước đo được **30,5 × 30,5mm** ở `x −15…15, z 6,5…36,5` — vùng
hiển thị 27,7 × 27,7 của màn 1.54" lọt thoải mái.

Chiều cao servo `z 2…25` là **ước lượng theo thân SG90 (22,5mm)**, không đo
được từ file thân vì servo không nằm trong đó. Rãnh sàn đo được 12 × 25mm,
khớp đúng tiết diện thân SG90 (12,6 × 22,8), và mã rig trong `viewer.html`
ghi "cần servo cắm từ sàn xuống" nên thân servo nằm trên sàn. Nếu lắp thật
thấy khác thì phải đo lại cao độ z=31.

## Hệ toạ độ

```
PCB_x = robot_x + 150
PCB_y = 100 − robot_y
```

Mạch nằm ở `z = 31` trong thân. Biên mạch phủ `robot x −32…32, y −27…18`.

Bốn lỗ vít M2 (Ø2,2) ở `robot (±28, −23)` và `(±28, 14)`. **Thân in chưa có
trụ bắt vít** — phải thêm vào `vo-than-noi-luoi-loa.stl` trước khi in.

## Sơ đồ chân

ESP32-S3-WROOM-1 N16R8 dùng được: 0–18, 21, 38–42, 45–48.
Tránh: 19/20 là USB D−/D+, 22–25 không tồn tại, 26–32 nuôi flash,
**33–37 nuôi PSRAM octal** của bản R8, 43/44 là UART0.

| Khối | Chân |
|---|---|
| Màn ST7789 SPI | CLK 18 · MOSI 17 · DC 8 · RST 9 · BLK 10 |
| Mic INMP441 I2S | WS 4 · SCK 5 · DIN 6 |
| Loa MAX98357A I2S | DOUT 7 · BCLK 15 · LRCK 16 |
| Servo | chân trái 13 · chân phải 14 · cổ trái 21 · cổ phải 12 |
| Nút | BOOT 0 · TOUCH 47 · ASR 38 |

Còn trống: **1, 2, 3, 11, 39, 40, 41, 42, 45, 46, 48**. Dự định dùng:

- **Đo điện áp pin** — bắt buộc ADC1 (GPIO 1–10) vì ADC2 đụng WiFi; trong
  nhóm đó chỉ còn 1, 2, 3 trống. Ver1 không có nên không biết pin còn bao nhiêu.
- **Chân KEY giữ mạch sạc không tự tắt** — ver1 dùng GPIO2, giữ nguyên cho đồng bộ.
- **LED trạng thái** — GPIO48, đúng chân ver1 dùng.
- **I2C dự phòng** — 41/42, cặp ver1 dùng cho OLED.

Số chân khớp với `../xiaozhi-esp32/main/boards/s3-otto-lcd/config.h`. Đổi ở
một nơi thì phải đổi cả hai.

## Lưu ý thiết kế

- **Vùng anten.** Chỗ anten WROOM-1 phải không có đồng ở mọi lớp, và nên
  quay về phía trước (`y −27`). Cục pin LiPo ở `y 18,5…28,5` có vỏ nhôm,
  chắn 2,4GHz.
- **Dòng servo.** 4 con SG90 lúc khởi động kéo đỉnh ~2,5A. Đường nguồn servo
  tách riêng khỏi nguồn 3,3V của MCU, dùng net class `Power` (đường 1,0mm),
  và cần tụ lớn ngay tại cổng servo.
- **Cỡ linh kiện 0805/0603, chân rộng** — hàn tay được mà đặt máy hàn cũng được.

## Chưa làm

- Phần sạc/nguồn pin: chờ bản vẽ tham khảo.
- Schematic mới chỉ là khung rỗng.
- Thân in chưa có trụ bắt vít cho mạch.
