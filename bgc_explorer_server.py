#!/usr/bin/env python3
# =====================================================================
#  BGC EXPLORER SERVER - website cho NGUOI DUNG xem chuoi BGC (fair-launch) qua URL.
#  Dung: python bgc_explorer_server.py <datadir> [port] [--regtest]
#  Doc chuoi tu datadir cua node dang chay (chi doc them khoi moi moi 10s, khong nap lai
#  ca chuoi), render HTML tu dong lam moi -> cong dong "thay" mang.
# =====================================================================
import os, sys, html, time, threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bgcfl_engine import Chain, COIN, MAIN, REGTEST

MSG="BGC: dong tien hau luong tu, sinh ra cho ky nguyen AI va robot."
CHAIN=None; PAGE=b""

def render(chain):
    h=chain.height(); supply=chain.audit_supply(); MAX_SUPPLY=chain.p.max_supply()
    def subsidy(x): return chain.p.subsidy(x)
    bal=chain.balances()
    top="".join(f"<tr><td><code>{html.escape(a[:34])}…</code></td><td class=r>{v/COIN:,.2f}</td></tr>"
                for a,v in sorted(bal.items(),key=lambda x:-x[1])[:12])
    rows=[]
    for blk in reversed(chain.blocks[-20:]):
        cb=blk.txs[0].vout[0]
        rows.append(f"<tr><td>#{blk.index}</td><td><code>{blk.hash()[:18]}…</code></td>"
                    f"<td>{len(blk.txs)}</td><td class=r>{cb.value/COIN:g}</td>"
                    f"<td><code>{html.escape(cb.address[:20])}…</code></td></tr>")
    pct=100*supply/MAX_SUPPLY if MAX_SUPPLY else 0
    return f"""<!doctype html><html lang=vi><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><meta http-equiv=refresh content=5>
<title>BGC Explorer</title><style>
:root{{--bg:#0b0e14;--card:#141a24;--line:#263040;--mut:#8aa0b4;--ok:#49d17a;--ac:#5aa0ff}}
@media(prefers-color-scheme:light){{:root:not([data-theme=dark]){{--bg:#f3f6fa;--card:#fff;--line:#d7dee8;--mut:#5a6b7b;--ok:#128a43;--ac:#1763d6}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:#dfe8f0;font:15px/1.55 system-ui,Segoe UI,Roboto,sans-serif;padding:18px}}
@media(prefers-color-scheme:light){{body{{color:#1b2430}}}}
.msg{{font-size:17px;font-weight:600;color:var(--ac);margin:0 0 4px}} .sub{{color:var(--mut);margin-bottom:16px;font-size:13px}}
.k{{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:16px}}
.cell{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 16px;min-width:150px;flex:1}}
.cell .n{{font-size:22px;font-weight:700}} .cell .l{{color:var(--mut);font-size:12px}}
.bar{{height:8px;background:var(--line);border-radius:6px;overflow:hidden;margin-top:6px}} .bar>i{{display:block;height:100%;background:var(--ok);width:{pct:.2f}%}}
table{{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;margin-bottom:16px}}
th,td{{padding:8px 12px;border-bottom:1px solid var(--line);text-align:left;font-size:13px}} th{{color:var(--mut);font-weight:600}} .r{{text-align:right}}
code{{background:rgba(120,140,170,.18);padding:1px 5px;border-radius:5px;font-size:12px}} h3{{margin:18px 0 8px;font-size:14px}}
</style></head><body>
<p class=msg>⬡ {html.escape(MSG)}</p>
<p class=sub>Explorer cong khai · chu ky khang luong tu (XMSS) · phat hanh fair-launch PoW · tu lam moi 5s</p>
<div class=k>
 <div class=cell><div class=n>{h}</div><div class=l>Chieu cao (so khoi)</div></div>
 <div class=cell><div class=n>{supply/COIN:,.0f}</div><div class=l>Da phat hanh (BGC)</div><div class=bar><i></i></div></div>
 <div class=cell><div class=n>{subsidy(h)/COIN:g}</div><div class=l>Phan thuong khoi hien tai</div></div>
 <div class=cell><div class=n>{MAX_SUPPLY/COIN:,.0f}</div><div class=l>Tong toi da (co dinh)</div></div>
</div>
<h3>20 khoi gan nhat</h3>
<table><tr><th>Khoi</th><th>Hash</th><th>Tx</th><th class=r>Thuong</th><th>Nguoi dao</th></tr>{''.join(rows)}</table>
<h3>Vi nhieu BGC nhat</h3>
<table><tr><th>Dia chi</th><th class=r>So du (BGC)</th></tr>{top}</table>
<p class=sub>Du lieu doc truc tiep tu chuoi; ai cung chay node + explorer de TU KIEM. Khong co premine.</p>
</body></html>"""

def refresher():
    global PAGE
    while True:
        try:
            CHAIN.load()                              # chi doc cac khoi moi them vao file
            PAGE=render(CHAIN).encode()
        except Exception as e:
            print("[explorer] loi doc chuoi:", e)
        time.sleep(10)

class H(BaseHTTPRequestHandler):
    def do_GET(s):
        page=PAGE or b"dang nap chuoi..."
        s.send_response(200); s.send_header("Content-Type","text/html; charset=utf-8")
        s.send_header("Content-Length",str(len(page))); s.end_headers(); s.wfile.write(page)
    def log_message(s,*a): pass

def main():
    global CHAIN
    args=[a for a in sys.argv[1:] if a!="--regtest"]
    DATADIR=args[0] if args else "bgcfl_data"
    port=int(args[1]) if len(args)>1 else 8800
    CHAIN=Chain(datadir=DATADIR, params=REGTEST if "--regtest" in sys.argv else MAIN)
    threading.Thread(target=refresher, daemon=True).start()
    srv=ThreadingHTTPServer(("0.0.0.0",port),H)
    print(f"[explorer] phuc vu tai http://0.0.0.0:{port}  (doc datadir: {DATADIR})")
    print(f"[explorer] mo tren trinh duyet; lien may: thay 0.0.0.0 bang IP may chu.")
    try: srv.serve_forever()
    except KeyboardInterrupt: srv.shutdown()

if __name__=="__main__": main()
