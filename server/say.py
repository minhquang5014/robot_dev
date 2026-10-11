#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Dieu khien robot tu may tinh, khoi phai noi.

    python say.py "nhay di"              # y het nhu vua noi cau do
    python say.py "cau co khoe khong"
    python say.py --do dance             # ban thang dong tac, khong qua LLM
    python say.py --do walk --steps 4
    python say.py --liet-ke              # cac dong tac hop le

Mac dinh goi len server tren Fly. Dung --url http://127.0.0.1:8000 de thu may
minh. Neu co nhieu robot cung ket noi thi them --device <Device-Id>.

Vi sao co --do: thu dang di phai lap lai hang chuc lan, ma moi lan qua LLM la
mot luot goi Groq (ban mien phi chi 20 STT/phut) cong mot luot TTS. --do ban
thang lenh MCP xuong chan, khong ton gi ca.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

MAC_DINH = "https://xiaozhi-esp32-server.fly.dev"


def lay_mat_khau(tu_dong_lenh: str = None) -> str:
    """--token, roi bien moi truong XZ_CTRL_TOKEN, roi server/.env.

    Doc .env de khoi phai dat bien moi lan mo terminal. Tep do da nam trong
    .gitignore nen mat khau khong lot vao git.
    """
    if tu_dong_lenh:
        return tu_dong_lenh
    mk = os.environ.get("XZ_CTRL_TOKEN", "").strip()
    if mk:
        return mk
    env = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        with open(env, encoding="utf-8") as f:
            for dong in f:
                dong = dong.strip()
                if dong.startswith("XZ_CTRL_TOKEN=") and not dong.startswith("#"):
                    return dong.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""

DONG_TAC = ["walk", "walk_back", "turn_left", "turn_right", "step", "step_back",
            "pivot_left", "pivot_right", "jump", "dance", "celebrate",
            "tiptoe", "sway", "windup", "home"]


def goi(url: str, duong_dan: str, body: dict, mat_khau: str = ""):
    if not mat_khau:
        print("Thieu mat khau. Dat XZ_CTRL_TOKEN trong server/.env, hoac dung --token.",
              file=sys.stderr)
        sys.exit(2)
    req = urllib.request.Request(
        url.rstrip("/") + duong_dan,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + mat_khau},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        chi_tiet = e.read().decode("utf-8", "replace").strip()
        print("Loi %d: %s" % (e.code, chi_tiet), file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print("Khong goi duoc %s: %s" % (url, e.reason), file=sys.stderr)
        sys.exit(1)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("text", nargs="*", help="cau muon robot nghe")
    p.add_argument("--do", dest="dong_tac", help="ban thang mot dong tac")
    p.add_argument("--steps", type=int, default=0, help="so buoc (0 = mac dinh)")
    p.add_argument("--device", help="Device-Id khi co nhieu robot")
    p.add_argument("--url", default=MAC_DINH)
    p.add_argument("--token", help="mat khau; mac dinh lay tu XZ_CTRL_TOKEN hoac .env")
    p.add_argument("--liet-ke", action="store_true", help="in cac dong tac hop le")
    a = p.parse_args()

    if a.liet_ke:
        print("  ".join(DONG_TAC))
        return

    if a.dong_tac:
        if a.dong_tac not in DONG_TAC:
            print("Dong tac khong hop le. Chon: " + "  ".join(DONG_TAC), file=sys.stderr)
            sys.exit(2)
        body = {"action": a.dong_tac, "steps": a.steps}
        if a.device:
            body["device"] = a.device
        print(json.dumps(goi(a.url, "/xiaozhi/do", body, lay_mat_khau(a.token)),
                         ensure_ascii=False))
        return

    cau = " ".join(a.text).strip()
    if not cau:
        p.error("can mot cau, hoac dung --do <dong tac>")
    body = {"text": cau}
    if a.device:
        body["device"] = a.device
    print(json.dumps(goi(a.url, "/xiaozhi/say", body, lay_mat_khau(a.token)),
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
