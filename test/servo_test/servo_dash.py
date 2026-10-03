"""
Bang dieu khien servo cho servo_test.ino — bam nut thay vi go lenh.

    python test/servo_test/servo_dash.py
    python test/servo_test/servo_dash.py --port COM5

Hai the:
  DIEU KHIEN  bat/tat servo, chay cac bai di co san, chinh bien do va nhip
  DUNG CHUOI  nhich tung servo mot, ghi lai thanh khung hinh, chay thu ca
              chuoi, roi xuat ra text de dan vao otto_movements.cc

Vi sao khong dung servo_cmd.py cho xong:
  servo_cmd.py mo cong roi dong lai sau moi lan chay, ma mo cong serial la Uno
  TU RESET (tin hieu DTR). Nen moi lan goi la trim, bien do, gioi han maxOn deu
  ve mac dinh. Bang nay giu cong MO suot phien.

Can: pip install pyserial   (tkinter co san trong Python tren Windows)
"""

import argparse
import io
import json
import queue
import re
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog

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

# Thu tu nay la thu tu chi so trong servo_test.ino, dung cho ca lenh G.
JOINTS = [("Hông trái",    "chân 9"),
          ("Hông phải",    "chân 11"),
          ("Cổ chân trái", "chân 10"),
          ("Cổ chân phải", "chân 6")]


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
    """Giu cong serial mo, doc nen, gui lenh."""

    def __init__(self, port, on_line):
        self.ser = serial.Serial(port, BAUD, timeout=0.2)
        self.on_line = on_line
        self.alive = True
        self.lock = threading.Lock()
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
        with self.lock:
            self.ser.write(text.encode("ascii"))
            self.ser.flush()

    def close(self):
        self.alive = False
        try:
            self.ser.close()
        except Exception:
            pass


