#!/usr/bin/env python3
# Gop tat ca module BGC thanh MOT FILE duy nhat: BGC_Miner_1file.py
import re

ORDER = ["btclib","bigcoin_pq","bgc_secure","bgcfl_engine","bgcfl_wallet","bgcfl_genesis","run_miner","bgc_app"]
CUT_MAIN = {"run_miner","bgcfl_genesis"}   # bo def main() cua 2 module nay (giu bgc_app.main)

HEADER = '''#!/usr/bin/env python3
# =====================================================================
#  BGC MINER - MOT FILE DUY NHAT (tu chua tat ca). Gui file nay cho may khac:
#  chay la DAO ra BGC, BGC hien trong vi, va CHUYEN QUA LAI duoc.
#  Mac dinh tieng Duc + chon ngon ngu. Tu tao genesis ben trong (khong can file phu).
#  Chay:   python BGC_Miner_1file.py                 (mo trinh duyet, dao solo)
#          python BGC_Miner_1file.py --peers IP:9333 (tham gia mang, chuyen qua lai)
#  (Dong goi .exe:  pyinstaller --onefile --name BGC-Miner BGC_Miner_1file.py)
# =====================================================================
import hashlib, hmac, struct, json, subprocess, os, time, sys, socket, threading, argparse, functools, webbrowser, io, base64, math, re, secrets
from decimal import Decimal, InvalidOperation
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
try:
    import qrcode, qrcode.image.svg
    HAS_QR=True
except Exception:
    HAS_QR=False
print=functools.partial(print, flush=True)
'''

def strip(mod, src):
    # bo khoi __main__
    src = re.split(r'\nif __name__\s*==', src)[0]
    # bo def main() (va phan sau) cho cac module chi dinh
    if mod in CUT_MAIN:
        i = src.find("\ndef main(")
        if i!=-1: src = src[:i]
    out=[]
    for ln in src.splitlines():
        s=ln.rstrip("\n")
        # bo import/from TOP-LEVEL (khong thut dau); giu import thut dau trong ham
        if re.match(r'^(import |from )', s): continue
        if re.match(r'^\s*sys\.path\.insert', s): continue
        if re.match(r'^print=functools\.partial', s): continue
        if 'import bgcfl_genesis' in s: continue      # thay bang build() noi tuyen
        if 'import run_miner' in s: continue
        out.append(s)
    body="\n".join(out)
    # sua tham chieu cheo
    body=body.replace("bgcfl_genesis.build()","build()")
    for name in ("MinerNode","load_genesis","parse_peers","start_reconnector"):
        body=body.replace("R."+name, name)
    return body.strip("\n")

parts=[HEADER]
for mod in ORDER:
    with open(mod+".py",encoding="utf-8") as f: src=f.read()
    parts.append(f"\n# ================= {mod} =================\n"+strip(mod,src))
parts.append('\nif __name__=="__main__": sys.exit(main())\n')
with open("BGC_Miner_1file.py","w",encoding="utf-8") as f: f.write("\n".join(parts))
print("BGC_Miner_1file.py da tao:", sum(len(p) for p in parts), "ky tu")
