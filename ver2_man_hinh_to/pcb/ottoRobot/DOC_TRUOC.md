# Otto Robot – Tommy build (rev 1.1-k2)

Dựa trên ottoRobot V1.1 của txp (ottodiy.tech), phát hành theo
[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).
Bản này là tác phẩm phái sinh nên giữ nguyên license đó: được sửa và chia sẻ
lại nếu ghi công tác giả gốc và giữ cùng license, **không dùng thương mại**.

## Mở project
1. Giải nén, mở `ottoRobot.kicad_pro` bằng KiCad 10. KiCad sẽ hỏi nâng cấp định dạng file, bấm đồng ý.
2. Thư viện symbol và footprint nằm sẵn trong thư mục (`ottoRobot.kicad_sym`, `ottoRobot.pretty`).
3. Nếu chưa thấy đồng phủ: bấm phím **B** để đổ lại.

## Đã có trong project
- **Sơ đồ nguyên lý:** khớp 100% với netlist gốc (39/39 net).
- **PCB:** đúng vị trí, hướng xoay và kích thước từng pad như bản gốc. Có 328 đoạn mạch, 75 via, đồng GND ở cả hai mặt. Sau khi đổ đồng: 0 kết nối thiếu.
- **Silkscreen:** giữ khung linh kiện và ký hiệu (C1, R2, HDR1…) của bản gốc. Chữ Trung được thay bằng nhãn tiếng Việt không dấu:
  - NAU: dây nâu (GND) quay ra ngoài
  - DUI/CHAN: hàng trên đùi, hàng dưới bàn chân
  - TRAI/PHAI: tay trái/phải
  - MO RONG: servo mở rộng
  - + PIN −, LOA, BOOT
- Chữ in là hình vẽ của board, không gắn với footprint, nên nếu di chuyển linh kiện thì phải sửa chữ in bằng tay.
- **Header servo HDR1/HDR3/HDR4** loại 2x3: pad 1–2 GND, 3–4 VBAT_IN, 5–6 tín hiệu. Pad GND nối qua vùng đồng.
- Board dày **1.2 mm** (chọn khi đặt mạch).

## Lưu ý
- Khoảng cách mạch nhỏ nhất **0.1 mm (4 mil)**, lỗ via **0.2 mm**. Xưởng ở Việt Nam cần xác nhận làm được.
- Bản gốc nối IO2 và IO45 xuống GND bằng hai đoạn mạch ngắn không có trong sơ đồ. Bản này đã bỏ hai đoạn đó.
- Các lỗi DRC "hole clearance" ở mic U7 là cố ý (lỗ thu âm nằm trong vòng GND).
- Chưa có teardrop như bản gốc. Trong KiCad 10: **Edit → Edit Teardrops** để thêm.

## GPIO còn trống (cho camera)
- **Trống:** IO1, IO13, IO40, IO41, IO42, IO47, IO48.
- **Nhãn ML307 nhưng không nối đi đâu:** IO2, IO43, IO44.
- **Nếu bỏ servo tay HDR4:** IO8, IO12.
- IO45 là chân strapping. IO35–37 bị PSRAM của bản N16R8 chiếm, không dùng được.