class Dash:
    # (nhan, chu lenh, ms moi buoc de doan thoi gian cho)
    GAITS = [("Đi tới", "w", 1000), ("Đi lùi", "b", 1000),
             ("Quay trái", "l", 2000), ("Quay phải", "r", 2000),
             ("Kiễng chân", "t", 900), ("Nhảy", "j", 1000)]

    def __init__(self, root, port):
        self.root = root
        self.q = queue.Queue()
        self.busy_until = 0.0
        self.n_on = 0              # so servo dang bat, doc tu dong 'dang bat N/M'
        self.pose = [90, 90, 90, 90]
        self.frames = []           # [(ms, [4 goc]), ...]
        self.playing = False
        self.t_start = time.monotonic()
        root.title("Servo Otto — " + port)
        root.configure(padx=10, pady=10)

        self.link = Link(port, lambda s: self.q.put(s))

        top = ttk.Frame(root); top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.state = tk.StringVar(value="đang nối…")
        ttk.Label(top, textvariable=self.state, font=("Consolas", 9)).pack(side="left")
        ttk.Button(top, text="Đọc trạng thái", width=14,
                   command=lambda: self.cmd("i", 0)).pack(side="right")
        ttk.Button(top, text="Bật cả 4", width=10,
                   command=lambda: self.cmd("A", 0)).pack(side="right", padx=4)

        nb = ttk.Notebook(root); nb.grid(row=1, column=0, sticky="nsew")
        self.tab_ctrl(nb)
        self.tab_seq(nb)

        f6 = ttk.LabelFrame(root, text="Nhật ký", padding=4)
        f6.grid(row=2, column=0, sticky="nsew", pady=(8, 0))
        root.rowconfigure(2, weight=1); root.columnconfigure(0, weight=1)
        self.log = tk.Text(f6, height=11, width=86, font=("Consolas", 9),
                           bg="#101410", fg="#c8e0c0", insertbackground="#c8e0c0")
        self.log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(f6, command=self.log.yview); sb.pack(side="right", fill="y")
        self.log.config(yscrollcommand=sb.set)

        self.buttons = list(self._all_buttons(root))
        root.protocol("WM_DELETE_WINDOW", self.quit)
        self.pump()
        self.cmd("i", 0)

    # ------------------------------------------------- the DIEU KHIEN
    def tab_ctrl(self, nb):
        t = ttk.Frame(nb, padding=8); nb.add(t, text="Điều khiển")

        f1 = ttk.LabelFrame(t, text="Servo", padding=8)
        f1.grid(row=0, column=0, sticky="ew", pady=3)
        for i, (ten, chan) in enumerate(JOINTS):
            ttk.Button(f1, text="%s\n%s" % (ten, chan), width=14,
                       command=lambda k=str(i + 1): self.cmd(k, 0)
                       ).grid(row=0, column=i, padx=3)
        ttk.Button(f1, text="Giới hạn 1→2→4", width=16,
                   command=lambda: self.cmd("m", 0)).grid(row=1, column=0,
                                                          columnspan=2, pady=(6, 0))
        ttk.Label(f1, text="chỉ bật 4 khi đã có nguồn 5V ngoài",
                  foreground="#a05000").grid(row=1, column=2, columnspan=2,
                                             sticky="w", pady=(6, 0))

        f2 = ttk.LabelFrame(t, text="Dáng đi — điền số bước rồi bấm", padding=8)
        f2.grid(row=1, column=0, sticky="ew", pady=3)
        self.counts = {}
        for i, (ten, ch, ms) in enumerate(self.GAITS):
            r, c = divmod(i, 3)
            cell = ttk.Frame(f2); cell.grid(row=r, column=c, padx=4, pady=3)
            v = tk.StringVar(value="2"); self.counts[ch] = v
            ttk.Spinbox(cell, from_=1, to=20, width=3, textvariable=v,
                        justify="center").pack(side="left")
            ttk.Button(cell, text=ten, width=12,
                       command=lambda c2=ch, m=ms: self.gait(c2, m)).pack(side="left")

        f3 = ttk.LabelFrame(t, text="Biên độ & nhịp", padding=8)
        f3.grid(row=2, column=0, sticky="ew", pady=3)
        for i, (ten, ch) in enumerate([("biên độ −", ","), ("biên độ +", "."),
                                       ("chậm hơn", "<"), ("nhanh hơn", ">")]):
            ttk.Button(f3, text=ten, width=12,
                       command=lambda k=ch: self.cmd(k, 0)).grid(row=0, column=i, padx=3)
        ttk.Button(f3, text="Nhịp êm (73°/s)", width=18,
                   command=lambda: self.cmd("S", 0)).grid(row=1, column=0, columnspan=2,
                                                          padx=3, pady=(6, 0))
        ttk.Button(f3, text="Gốc Otto (188°/s)", width=18,
                   command=lambda: self.cmd("D", 0)).grid(row=1, column=2, columnspan=2,
                                                          padx=3, pady=(6, 0))

        f5 = ttk.LabelFrame(t, text="Chẩn đoán", padding=8)
        f5.grid(row=3, column=0, sticky="ew", pady=3)
        for i, (ten, ch, ms) in enumerate([("Quét thô 4 chân (X)", "X", 16000),
                                           ("Quét dải xung (P)", "P", 22000),
                                           ("Nhả hết servo", "d", 0)]):
            ttk.Button(f5, text=ten, width=20,
                       command=lambda k=ch, m=ms: self.cmd(k, m)
                       ).grid(row=0, column=i, padx=3)

    # ------------------------------------------------- the DUNG CHUOI
    def tab_seq(self, nb):
        t = ttk.Frame(nb, padding=8); nb.add(t, text="Dựng chuỗi")

        f = ttk.LabelFrame(t, text="Nhích từng servo — số là góc tuyệt đối, "
                                   "90° là tư thế nghỉ", padding=8)
        f.grid(row=0, column=0, sticky="ew")
        self.angle_lbl = []
        for i, (ten, chan) in enumerate(JOINTS):
            ttk.Label(f, text=ten, width=13).grid(row=i, column=0, sticky="w", pady=2)
            for j, d in enumerate((-10, -5, -1)):
                ttk.Button(f, text=str(d), width=4,
                           command=lambda a=i, b=d: self.nudge(a, b)
                           ).grid(row=i, column=1 + j, padx=1)
            v = tk.StringVar(value="90"); self.angle_lbl.append(v)
            ttk.Label(f, textvariable=v, width=5, anchor="center",
                      font=("Consolas", 11, "bold")).grid(row=i, column=4, padx=6)
            for j, d in enumerate((1, 5, 10)):
                ttk.Button(f, text="+" + str(d), width=4,
                           command=lambda a=i, b=d: self.nudge(a, b)
                           ).grid(row=i, column=5 + j, padx=1)
            ttk.Label(f, text=chan, foreground="#777").grid(row=i, column=8,
                                                            sticky="w", padx=(8, 0))
        ttk.Button(f, text="Tất cả về 90°", width=14,
                   command=self.center).grid(row=4, column=0, columnspan=3, pady=(8, 0))
        ttk.Button(f, text="Đọc lại từ board", width=16,
                   command=lambda: self.cmd("Q", 0)).grid(row=4, column=3, columnspan=3,
                                                          pady=(8, 0))

        g = ttk.LabelFrame(t, text="Khung hình", padding=8)
        g.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        t.rowconfigure(1, weight=1); t.columnconfigure(0, weight=1)

        bar = ttk.Frame(g); bar.grid(row=0, column=0, sticky="ew")
        ttk.Label(bar, text="thời gian tới khung này (ms)").pack(side="left")
        self.frame_ms = tk.StringVar(value="400")
        ttk.Spinbox(bar, from_=100, to=3000, increment=100, width=6,
                    textvariable=self.frame_ms).pack(side="left", padx=5)
        ttk.Button(bar, text="Ghi khung", width=12,
                   command=self.add_frame).pack(side="left", padx=3)
        ttk.Button(bar, text="Xoá khung đang chọn", width=20,
                   command=self.del_frame).pack(side="left", padx=3)
        ttk.Button(bar, text="Xoá hết", width=9,
                   command=self.clear_frames).pack(side="left", padx=3)

        self.lst = tk.Listbox(g, height=8, font=("Consolas", 10))
        self.lst.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        g.rowconfigure(1, weight=1); g.columnconfigure(0, weight=1)
        self.lst.bind("<<ListboxSelect>>", self.goto_frame)

        bar2 = ttk.Frame(g); bar2.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(bar2, text="lặp").pack(side="left")
        self.loops = tk.StringVar(value="2")
        ttk.Spinbox(bar2, from_=1, to=20, width=3,
                    textvariable=self.loops).pack(side="left", padx=4)
        ttk.Button(bar2, text="Chạy chuỗi", width=12,
                   command=self.play).pack(side="left", padx=3)
        ttk.Button(bar2, text="Xuất ra nhật ký", width=16,
                   command=self.export).pack(side="left", padx=3)
        ttk.Button(bar2, text="Lưu tệp…", width=10,
                   command=self.save).pack(side="left", padx=3)
        ttk.Button(bar2, text="Mở tệp…", width=10,
                   command=self.load).pack(side="left", padx=3)

    # ------------------------------------------------- tu the
    def send_pose(self, ms=250):
        self.link.send("G%d,%d,%d,%d,%d\n" % (tuple(self.pose) + (ms,)))
        for i, v in enumerate(self.pose):
            self.angle_lbl[i].set(str(v))

    def nudge(self, i, d):
        self.pose[i] = max(0, min(180, self.pose[i] + d))
        self.send_pose(200)

    def center(self):
        self.pose = [90, 90, 90, 90]
        self.send_pose(500)

    def add_frame(self):
        try:
            ms = max(100, min(3000, int(self.frame_ms.get())))
        except ValueError:
            ms = 400
        self.frames.append((ms, list(self.pose)))
        self.refresh_list()

    def del_frame(self):
        s = self.lst.curselection()
        if s:
            self.frames.pop(s[0]); self.refresh_list()

    def clear_frames(self):
        self.frames = []; self.refresh_list()

    def refresh_list(self):
        self.lst.delete(0, "end")
        for i, (ms, p) in enumerate(self.frames):
            self.lst.insert("end", "%2d.  %4dms   %3d %3d %3d %3d"
                            % ((i + 1, ms) + tuple(p)))

    def goto_frame(self, _e=None):
        s = self.lst.curselection()
        if not s or self.playing:
            return
        ms, p = self.frames[s[0]]
        self.pose = list(p)
        self.send_pose(ms)

    def play(self):
        if self.playing or not self.frames:
            self.put("… chưa có khung nào để chạy" if not self.frames else "… đang chạy")
            return
        try:
            n = max(1, min(20, int(self.loops.get())))
        except ValueError:
            n = 1
        if self.n_on < 4:
            self.put("!!! mới có %d/4 servo bật — bấm “Bật cả 4” trước." % self.n_on)
        self.playing = True
        threading.Thread(target=self._play, args=(n,), daemon=True).start()

    def _play(self, n):
        # Chay tren luong rieng: moi khung gui lenh G roi ngu dung bang thoi
        # gian cua khung do. Arduino noi suy nen duong di muot san.
        self.q.put(">>> chạy chuỗi %d khung × %d lần" % (len(self.frames), n))
        for k in range(n):
            for ms, p in self.frames:
                if not self.playing:
                    break
                self.link.send("G%d,%d,%d,%d,%d\n" % (tuple(p) + (ms,)))
                time.sleep(ms / 1000.0 + 0.05)
            if not self.playing:
                break
        self.playing = False
        self.q.put("<<< xong")

    def export(self):
        if not self.frames:
            self.put("… chưa có khung nào"); return
        self.put("")
        self.put("=== CHUỖI — dán nguyên khối này gửi lại cho tôi ===")
        self.put("# thứ tự: hông trái, hông phải, cổ chân trái, cổ chân phải")
        for ms, p in self.frames:
            self.put("  %4d ms   %3d %3d %3d %3d" % ((ms,) + tuple(p)))
        self.put("=== hết %d khung ===" % len(self.frames))
        self.put("")

    def save(self):
        if not self.frames:
            self.put("… chưa có khung nào"); return
        fn = filedialog.asksaveasfilename(defaultextension=".json",
                                          initialfile="chuoi.json",
                                          filetypes=[("JSON", "*.json")])
        if not fn:
            return
        with io.open(fn, "w", encoding="utf-8") as f:
            json.dump({"thu_tu": ["hong_trai", "hong_phai", "co_chan_trai",
                                  "co_chan_phai"],
                       "khung": [{"ms": m, "goc": p} for m, p in self.frames]},
                      f, ensure_ascii=False, indent=2)
        self.put("đã lưu: " + fn)

    def load(self):
        fn = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not fn:
            return
        try:
            with io.open(fn, encoding="utf-8") as f:
                d = json.load(f)
            self.frames = [(int(k["ms"]), [int(x) for x in k["goc"]])
                           for k in d["khung"]]
        except Exception as e:
            self.put("LỖI đọc tệp: %s" % e); return
        self.refresh_list()
        self.put("đã mở: %s (%d khung)" % (fn, len(self.frames)))

    # ------------------------------------------------- chung
    def _all_buttons(self, w):
        for c in w.winfo_children():
            if isinstance(c, ttk.Button):
                yield c
            yield from self._all_buttons(c)

    def gait(self, ch, ms_each):
        try:
            n = max(1, min(20, int(self.counts[ch].get())))
        except ValueError:
            n = 1
        # Moi lan mo cong la Uno reset ve mac dinh 2/2, tuc CHI HAI servo bat.
        # Bam dang di luc do thi hai con kia nam im, rat de tuong la hong.
        if self.n_on < 4:
            self.put("!!! mới có %d/4 servo bật — bấm “Bật cả 4” trước, "
                     "không thì hai con kia nằm im." % self.n_on)
        # Do thuc te: dung 1000ms moi buoc + ~400ms dat nhip + ~600ms ve nghi.
        self.cmd("%s%d" % (ch, n), n * ms_each + 1100)

    def cmd(self, text, busy_ms):
        if time.monotonic() < self.busy_until:
            self.put("… đang bận, bỏ qua: " + text); return
        self.put(">>> " + text)
        try:
            self.link.send(text)
        except Exception as e:
            self.put("LỖI gửi: %s" % e); return
        if busy_ms:
            self.busy_until = time.monotonic() + busy_ms / 1000.0
            for b in self.buttons:
                b.state(["disabled"])

    def put(self, s):
        self.log.insert("end", s + "\n")
        self.log.see("end")

    def pump(self):
        try:
            while True:
                line = self.q.get_nowait()
                # Lan BOOT dau tien la do chinh minh mo cong (DTR reset Uno),
                # chuyen binh thuong. Chi dang lo neu no hien GIUA chung —
                # luc do gan nhu chac chan servo keo tut dien ap.
                if "### BOOT ###" in line:
                    if time.monotonic() - self.t_start > 5.0:
                        self.put("!!! BOARD VỪA RESET giữa chừng — gần như chắc "
                                 "chắn servo kéo tụt điện áp. Kiểm lại nguồn 5V.")
                    else:
                        self.put("   (board khởi động — bình thường khi vừa mở cổng)")
                self.put(line)
                if "dang bat" in line or "gioi han" in line:
                    self.state.set(line.strip())
                m = re.search(r"dang bat (\d+)/(\d+)", line)
                if m:
                    self.n_on = int(m.group(1))
                m = re.match(r"\s*POSE\s+(\d+),(\d+),(\d+),(\d+)", line)
                if m:
                    self.pose = [int(x) for x in m.groups()]
                    for i, v in enumerate(self.pose):
                        self.angle_lbl[i].set(str(v))
        except queue.Empty:
            pass
        if self.busy_until and time.monotonic() >= self.busy_until:
            self.busy_until = 0.0
            for b in self.buttons:
                b.state(["!disabled"])
        self.root.after(50, self.pump)

    def quit(self):
        self.playing = False
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
