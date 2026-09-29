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

**1. Thu cửa sổ OLED: `30,2 × 30,8` → `26,0 × 20,0mm`, và làm dày vách quanh đó**

Lỗ gốc **to hơn bo mạch OLED** (27,6 × 27,8) cả hai chiều nên nó lọt tọt qua,
không có gờ nào đỡ. Kích thước mới bám theo tấm kính thật của SSD1306 — rộng
hơn cao — và chừa gờ 0,8mm ngang, 3,9mm dọc.

Cách làm: **đắp thêm một khung dày 3,0mm** lên vách trước, không dời đỉnh nào
của lưới gốc. Khung phủ `x ±16,0`, `z −37,5..−0,5`, chừa lỗ `26 × 20`.

Vùng phủ rộng hơn mép lỗ là có chủ đích — bản gốc có **hai dải gờ đỡ OLED chỉ
dày 0,5–0,8mm** nằm ngay trên và dưới cửa sổ (`z −36..−33` và `z −2..−1`).
Bên in 3D báo chỗ này quá mỏng. Khung mới trùm hết:

| Bề dày vách trước | Gốc | Sau khi sửa |
|---|---|---|
| 0,5–0,8mm | 1.362 điểm | **13 điểm** |
| ≥2,5mm | 2.858 điểm | 6.794 điểm |

> ⚠️ Lần đầu mình thu cửa sổ bằng cách **dời đỉnh** — cách đó kéo giãn tam
> giác quanh lỗ thành màng mỏng, đẩy tỉ lệ vách dưới 1,0mm từ 6,1% lên 22,0%.
> Sửa hình học lưới thì **cộng thêm khối luôn an toàn hơn dời đỉnh**.

**2. Rãnh servo trên sàn: giữ nguyên `11,75mm`**

Đã từng nới lên `13,00mm` rồi **bỏ**. Đo ở lưới 0,25mm:

| | Servo SG90 | Rãnh gốc |
|---|---|---|
| Dài (cả tai bắt vít) | 32,2mm | 34,0mm ✅ |
| **Rộng** | 12,2mm | **11,75mm** |

Bề rộng hụt 0,45mm so với số liệu tra cứu. Nhưng đây là thiết kế Otto vốn dành
cho SG90 và đã có vô số người in chạy được, nên nhiều khả năng nó cố ý lắp
chật. Nếu chật thật thì gọt bằng dao dễ hơn in lại cả thân nhiều.

Cách nới cũ là dời đỉnh thành rãnh phía trong vào 1,25mm — không dùng được vì
thành phía ngoài chỉ cách vách thân ~0,3mm nên không đẩy ra được, mà dời phía
trong thì các đỉnh từ `|x| 20,3` trở ra nằm ngoài vùng chọn vẫn đứng yên, kéo
tam giác nối giữa thành màng. Lại đúng cái lỗi "dời đỉnh làm mỏng vách hàng
xóm" đã gặp ở cửa sổ OLED.

**3. Bỏ giàn đỡ tay: thân `109` → `69mm`**

Thân thật chỉ rộng 69mm (`|x| ≤ 34,5`); toàn bộ phần từ 36 đến 54,5mm là giàn
đỡ cánh tay. Cắt phẳng tại `|x| = 34,6`, vá mặt cắt bằng Delaunay.

## Kiểm trước khi gửi đi in

```
tệp              tam giác  cạnh hở  suy biến  phi-mf   khối rời
────────────────────────────────────────────────────────────────
vo-than.stl        111.550      32       122      69      1
vo-dau.stl         103.634       0         0       0      1
vo-dui.stl         121.794       0         0       0      2
vo-ban-chan.stl     43.240       0         0       0      2
vo-cong-tac.stl     10.812       0         0       0      1
vo-nut-boot.stl     10.748       0         0       0      1
```

**`vo-dui.stl` và `vo-ban-chan.stl` mỗi tệp đã chứa sẵn 2 bản.** In một lần
mỗi tệp là đủ cả đôi; đặt "2 cái" sẽ ra 4 cái.

`vo-than.stl` báo 32 cạnh hở nhưng **không thủng thật**: bắn 4.000 tia xuyên
ngang, không tia nào cắt lẻ lần. Đó là các đỉnh tách ở mức dưới micron tại mặt
cắt giàn tay — hàn lại ở dung sai `0,01mm` thì còn 1, ở `0,1mm` thì còn 0. 69
cạnh phi-manifold là chỗ khung cửa sổ cộng thêm chồng lên vách cũ, đúng như
mong đợi khi hợp khối bằng cách ghép tam giác.

Còn **một vùng 7mm² dày 0,40mm** ở `x −24,4..−20,4`, `z −32,4..−31,2`. Chỗ này
**có sẵn trong bản gốc**, không phải do sửa; bên in xem bản trước cũng không
nhắc tới nó. Rộng đúng một đường đùn của vòi 0,4mm.

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

Khoang trong **đầu** (`vo-dau.stl`), đo cùng cách:

```
hốc rỗng lớn nhất        56 (ngang) × 16 (cao) × 58 (sâu) mm  =  52 cm³
```

## Bố trí với pin 10 × 40 × 58mm

Cục pin này dài `58mm`, gần bằng cả chiều sâu khoang, nên nó chiếm trọn một
tầng. Bộ giải xếp hình chạy trên lưới voxel 1mm, khe hở 1mm quanh mỗi món:

