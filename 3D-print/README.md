# 3D-print — vỏ robot và linh kiện

Vỏ lấy từ [ottorobot 小智修改版外壳](https://makerworld.com/en/models/1552932) trên
MakerWorld, đã sửa lại cho hợp với phần cứng của mình.

Mở [`viewer.html`](viewer.html) bằng trình duyệt để xem 3D — một tệp duy nhất,
không cần mạng, không cần cài gì.

## Vỏ robot (`vo-*`)

| Tệp | Chi tiết | SL | Kích thước (mm) |
|---|---|---|---|
| `vo-than.stl` | Thân — **đã sửa** | 1 | 69 × 69 × 42 |
| `vo-dau.stl` | Đầu | 1 | 69 × 69 × 41,7 |
| `vo-dui.stl` | Đùi | 2 | 17 × 41,5 × 40 |
| `vo-ban-chan.stl` | Bàn chân | 2 | 42 × 64 × 27 |
| `vo-cong-tac.stl` | Công tắc | 1 | 5,8 × 5,8 × 3,7 |
| `vo-nut-boot.stl` | Nút BOOT | 1 | 6,2 × 4,9 × 4,6 |
| `vo-canh-tay.stl` | Cánh tay — **không dùng** | 2 | 40,5 × 41,5 × 40,5 |
| `vo-ban-tay.stl` | Bàn tay — **không dùng** | 2 | 27 × 25 × 27 |

Bốn tệp đùi / bàn chân / cánh tay / bàn tay chứa **hai bản sao xếp cạnh nhau
trên khay in**, nên hộp bao của cả tệp gấp đôi. Số trong bảng là của **một**
chi tiết.

Cánh tay và bàn tay không in — robot chỉ dùng 4 servo (2 hông + 2 cổ chân).

## Linh kiện điện tử (`lk-*`)

Chỉ để ướm thử trong `viewer.html`, không in.

| Tệp | Linh kiện | Kích thước (mm) |
|---|---|---|
| `lk-esp32.stl` | ESP32 WROOM-32 USB-C | 54,8 × 25,5 × 12,4 |
| `lk-oled.stl` | OLED SSD1306 | 27,6 × 27,8 × 10,9 |
| `lk-khuech-dai.stl` | Khuếch đại MAX98357A | 18,0 × 17,9 × 19,4 |
| `lk-mic.stl` | Mic INMP441 | 14,0 × 14,0 × 11,4 |
| `lk-loa.stl` | Loa 8Ω 2W | 25,0 × 15,0 × 5,0 |
| `lk-servo.stl` | Servo SG90 | 32,2 × 29,8 × 12,5 |

## Đã sửa gì trên thân

`vo-than-goc.stl` là bản gốc chưa đụng tới, giữ lại để đối chiếu.

**1. Thu cửa sổ OLED: `30,2 × 30,8` → `26,0 × 20,0mm`**

Lỗ gốc **to hơn bo mạch OLED** (27,6 × 27,8) cả hai chiều nên nó lọt tọt qua,
không có gờ nào đỡ. Kích thước mới bám theo tấm kính thật của SSD1306 — rộng
hơn cao — và chừa gờ 0,8mm ngang, 3,9mm dọc.

**2. Bỏ giàn đỡ tay: thân `109` → `69mm`**

Thân thật chỉ rộng 69mm (`|x| ≤ 34,5`); toàn bộ phần từ 36 đến 54,5mm là giàn
đỡ cánh tay. Cắt phẳng tại `|x| = 34,6`, vá mặt cắt bằng Delaunay.

Chất lượng lưới sau khi sửa: **207 cạnh hở trên 111.502 tam giác (0,19%)** —
máy cắt lớp tự vá. Bản gốc kín tuyệt đối (0 cạnh hở, 85 cạnh chồng).

## Khoang trong thân — số đo để bố trí linh kiện

Đo bằng cách voxel hoá thân ở độ phân giải 1mm:

```
mặt đáy trống lớn nhất   57 × 65 mm
sâu từ miệng trên        40 mm
dải giữa (né gân hông)   36 × 65 mm
```

Mấy con số này giải thích vì sao **không nhét được pin 18650 có đế**: đế thông
dụng dài 75–77mm, trong khi khoang rộng nhất chỉ 65mm. Thử ở mọi góc nghiêng
đều không lọt.

Bốn trụ `4 × 4mm` cao `4mm`, cách nhau `22 × 22mm` ở giữa sàn là **vấu bắt
loa**; mấy chấm tròn quanh đó là lưới thoát âm. Đừng đặt gì đè lên.

## Tên tệp

Không dấu, có gạch nối. Tên gốc là tiếng Trung, đọc được nhưng phải chỉnh
`core.quotepath` của git mới hiện đúng, và một số máy cắt lớp hiển thị lỗi
phông. Tiền tố `vo-` là vỏ in ra, `lk-` là linh kiện chỉ để ướm.
