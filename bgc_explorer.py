#!/usr/bin/env python3
# =====================================================================
#  BGC EXPLORER - xuat trang HTML cho cong dong "THAY" chuoi: khoi, giao dich,
#  memo (yeu cau AI/robot), so du, va BANG CHUNG 21tr co dinh + coin dang khoa.
# =====================================================================
import os, sys, html
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bgc_engine import COIN, MAX_SUPPLY

def render(chain, out_path):
    h=chain.height(); supply=chain.audit_supply()
    bal={}
    for v,a,lk in chain.utxo.values(): bal[a]=bal.get(a,0)+v
    rows=[]
    for blk in chain.blocks:
        txr=[]
        for tx in blk.txs:
            outs="".join(f"<li>{o.value/COIN:,.0f} BGC → <code>{html.escape(o.address[:22])}…</code>"
                         f"{' 🔒khoa→khoi '+str(o.lock) if o.lock else ''}"
                         f"{' <em>“'+html.escape(o.memo)+'”</em>' if o.memo else ''}</li>" for o in tx.vout)
            kind="⛏ coinbase/genesis" if tx.coinbase else "giao dich"
            txr.append(f"<div class=tx><b>{kind}</b> <code>{tx.txid()[:16]}…</code><ul>{outs}</ul></div>")
        rows.append(f"<div class=blk><h3>Khối #{blk.index} <small><code>{blk.hash()[:16]}…</code></small></h3>{''.join(txr)}</div>")
    balrows="".join(f"<tr><td><code>{html.escape(a[:30])}…</code></td><td style='text-align:right'>{v/COIN:,.0f} BGC</td></tr>"
                    for a,v in sorted(bal.items(),key=lambda x:-x[1]))
    ok = supply==MAX_SUPPLY
    page=f"""<!doctype html><html lang=vi><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>BGC Explorer</title>
<style>
:root{{--bg:#0d1117;--card:#161b22;--line:#30363d;--tx:#8b949e;--ok:#3fb950;--accent:#58a6ff}}
@media(prefers-color-scheme:light){{:root:not([data-theme=dark]){{--bg:#f6f8fa;--card:#fff;--line:#d0d7de;--tx:#57606a;--ok:#1a7f37;--accent:#0969da}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:#c9d1d9;font:15px/1.5 system-ui,Segoe UI,Roboto,sans-serif;padding:16px}}
@media(prefers-color-scheme:light){{body{{color:#1f2328}}}}
h1{{font-size:22px;margin:0 0 4px}}.sub{{color:var(--tx);margin-bottom:16px}}
.cap{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:16px}}
.big{{font-size:30px;font-weight:700;color:var(--ok)}}
.grid{{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}}
table{{width:100%;border-collapse:collapse}}td{{padding:6px 8px;border-bottom:1px solid var(--line)}}
.blk{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 16px;margin-bottom:12px}}
.blk h3{{margin:0 0 8px;font-size:16px}}.tx{{border-top:1px dashed var(--line);padding:8px 0;color:var(--tx)}}
.tx ul{{margin:6px 0 0;padding-left:18px;color:#c9d1d9}}@media(prefers-color-scheme:light){{.tx ul{{color:#1f2328}}}}
code{{background:rgba(110,118,129,.2);padding:1px 5px;border-radius:5px;font-size:12px}}em{{color:var(--accent);font-style:normal}}
</style></head><body>
<h1>⬡ Bigcoin (BGC) Explorer</h1>
<div class=sub>Dong tien khang luong tu cho kinh te AI – robot · tong cung CO DINH, ai cung tu kiem</div>
<div class=cap>
  <div>Tong cung (tu cong tu UTXO):</div>
  <div class=big>{supply/COIN:,.0f} / 21,000,000 BGC {'✓ CO DINH' if ok else '✗ SAI!'}</div>
  <div class=sub>Chieu cao: {h} khoi · Chu ky: hash-based (khang luong tu) · Dong thuan: PoA</div>
</div>
<div class=grid>
  <div class=cap><h3>So du cac vi</h3><table>{balrows}</table></div>
  <div class=cap><h3>Cach tu kiem</h3><p class=sub>Chay node BGC cua ban → tu cong lai UTXO → phai ra dung 21,000,000. Coin founder co 🔒 (lock) hien ngay tren giao dich genesis. Khong tin — hay tu verify.</p></div>
</div>
<h2>Chuoi khoi</h2>
{''.join(rows)}
<div class=sub style=margin-top:16px>Trang nay sinh tu chuoi that; mo lai bat cu luc nao bang bgc_explorer.</div>
</body></html>"""
    open(out_path,"w",encoding="utf-8").write(page)
    return out_path
