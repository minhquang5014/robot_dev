"""
Bang dieu khien servo cho servo_test.ino — bam nut thay vi go lenh.

    python test/servo_test/servo_dash.py
    python test/servo_test/servo_dash.py --port COM5

Vi sao khong dung servo_cmd.py cho xong:
  servo_cmd.py mo cong roi dong lai sau moi lan chay, ma mo cong serial la Uno
  TU RESET (tin hieu DTR). Nen moi lan goi la trim, bien do, gioi han maxOn deu
  ve mac dinh — do trim kieu do khong xong duoc. Bang nay giu cong MO suot
  phien, nen trang thai con nguyen giua cac lan bam.

Can: pip install pyserial   (tkinter co san trong Python tren Windows)
"""

import argparse
import io
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk

for _n in ("stdout", "stderr"):
    _s = getattr(sys, _n)
    if hasattr(_s, "buffer"):
        setattr(sys, _n, io.TextIOWrapper(_s.buffer, encoding="utf-8",
                                          errors="replace", line_buffering=True))

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    sys.exit("Thieu pyserial. Chay:  pip install pyserial")

BAUD = 115200
BOOT_S = 2.5          # Uno tu reset khi mo cong, phai cho no khoi dong xong


def find_port(explicit=None):
    if explicit:
        return explicit
    ports = list(list_ports.comports())
    for p in ports:
        blob = "%s %s" % (p.description or "", p.manufacturer or "")
        if any(k in blob.lower() for k in ("arduino", "ch340", "usb-serial", "wch")):
            return p.device
        if p.vid == 0x2341:                     # ma nha san xuat Arduino
            return p.device
    return ports[0].device if len(ports) == 1 else None


class Link:
    """Giu cong serial mo, doc nen, gui lenh tu hang doi."""

    def __init__(self, port, on_line):
        self.ser = serial.Serial(port, BAUD, timeout=0.2)
        self.on_line = on_line
        self.alive = True
        self.last_rx = time.monotonic()
        threading.Thread(target=self._reader, daemon=True).start()
        time.sleep(BOOT_S)
        self.ser.reset_input_buffer()

    def _reader(self):
        buf = b""
        while self.alive:
            try:
                n = self.ser.in_waiting
                chunk = self.ser.read(n if n else 1)
            except Exception:
                break
            if not chunk:
                continue
            self.last_rx = time.monotonic()
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                txt = line.decode("utf-8", "replace").rstrip("\r")
                # Luc mo cong, tin hieu DTR reset Uno va duong truyen co vai
                # byte rac. Bo di cho nhat ky sach.
                if "�" in txt and len(txt) < 8:
                    continue
                self.on_line(txt)

    def send(self, text):
        # Gui CA CHUOI mot lan. Tach ra tung ky tu thi `w2` se bi doc thanh
        # `w` roi `2`, tuc di 4 buoc xong bat/tat servo 2 — da vap.
        self.ser.write(text.encode("ascii"))
        self.ser.flush()

    def close(self):
        self.alive = False
        try:
            self.ser.close()
        except Exception:
            pass