```
tầng      Y (mm)      món
────────────────────────────────────────────────────────────
sàn        3 – 10     loa 25×15×5, úp lên lưới thoát âm
giữa      10 – 22     PIN 58×10×40 nằm ngang, đè lên loa
                      mic INMP441 nhét cạnh pin, Z 10.5..26.5
trên      22 – 37     ESP32 nằm ngang, sát vách sau
          22 – 42     khuếch đại dựng đứng, giữa thân
cửa sổ    11 – 41     OLED áp sau khung
────────────────────────────────────────────────────────────
trong đầu              mạch IP5306 50×25×8 nằm ngang
```

**Thứ tự xếp quan trọng.** Xếp pin sau cùng thì không hướng nào lọt; xếp pin
trước thì vừa. Lý do là mặt bằng `58 × 40mm` của nó cần một tầng liền mạch, mà
ESP32 với IP5306 xếp trước sẽ cắt khoang thành những lát mỏng vô dụng.

**IP5306 phải dời lên đầu.** Trần khoang thân chỉ cao `40mm` tính từ sàn, mà
pin `12mm` + ESP32 `15mm` + IP5306 `10mm` đã là `37mm` — cộng thêm `7mm` loa ở
dưới là tràn. Đặt nghiêng mạch cũng không cứu được vì nó dài `50mm`. Hốc đầu
`56 × 16 × 58mm` thì chứa nó thoải mái, còn thừa chỗ đi dây xuống thân.

Pin không nhét được vào đầu: hốc rộng `56mm`, pin dài `58mm` — thiếu 2mm.

## Chế độ "Giả lập" trong viewer

Xem trước robot ráp xong sẽ chạy thế nào: màn OLED hiện gì, chân nhảy ra sao.
Mọi con số đều lấy từ mã nguồn thật, không ước lượng.

**Góc servo** dùng đúng công thức dao động của Otto
(`boards/otto-robot/otto_movements.cc`):

```
góc = 90 + trim + biên_độ · sin(2π·t/chu_kỳ + pha)
```

14 động tác với đúng bộ tham số `A / O / phase` chép từ firmware — đi tới, đi
lùi, quay trái/phải, lắc lư, nhún, kiễng chân, rung hông, xoay dâng, moonwalk,
crusaito, vỗ cánh, nhảy, về nghỉ.

**Vị trí khớp** đo bằng thuật toán chứ không ướm bằng mắt: voxel hoá từng chi
tiết rồi tìm các lỗ tròn xuyên suốt.

| chi tiết | lỗ tìm được | trục | tâm |
|---|---|---|---|
| đùi | Ø22,5mm (hốc servo hông) | **X** | Y −50,3 · Z 3,8 |
| bàn chân | Ø5,5mm (trục cổ chân) | **Z** | X −25,5 · Y −71,5 |

Hai lỗ đó xác định luôn hướng quay: **hông quay quanh trục X** (đùi vung
trước/sau), **cổ chân quay quanh trục Z** (bàn chân nghiêng trái/phải). Khớp
với `Jump` đặt hai bàn chân `150°/30°` đối xứng, và với rãnh servo trên sàn
rộng 11,75mm theo X — đúng bề dày thân SG90.

**Màn OLED** vẽ theo `main/display/oled_display.cc`: glyph emoji Noto 30px bên
trái, chữ bên phải. Không phải mặt hoạt hình — bo `otto-robot` mới có GIF,
nhưng bo đó dùng LCD 240×240 chứ không phải SSD1306.

> **21 tên biểu cảm nhưng chỉ 9 khuôn mặt.** `emote.json` cho thấy `Happy.eaf`
> gánh 10 tên: happy, laughing, funny, loving, embarrassed, confident,
> delicious, silly, **surprised**, **relaxed**. Nghĩa là "ngạc nhiên" và "thư
> giãn" trông y hệt "vui". Ngoài ra `neutral` ↔ `winking` bị **đổi chỗ cho
> nhau** trong bảng: gửi `[neutral]` thì robot nháy mắt, gửi `[winking]` thì nó
> mặt bình thường.

**Nút "Nói thử một lượt"** chạy đúng trình tự có thật, mốc thời gian là trung
vị đo được ngày 27/09/2026 (xem `server/README.md`): nghe → VAD chốt câu sau
800ms → STT 757ms → **cảm xúc hiện ở mốc 477ms, trước tiếng nói** → TTS 433ms.

> ⚠️ **Chân sẽ KHÔNG tự nhảy khi cắm máy thật.** Firmware phơi các động tác ra
> dưới dạng **công cụ MCP** để LLM tự gọi (`otto_controller.cc`, thuộc tính
> `action`: walk, turn, jump, swing, moonwalk, bend, shake_leg, updown,
> whirlwind_leg, sit, showcase, home…). Server trong `server/` **chưa có một
> dòng MCP nào** — nó mới gửi cảm xúc và tiếng nói. Nên robot sẽ nói và đổi mặt
> nhưng đứng im. Giả lập cho thấy chân nhảy là để biết *sẽ* thế nào sau khi
> làm cầu MCP.

## Tên tệp

Không dấu, có gạch nối. Tên gốc là tiếng Trung, đọc được nhưng phải chỉnh
`core.quotepath` của git mới hiện đúng, và một số máy cắt lớp hiển thị lỗi
phông. Tiền tố `vo-` là vỏ in ra, `lk-` là linh kiện chỉ để ướm.
