"""
Gui lenh cho servo_test.ino qua serial.

    python test/servo_test/servo_cmd.py                 # che do go tay
    python test/servo_test/servo_cmd.py X               # chay mot lenh roi thoat
    python test/servo_test/servo_cmd.py 1 c a45 z       # chay lien tiep nhieu lenh
    python test/servo_test/servo_cmd.py --port COM5 X   # chi dinh cong

Vi sao khong dung `arduino-cli monitor`:
  - Script nay tu tim cong, khong phai nho COM may.
  - Chay duoc mot chuoi lenh lien tiep, tien khi do trim hoac lap lai bai test.
  - Che do mot lenh biet CHO cho dong tac chay xong roi moi thoat. Servo chay
    thi Arduino im hoan toan vai giay, neu chi doi "khong con chu nao nua" mot
    cach ngay tho thi se cat giua chung (da vap dung loi nay).

Can: pip install pyserial
"""

import argparse
import io
import sys
import threading
import time

# Console Windows mac dinh la cp1252, in ky tu la se no UnicodeEncodeError
# ngay giua luc chay. Ep UTF-8 truoc khi lam bat cu viec gi khac.
for _name in ("stdout", "stderr"):
    _s = getattr(sys, _name)
    if hasattr(_s, "buffer"):
        setattr(sys, _name, io.TextIOWrapper(_s.buffer, encoding="utf-8",
                                             errors="replace", line_buffering=True))

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    sys.exit("Thieu pyserial. Chay:  pip install pyserial")

BAUD = 115200

# Lenh `X` quet ca 4 chan, moi chan ~3.5s va Arduino KHONG in gi trong luc do.
# Nguong im phai lon hon khoang lang do, neu khong se tuong da xong.
QUIET_S = 5.0
MAX_WAIT_S = 60.0

# Boot xong moi nhan lenh. Uno tu reset khi mo cong serial (tin hieu DTR).
BOOT_S = 2.5


def find_port(explicit=None):
    if explicit:
        return explicit
    ports = list(list_ports.comports())
    for p in ports:
        blob = "%s %s" % (p.description or "", p.manufacturer or "")
        if any(k in blob.lower() for k in ("arduino", "ch340", "usb-serial", "wch")):
            return p.device
    if len(ports) == 1:
        return ports[0].device
    if not ports:
        sys.exit("Khong thay cong serial nao. Cam Arduino vao roi thu lai.")
    sys.exit("Co nhieu cong, chon bang --port:\n  " +
             "\n  ".join("%s  %s" % (p.device, p.description) for p in ports))


def drain(ser, quiet=QUIET_S, maxw=MAX_WAIT_S, show=True):
    """Doc cho toi khi Arduino im `quiet` giay, hoac het `maxw` giay."""
    t0 = last = time.time()
    while time.time() - t0 < maxw:
        line = ser.readline()
        if line:
            last = time.time()
            if show:
                sys.stdout.write(line.decode("ascii", "replace"))
        elif time.time() - last > quiet:
            return


def run_batch(ser, cmds):
    # Phai NGU du BOOT_S truoc da. Uno chua boot xong thi chua in gi, neu
    # do quiet ngay thi tuong la da xong va banner se lot xuong duoi lenh.
    time.sleep(BOOT_S)
    drain(ser, quiet=1.0, maxw=4.0, show=False)          # bo banner luc boot
    print("--- Uno san sang ---")
    for c in cmds:
        print("\n>>>>> %s" % c)
        ser.write(c.encode())        # ca chuoi mot lan, de 'a45' khong bi dut
        drain(ser)


def run_interactive(ser):
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            try:
                line = ser.readline()
            except Exception:
                return
            if line:
                sys.stdout.write(line.decode("ascii", "replace"))

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    time.sleep(BOOT_S)
    print("\n--- go lenh roi Enter. Ctrl+C de thoat. `h` de xem bang lenh ---")
    try:
        while True:
            cmd = input()
            if cmd.strip() in ("q", "quit", "exit"):
                break
            if cmd:
                # Gui ca dong mot lan. Neu go tung ky tu cach nhau thi lenh
                # dang 'a45' se hong: sketch peek() tim chu so ngay sau 'a'.
                ser.write(cmd.encode())
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        stop.set()
        time.sleep(0.3)
        print("\n-- thoat --")


def main():
    ap = argparse.ArgumentParser(description="Gui lenh cho servo_test.ino")
    ap.add_argument("cmds", nargs="*", help="Lenh chay lien tiep; bo trong = go tay")
    ap.add_argument("--port", help="VD: COM3. Bo trong thi tu tim")
    args = ap.parse_args()

    port = find_port(args.port)
    print("Cong: %s @ %d" % (port, BAUD))
    ser = serial.Serial(port, BAUD, timeout=0.2)
    try:
        if args.cmds:
            run_batch(ser, args.cmds)
        else:
            run_interactive(ser)
    finally:
        ser.close()


if __name__ == "__main__":
    main()