class Dash:
    JOINTS = [("1", "Hông trái",    "chân 9"),
              ("2", "Hông phải",    "chân 11"),
              ("3", "Cổ chân trái", "chân 10"),
              ("4", "Cổ chân phải", "chân 6")]

    # (nhan, chu lenh, co nhan so buoc khong, ms moi buoc de doan thoi gian)
    GAITS = [("Đi tới",      "w", True,  1000),
             ("Đi lùi",      "b", True,  1000),
             ("Quay trái",   "l", True,  2000),
             ("Quay phải",   "r", True,  2000),
             ("Kiễng chân",  "t", True,   900),
             ("Nhảy",        "j", True,  1000)]

    def __init__(self, root, port):
        self.root = root
        self.q = queue.Queue()
        self.busy_until = 0.0
        root.title("Servo Otto — " + port)
        root.configure(padx=10, pady=10)

        self.link = Link(port, lambda s: self.q.put(s))

        # ---- hang trang thai ----
        top = ttk.Frame(root); top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.state = tk.StringVar(value="đang nối…")
        ttk.Label(top, textvariable=self.state,
                  font=("Consolas", 9)).pack(side="left")
        ttk.Button(top, text="Đọc trạng thái", width=14,
                   command=lambda: self.cmd("i", 0)).pack(side="right")

        # ---- bat/tat tung servo ----
        f1 = ttk.LabelFrame(root, text="Servo", padding=8)
        f1.grid(row=1, column=0, sticky="ew", pady=4)
        for i, (key, ten, chan) in enumerate(self.JOINTS):
            ttk.Button(f1, text="%s\n%s" % (ten, chan), width=14,
                       command=lambda k=key: self.cmd(k, 0)
                       ).grid(row=0, column=i, padx=3)
        ttk.Button(f1, text="Bật cả 4", width=14,
                   command=lambda: self.cmd("A", 0)).grid(row=1, column=0,
                                                          pady=(6, 0))
        ttk.Button(f1, text="Giới hạn 1→2→4", width=14,
                   command=lambda: self.cmd("m", 0)).grid(row=1, column=1,
                                                          pady=(6, 0))
        ttk.Label(f1, text="chỉ bật 4 khi đã có nguồn 5V ngoài",
                  foreground="#a05000").grid(row=1, column=2, columnspan=2,
                                             sticky="w", pady=(6, 0))

        # ---- dang di ----
        f2 = ttk.LabelFrame(root, text="Dáng đi — điền số bước rồi bấm", padding=8)
        f2.grid(row=2, column=0, sticky="ew", pady=4)
        self.counts = {}
        for i, (ten, ch, has_n, ms) in enumerate(self.GAITS):
            r, c = divmod(i, 3)
            cell = ttk.Frame(f2); cell.grid(row=r, column=c, padx=4, pady=3)
            v = tk.StringVar(value="2")
            self.counts[ch] = v
            ttk.Spinbox(cell, from_=1, to=20, width=3, textvariable=v,
                        justify="center").pack(side="left")
            ttk.Button(cell, text=ten, width=12,
                       command=lambda c2=ch, m=ms: self.gait(c2, m)).pack(side="left")

        # ---- bien do / chu ky ----
        f3 = ttk.LabelFrame(root, text="Biên độ & nhịp", padding=8)
        f3.grid(row=3, column=0, sticky="ew", pady=4)
        for i, (ten, ch) in enumerate([("biên độ −", ","), ("biên độ +", "."),
                                       ("chậm hơn", "<"), ("nhanh hơn", ">")]):
            ttk.Button(f3, text=ten, width=12,
                       command=lambda k=ch: self.cmd(k, 0)).grid(row=0, column=i, padx=3)

        # ---- can chinh ----
        f4 = ttk.LabelFrame(root, text="Căn chỉnh — tác động lên servo vừa chọn ở trên",
                            padding=8)
        f4.grid(row=4, column=0, sticky="ew", pady=4)
        row = [("về 90°", "c"), ("−5°", "["), ("−1°", "-"),
               ("+1°", "+"), ("+5°", "]"), ("lấy trim", "z")]
        for i, (ten, ch) in enumerate(row):
            ttk.Button(f4, text=ten, width=9,
                       command=lambda k=ch: self.cmd(k, 0)).grid(row=0, column=i, padx=2)
        ttk.Label(f4, text="Lắp càng servo khi đang ở 90°. Chỉnh xong bấm "
                           "“lấy trim”, chép 4 số vào SetTrims().",
                  foreground="#555").grid(row=1, column=0, columnspan=6,
                                          sticky="w", pady=(6, 0))

        # ---- chan doan ----
        f5 = ttk.LabelFrame(root, text="Chẩn đoán", padding=8)
        f5.grid(row=5, column=0, sticky="ew", pady=4)
        ttk.Button(f5, text="Quét thô 4 chân (X)", width=20,
                   command=lambda: self.cmd("X", 16000)).grid(row=0, column=0, padx=3)
        ttk.Button(f5, text="Quét dải xung (P)", width=18,
                   command=lambda: self.cmd("P", 22000)).grid(row=0, column=1, padx=3)
        ttk.Button(f5, text="Nhả hết servo", width=14,
                   command=lambda: self.cmd("d", 0)).grid(row=0, column=2, padx=3)

        # ---- nhat ky ----
        f6 = ttk.LabelFrame(root, text="Nhật ký", padding=4)
        f6.grid(row=6, column=0, sticky="nsew", pady=(6, 0))
        root.rowconfigure(6, weight=1); root.columnconfigure(0, weight=1)
        self.log = tk.Text(f6, height=14, width=78, font=("Consolas", 9),
                           bg="#101410", fg="#c8e0c0", insertbackground="#c8e0c0")
        self.log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(f6, command=self.log.yview); sb.pack(side="right", fill="y")
        self.log.config(yscrollcommand=sb.set)

        self.buttons = [w for w in self._all_buttons(root)]
        root.protocol("WM_DELETE_WINDOW", self.quit)
        self.pump()
        self.cmd("i", 0)

    def _all_buttons(self, w):
        for c in w.winfo_children():
            if isinstance(c, ttk.Button):
                yield c
            yield from self._all_buttons(c)

    # ---------------------------------------------------------------
    def gait(self, ch, ms_each):
        try:
            n = max(1, min(20, int(self.counts[ch].get())))
        except ValueError:
            n = 1
        # Do thuc te tren may that: dung 1000ms moi buoc di (chu ky), cong
        # them ~600ms home() o cuoi bai. Cho du 900ms cho chac.
        self.cmd("%s%d" % (ch, n), n * ms_each + 900)

    def cmd(self, text, busy_ms):
        if time.monotonic() < self.busy_until:
            self.put("… đang bận, bỏ qua: " + text)
            return
        self.put(">>> " + text)
        try:
            self.link.send(text)
        except Exception as e:
            self.put("LỖI gửi: %s" % e)
            return
        if busy_ms:
            self.busy_until = time.monotonic() + busy_ms / 1000.0
            for b in self.buttons:
                b.state(["disabled"])

    def put(self, s):
        self.log.insert("end", s + "\n")
        self.log.see("end")

    def pump(self):
        """Chay 20 lan/giay tren luong giao dien: do nhat ky, mo khoa nut."""
        try:
            while True:
                line = self.q.get_nowait()
                if "### BOOT ###" in line:
                    self.put("!!! BOARD VỪA RESET — gần như chắc chắn servo "
                             "kéo tụt điện áp. Kiểm lại nguồn 5V.")
                self.put(line)
                if "dang bat" in line or "gioi han" in line:
                    self.state.set(line.strip())
        except queue.Empty:
            pass
        if self.busy_until and time.monotonic() >= self.busy_until:
            self.busy_until = 0.0
            for b in self.buttons:
                b.state(["!disabled"])
        self.root.after(50, self.pump)

    def quit(self):
        self.link.close()
        self.root.destroy()


def main():
    ap = argparse.ArgumentParser(description="Bang dieu khien servo Otto")
    ap.add_argument("--port")
    a = ap.parse_args()
    port = find_port(a.port)
    if not port:
        sys.exit("Khong tim thay cong. Chi dinh bang --port COM3")
    root = tk.Tk()
    Dash(root, port)
    root.mainloop()


if __name__ == "__main__":
    main()
