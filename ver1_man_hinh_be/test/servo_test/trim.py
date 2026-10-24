#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Do trim servo qua serial, chiu duoc viec Uno reset moi lan mo cong.

    python trim.py                      # ve giua ca 4, xem trang thai
    python trim.py --nhich 1=+3 3=-2    # nhich hong trai +3, co chan trai -2
    python trim.py --chot               # chot goc hien tai thanh trim (lenh z)
    python trim.py --thu w              # chay thu mot dang di

So servo theo dung phim cua sketch (va dung thu tu SetTrims):
    1 LEFT_LEG   2 RIGHT_LEG   3 LEFT_FOOT   4 RIGHT_FOOT

VI SAO CAN TEP NAY: mo cong serial la Uno reset, trim ve 0 het. Nen moi lan
chay, script doc trim da luu trong trim.json roi dat lai bang `a<goc>` + `z`
truoc khi lam viec moi. Khong co buoc do thi do xong con nay la mat con truoc.
"""
import argparse
import json
import os
import sys
import time

try:
    import serial
except ImportError:
    sys.exit("Can pyserial:  python -m pip install pyserial")

HERE = os.path.dirname(os.path.abspath(__file__))
LUU = os.path.join(HERE, "trim.json")
TEN = {1: "LEFT_LEG", 2: "RIGHT_LEG", 3: "LEFT_FOOT", 4: "RIGHT_FOOT"}


def doc_luu() -> dict:
    try:
        with open(LUU, encoding="utf-8") as f:
            return {int(k): int(v) for k, v in json.load(f).items()}
    except (OSError, ValueError):
        return {}


def ghi_luu(t: dict):
    with open(LUU, "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in sorted(t.items())}, f, indent=2)


class Bang:
    def __init__(self, cong, baud=115200):
        self.sp = serial.Serial(cong, baud, timeout=0.3)
        time.sleep(2.2)              # Uno vua reset, cho bootloader xong
        self.sp.reset_input_buffer()

    def gui(self, s, cho=0.35):
        self.sp.write(s.encode())
        self.sp.flush()
        time.sleep(cho)
        return self.sp.read_all().decode("utf-8", "replace")

    def dong(self):
        self.sp.close()


def dat_trim(b: Bang, so: int, tri: int):
    """Dat trim cua servo `so` thanh `tri` tu trang thai vua reset (trim=0).

    `z` lay (goc hien tai - 90) cong vao trim. Vua reset thi trim=0, nen cho
    goc toi 90+tri roi bam z la trim thanh dung `tri`.
    """
    # Phim so la BAT/TAT, va `sel` chi duoc gan khi BAT (servo_test.ino:193).
    # Sau lenh `A` thi ca 4 dang bat, bam mot lan la TAT. Bam hai lan: tat roi
    # bat lai — ket thuc o trang thai bat va dang duoc chon.
    b.gui(str(so))
    b.gui(str(so), cho=0.5)
    if tri:
        b.gui("a%d" % (90 + tri), cho=0.8)
        b.gui("z")
    b.gui("c", cho=0.6)              # ve giua (da co trim)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cong", default="COM3")
    p.add_argument("--nhich", nargs="*", default=[],
                   help="vd 1=+3 3=-2 — cong them vao trim dang co")
    p.add_argument("--chot", action="store_true",
                   help="bam z: lay goc hien tai lam trim (dung sau khi tu tay chinh)")
    p.add_argument("--thu", help="chay thu mot dang di: w b l r j t x")
    p.add_argument("--cho", type=float, default=6.0,
                   help="giay cho ket qua --thu (x can ~14)")
    p.add_argument("--tho", nargs="*", default=[],
                   help="gui lenh THO, bo qua buoc bat/dat trim. vd --tho d 1 1 c")
    p.add_argument("--dat", nargs="*", default=[],
                   help="vd 1=5 — dat thang trim, khong cong don")
    a = p.parse_args()

    trim = doc_luu()
    for c in a.dat:
        k, v = c.split("="); trim[int(k)] = int(v)
    for c in a.nhich:
        k, v = c.split("="); trim[int(k)] = trim.get(int(k), 0) + int(v)

    b = Bang(a.cong)
    try:
        if a.tho:
            # Khong bat gi, khong dat trim — dung khi servo dang ket va
            # can nha ra truoc, ep ve 90 luc dang ket la no gong va nong.
            for c in a.tho:
                print(b.gui(c, cho=0.8), end="")
            print(b.gui("i", cho=0.8))
            return
        b.gui("A", cho=1.0)                      # bat ca 4 (can nguon 5V ngoai)
        for so in (1, 2, 3, 4):
            dat_trim(b, so, trim.get(so, 0))
        if a.chot:
            for so in (1, 2, 3, 4):
                b.gui(str(so)); b.gui("z")
        if a.thu:
            print(b.gui(a.thu, cho=a.cho))
        print(b.gui("i", cho=0.8))
    finally:
        b.dong()

    ghi_luu(trim)
    print("trim dang luu:", {TEN[k]: v for k, v in sorted(trim.items())})
    print("-> SetTrims(%d, %d, %d, %d)"
          % tuple(trim.get(i, 0) for i in (1, 2, 3, 4)))


if __name__ == "__main__":
    main()
