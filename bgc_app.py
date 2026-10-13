#!/usr/bin/env python3
# =====================================================================
#  BGC-APP - a "one-click" GUI to mine BGC (runs in the browser).
#  - Runs a MinerNode in the background and opens a control page in the browser.
#  - DEFAULT LANGUAGE GERMAN; with a language picker (Deutsch / English / Tieng Viet).
#  - Shows: status, balance, address, start/stop mining, send BGC, add seed, event log, history.
#  Usage: python bgc_app.py                          (opens http://localhost:7000)
#         python bgc_app.py --peers IP:9333          (join a network)
#         python bgc_app.py --web-port 7000 --port 9333 --name An
# =====================================================================
import os, sys, json, time, threading, argparse, webbrowser, functools, secrets, hmac
print=functools.partial(print, flush=True)
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_miner as R
from bgcfl_engine import COIN, MAIN, REGTEST
from bgcfl_wallet import Wallet
try:
    import qrcode, qrcode.image.svg               # tao ma QR cho dia chi (tuy chon)
    HAS_QR=True
except Exception:
    HAS_QR=False

# Khi dong goi thanh .exe (PyInstaller one-file): dat vi/du lieu/genesis CANH BEN
# file .exe (de nguoi dung tim/sao luu vi), khong phai trong thu muc giai nen tam.
if getattr(sys, "frozen", False):
    HERE=os.path.dirname(sys.executable)
else:
    HERE=os.path.dirname(os.path.abspath(__file__))
NODE=None; PEERS_CFG=[]
# Secret for this run: only the page we serve knows it, so other websites open in the same
# browser cannot call /api/send (CSRF). The Host check below blocks DNS-rebinding.
TOKEN=secrets.token_urlsafe(32); WEB_PORT=7000

# ---------------------------------------------------------------- trang HTML
PAGE=r"""<!doctype html><html lang="de" data-theme="dark"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Cpolygon points='32,3 57,17.5 57,46.5 32,61 7,46.5 7,17.5' fill='%235aa0ff'/%3E%3Cpolygon points='32,12 49,22 49,42 32,52 15,42 15,22' fill='%23141a24'/%3E%3Ctext x='32' y='43' font-family='Arial,sans-serif' font-weight='bold' font-size='30' fill='%235aa0ff' text-anchor='middle'%3EB%3C/text%3E%3Ccircle cx='49' cy='18' r='5' fill='%2349d17a'/%3E%3C/svg%3E">
<title>BGC Miner</title><style>
:root{--bg:#0b0e14;--card:#141a24;--line:#263040;--mut:#8aa0b4;--ok:#49d17a;--ac:#5aa0ff;--txt:#dfe8f0;--warn:#ffb454}
@media(prefers-color-scheme:light){:root:not([data-theme=dark]){--bg:#f3f6fa;--card:#fff;--line:#d7dee8;--mut:#5a6b7b;--ok:#128a43;--ac:#1763d6;--txt:#1b2430}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:15px/1.55 system-ui,Segoe UI,Roboto,sans-serif;padding:16px;max-width:860px;margin:0 auto}
.top{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
.msg{font-size:17px;font-weight:600;color:var(--ac);margin:4px 0}
select,input,button{font:inherit;color:var(--txt);background:var(--card);border:1px solid var(--line);border-radius:9px;padding:8px 10px}
button{cursor:pointer;background:var(--ac);color:#fff;border:0;font-weight:600}
button.sec{background:var(--card);color:var(--txt);border:1px solid var(--line)}
button:disabled{opacity:.5;cursor:default}
.sub{color:var(--mut);font-size:13px;margin:2px 0 14px}
.k{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}
.cell{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;min-width:135px;flex:1}
.cell .n{font-size:21px;font-weight:700} .cell .l{color:var(--mut);font-size:12px}
.bar{height:7px;background:var(--line);border-radius:6px;overflow:hidden;margin-top:6px}.bar>i{display:block;height:100%;background:var(--ok);width:0}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin:12px 0}
.card h3{margin:0 0 10px;font-size:14px}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.row input{flex:1;min-width:120px}
code{background:rgba(120,140,170,.18);padding:2px 6px;border-radius:5px;font-size:12px;word-break:break-all}
.addr{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:var(--mut);margin-right:6px}
.dot.on{background:var(--ok)} .pill{font-size:12px;color:var(--mut)}
#log{max-height:200px;overflow:auto;font-size:13px}
#log div{padding:3px 0;border-bottom:1px solid var(--line)}
#hist{max-height:260px;overflow:auto;font-size:13px}
#hist .it{display:flex;justify-content:space-between;gap:10px;padding:7px 0;border-bottom:1px solid var(--line)}
#hist .l2{color:var(--mut);font-size:12px}
#hist .amt{font-weight:700;white-space:nowrap}
#hist .pos{color:var(--ok)} #hist .neg{color:var(--warn)}
.note{color:var(--warn);font-size:12px;margin-top:8px}
.toast{position:fixed;bottom:16px;left:50%;transform:translateX(-50%);background:var(--card);border:1px solid var(--line);padding:10px 16px;border-radius:10px;opacity:0;transition:.3s;pointer-events:none}
.toast.show{opacity:1}
</style></head><body>
<div class="top">
  <div><p class="msg" id="tagline">⬡</p><p class="sub" id="subtitle"></p></div>
  <div><label class="pill" id="lang_l"></label>
    <select id="lang"><option value="de">Deutsch</option><option value="en">English</option><option value="vi">Tiếng Việt</option></select>
  </div>
</div>

<div class="k">
  <div class="cell"><div class="n" id="s_h">0</div><div class="l" id="l_h"></div></div>
  <div class="cell"><div class="n" id="s_peers">0</div><div class="l" id="l_peers"></div></div>
  <div class="cell"><div class="n" id="s_bal">0</div><div class="l" id="l_bal"></div></div>
  <div class="cell"><div class="n" id="s_reward">0</div><div class="l" id="l_reward"></div></div>
  <div class="cell"><div class="n" id="s_supply">0</div><div class="l" id="l_supply"></div><div class="bar"><i id="s_bar"></i></div></div>
</div>

<div class="card">
  <h3 id="h_mine"></h3>
  <div class="row">
    <span><span class="dot" id="mdot"></span><span class="pill" id="mstat"></span></span>
    <button id="btn_mine"></button>
  </div>
  <div class="note" id="mnote"></div>
</div>

<div class="card">
  <h3 id="h_wallet"></h3>
  <div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap">
    <div style="background:#fff;padding:8px;border-radius:10px;line-height:0" id="qrbox">
      <img id="qr" width="132" height="132" alt="QR">
    </div>
    <div style="flex:1;min-width:200px">
      <p class="sub" id="recv_l" style="margin:0 0 6px"></p>
      <div class="addr"><code id="addr"></code><button class="sec" id="btn_copy"></button></div>
      <p class="sub" id="wallet_hint"></p>
    </div>
  </div>
</div>

<div class="card">
  <h3 id="h_send"></h3>
  <div class="row">
    <input id="to" placeholder="BGCQ...">
    <input id="amt" type="number" step="0.0001" style="max-width:130px" placeholder="0.00">
    <input id="memo" placeholder="" style="max-width:150px">
    <button id="btn_send"></button>
  </div>
  <p class="sub" id="send_hint"></p>
</div>

<div class="card">
  <h3 id="h_net"></h3>
  <div class="row">
    <input id="peer" placeholder="IP:9333">
    <button class="sec" id="btn_connect"></button>
  </div>
  <p class="sub" id="net_hint"></p>
</div>

<div class="card"><h3 id="h_hist"></h3><div id="hist"></div></div>
<div class="card"><h3 id="h_log"></h3><div id="log"></div></div>
<p class="sub" id="footer"></p>
<div class="toast" id="toast"></div>

<script>
const T={
 de:{tag:"BGC: Die post-quanten Währung, geboren für das Zeitalter von KI und Robotern.",
  subtitle:"Fair-Launch · quantensichere Signaturen (XMSS) · verschlüsseltes P2P · wie Bitcoin, nur stärker",
  lang:"Sprache", l_h:"Höhe (Blöcke)", l_peers:"Verbundene Knoten", l_bal:"Dein Guthaben (BGC)",
  l_reward:"Aktuelle Belohnung", l_supply:"Ausgegeben / Max",
  h_mine:"Schürfen (Mining)", mine_on:"Mining läuft", mine_off:"Mining gestoppt",
  btn_start:"Mining starten", btn_stop:"Mining stoppen",
  mnote:"Frisch geschürfte Coins brauchen einige Blöcke bis sie ausgegeben werden können (Coinbase-Reife).",
  h_wallet:"Deine Brieftasche", recv_l:"Diese Adresse scannen, um dir BGC zu senden:", copy:"Adresse kopieren", copied:"Adresse kopiert",
  wallet_hint:"Gib diese Adresse weiter, um BGC zu empfangen. Bewahre die Wallet-Datei sicher auf — Verlust = Coins verloren.",
  h_send:"BGC senden", btn_send:"Senden", memo:"Notiz",
  send_hint:"Signiert quantensicher (XMSS) und über das Netz verbreitet. Nur ausgereifte Coins sind verfügbar.",
  spendable:"verfügbar", remaining:"Signaturen übrig",
  h_net:"Dem Netzwerk beitreten", btn_connect:"Verbinden",
  net_hint:"Gib die Adresse eines Seed-Knotens ein (IP:Port), um dem Netzwerk beizutreten. Alle Knoten müssen dieselbe genesis-Datei verwenden.",
  h_log:"Ereignisse", h_hist:"Verlauf (Transaktionen)", hist_mined:"Geschürft", hist_sent:"Gesendet an", hist_received:"Erhalten von", hist_empty:"Noch keine Transaktionen", footer:"Prototyp zum Lernen/Demo — vor echtem Einsatz Parameter anpassen und Sicherheitsaudit durchführen.",
  ev_mined:"Block #{h} geschürft (+{r} BGC)", ev_start:"Mining gestartet", ev_stop:"Mining gestoppt",
  ev_send:"{a} BGC gesendet an {to}…", ev_recv:"Guthaben aktualisiert", err:"Fehler"},
 en:{tag:"BGC: The post-quantum currency, born for the age of AI and robots.",
  subtitle:"Fair launch · quantum-safe signatures (XMSS) · encrypted P2P · like Bitcoin, but stronger",
  lang:"Language", l_h:"Height (blocks)", l_peers:"Connected peers", l_bal:"Your balance (BGC)",
  l_reward:"Current reward", l_supply:"Issued / Max",
  h_mine:"Mining", mine_on:"Mining running", mine_off:"Mining stopped",
  btn_start:"Start mining", btn_stop:"Stop mining",
  mnote:"Freshly mined coins need a few blocks before they can be spent (coinbase maturity).",
  h_wallet:"Your wallet", recv_l:"Scan this address to send yourself BGC:", copy:"Copy address", copied:"Address copied",
  wallet_hint:"Share this address to receive BGC. Keep the wallet file safe — losing it means losing your coins.",
  h_send:"Send BGC", btn_send:"Send", memo:"Memo",
  send_hint:"Signed quantum-safe (XMSS) and broadcast to the network. Only matured coins are spendable.",
  spendable:"spendable", remaining:"signatures left",
  h_net:"Join the network", btn_connect:"Connect",
  net_hint:"Enter a seed node address (IP:port) to join the network. All nodes must use the same genesis file.",
  h_log:"Events", h_hist:"History (transactions)", hist_mined:"Mined", hist_sent:"Sent to", hist_received:"Received from", hist_empty:"No transactions yet", footer:"Learning/demo prototype — tune parameters and get a security audit before real use.",
  ev_mined:"Mined block #{h} (+{r} BGC)", ev_start:"Mining started", ev_stop:"Mining stopped",
  ev_send:"Sent {a} BGC to {to}…", ev_recv:"Balance updated", err:"Error"},
 vi:{tag:"BGC: đồng tiền hậu lượng tử, sinh ra cho kỷ nguyên AI và robot.",
  subtitle:"Fair-launch · chữ ký kháng lượng tử (XMSS) · P2P mã hóa · giống Bitcoin, mạnh hơn",
  lang:"Ngôn ngữ", l_h:"Chiều cao (số khối)", l_peers:"Số máy kết nối", l_bal:"Số dư của bạn (BGC)",
  l_reward:"Phần thưởng hiện tại", l_supply:"Đã phát hành / Tối đa",
  h_mine:"Đào (Mining)", mine_on:"Đang đào", mine_off:"Đã dừng đào",
  btn_start:"Bắt đầu đào", btn_stop:"Dừng đào",
  mnote:"Coin vừa đào cần chờ vài khối mới tiêu được (coinbase maturity).",
  h_wallet:"Ví của bạn", recv_l:"Quét địa chỉ này để gửi BGC cho bạn:", copy:"Chép địa chỉ", copied:"Đã chép địa chỉ",
  wallet_hint:"Đưa địa chỉ này để nhận BGC. Giữ kỹ file ví — mất là mất coin.",
  h_send:"Gửi BGC", btn_send:"Gửi", memo:"Ghi chú",
  send_hint:"Ký kháng lượng tử (XMSS) rồi phát lên mạng. Chỉ coin đã trưởng thành mới tiêu được.",
  spendable:"tiêu được", remaining:"chữ ký còn lại",
  h_net:"Tham gia mạng", btn_connect:"Kết nối",
  net_hint:"Nhập địa chỉ seed node (IP:cổng) để tham gia mạng. Mọi máy phải dùng cùng file genesis.",
  h_log:"Nhật ký", h_hist:"Lịch sử giao dịch", hist_mined:"Đào được", hist_sent:"Đã gửi tới", hist_received:"Đã nhận từ", hist_empty:"Chưa có giao dịch", footer:"Bản nguyên mẫu học/demo — chỉnh tham số và kiểm toán an ninh trước khi dùng thật.",
  ev_mined:"Đào được khối #{h} (+{r} BGC)", ev_start:"Bắt đầu đào", ev_stop:"Dừng đào",
  ev_send:"Đã gửi {a} BGC tới {to}…", ev_recv:"Cập nhật số dư", err:"Lỗi"}
};
let L="de", ST={};
function fmt(s,o){return s.replace(/\{(\w+)\}/g,(_,k)=>o[k]!=null?o[k]:"")}
function tr(){const t=T[L];
 document.documentElement.lang=L;
 document.getElementById("tagline").textContent="⬡ "+t.tag;
 document.getElementById("subtitle").textContent=t.subtitle;
 document.getElementById("lang_l").textContent=t.lang+": ";
 for(const[id,k] of [["l_h","l_h"],["l_peers","l_peers"],["l_bal","l_bal"],["l_reward","l_reward"],["l_supply","l_supply"],
   ["h_mine","h_mine"],["h_wallet","h_wallet"],["h_send","h_send"],["h_net","h_net"],["h_log","h_log"],
   ["mnote","mnote"],["wallet_hint","wallet_hint"],["send_hint","send_hint"],["net_hint","net_hint"],["footer","footer"],
   ["btn_copy","copy"],["recv_l","recv_l"],["h_hist","h_hist"]]) document.getElementById(id).textContent=t[k];
 document.getElementById("memo").placeholder=t.memo;
 document.getElementById("btn_send").textContent=t.btn_send;
 document.getElementById("btn_connect").textContent=t.btn_connect;
 render();
}
function toast(m){const e=document.getElementById("toast");e.textContent=m;e.classList.add("show");setTimeout(()=>e.classList.remove("show"),1600)}
function evtext(e){const t=T[L];
 if(e.kind==="mined")return fmt(t.ev_mined,{h:e.h,r:e.reward});
 if(e.kind==="start")return t.ev_start; if(e.kind==="stop")return t.ev_stop;
 if(e.kind==="send")return fmt(t.ev_send,{a:e.amount,to:(e.to||"").slice(0,14)});
 return e.kind;}
function render(){const t=T[L],d=ST;if(!d.address)return;
 document.getElementById("s_h").textContent=d.height;
 document.getElementById("s_peers").textContent=d.peers;
 document.getElementById("s_bal").textContent=(+d.balance).toLocaleString(undefined,{maximumFractionDigits:4});
 document.getElementById("s_reward").textContent=(+d.reward);
 document.getElementById("s_supply").textContent=Math.round(d.supply).toLocaleString()+" / "+Math.round(d.maxsupply).toLocaleString();
 document.getElementById("s_bar").style.width=(100*d.supply/d.maxsupply)+"%";
 document.getElementById("addr").textContent=d.address;
 document.getElementById("mdot").className="dot"+(d.mining?" on":"");
 document.getElementById("mstat").textContent=(d.mining?t.mine_on:t.mine_off)+" · "+(+d.spendable).toLocaleString(undefined,{maximumFractionDigits:4})+" "+t.spendable+" · "+d.remaining+" "+t.remaining;
 const b=document.getElementById("btn_mine");b.textContent=d.mining?t.btn_stop:t.btn_start;b.dataset.on=d.mining?"1":"0";
 const log=document.getElementById("log");log.innerHTML="";
 (d.events||[]).slice().reverse().forEach(e=>{const row=document.createElement("div");
   const ts=new Date(e.t*1000).toLocaleTimeString();row.textContent=ts+"  "+evtext(e);log.appendChild(row)});
}
function el(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e}
function renderHist(items){const t=T[L],box=document.getElementById("hist");box.textContent="";
 if(!items||!items.length){box.appendChild(el("div","l2",t.hist_empty));return}
 items.forEach(it=>{const row=el("div","it");
   let label,sign,cls;
   if(it.kind==="mined"){label=t.hist_mined;sign="+";cls="pos"}
   else if(it.kind==="received"){label=t.hist_received+" "+String(it.party||"").slice(0,16)+"…";sign="+";cls="pos"}
   else{label=t.hist_sent+" "+String(it.party||"").slice(0,16)+"…";sign="−";cls="neg"}
   const memo=it.memo?(" · "+it.memo):"";
   const left=el("div");left.appendChild(el("div",null,label));left.appendChild(el("div","l2","#"+it.h+memo));
   row.appendChild(left);
   row.appendChild(el("div","amt "+cls,sign+(+it.amount).toLocaleString(undefined,{maximumFractionDigits:4})+" BGC"));
   box.appendChild(row)});
}
const TOKEN="__BGC_TOKEN__";
const H={"X-BGC-Token":TOKEN};
async function pollHist(){try{const r=await fetch("/api/history",{headers:H});renderHist(await r.json())}catch(e){}}
async function poll(){try{const r=await fetch("/api/status",{headers:H});ST=await r.json();render()}catch(e){}}
async function post(u,b){const r=await fetch(u,{method:"POST",headers:Object.assign({"Content-Type":"application/json"},H),body:JSON.stringify(b||{})});return r.json()}
document.getElementById("lang").onchange=e=>{L=e.target.value;localStorage&&localStorage.setItem("bgc_lang",L);tr()};
document.getElementById("btn_mine").onclick=async e=>{const on=e.target.dataset.on==="1";await post("/api/mine",{on:!on});poll()};
document.getElementById("btn_copy").onclick=()=>{navigator.clipboard&&navigator.clipboard.writeText(ST.address);toast(T[L].copied)};
document.getElementById("btn_send").onclick=async()=>{const to=document.getElementById("to").value.trim(),amt=document.getElementById("amt").value,memo=document.getElementById("memo").value;
 if(!to||!amt)return;const r=await post("/api/send",{to,amount:amt,memo});toast(r.ok?T[L].btn_send+" ✓":(T[L].err+": "+r.msg));if(r.ok){document.getElementById("to").value="";document.getElementById("amt").value=""}poll()};
document.getElementById("btn_connect").onclick=async()=>{const p=document.getElementById("peer").value.trim();if(!p)return;await post("/api/connect",{peer:p});try{localStorage&&localStorage.setItem("bgc_peer",p)}catch(e){}toast("OK");poll()};
try{const s=localStorage&&localStorage.getItem("bgc_lang");if(s){L=s;document.getElementById("lang").value=s}}catch(e){}
try{const p=localStorage&&localStorage.getItem("bgc_peer");if(p)document.getElementById("peer").value=p}catch(e){}
// QR dia chi: hien neu server co; an ca o neu khong co (204/loi)
const _qr=document.getElementById("qr");
_qr.onerror=()=>{document.getElementById("qrbox").style.display="none"};
_qr.src="/api/qr?k="+encodeURIComponent(TOKEN)+"&"+Date.now();
tr();poll();pollHist();setInterval(poll,2000);setInterval(pollHist,5000);
</script></body></html>"""

# ---------------------------------------------------------------- API
def status():
    n=NODE; ch=n.chain; w=n.w; h=ch.height(); p=ch.p
    return {"height":h,"peers":len(n.peers),"supply":ch.audit_supply()/COIN,"maxsupply":p.max_supply()/COIN,
            "reward":p.subsidy(h)/COIN,"balance":w.balance(ch),"spendable":w.balance_spendable(ch),
            "address":n.addr,"remaining":w.remaining(),"mining":n.mining,"chainwork":str(ch.chainwork()),
            "name":n.name,"port":n.port,"maturity":p.maturity,"net":p.name,"hashrate":round(n.hashrate),
            "events":n.events[-60:]}

_HIST={"tip":None,"items":[]}
def history(limit=30):
    """Lich su giao dich cua vi (cache theo dinh chuoi, chi quet lai khi co khoi moi)."""
    tip=NODE.chain.tip()
    if _HIST["tip"]!=tip:
        _HIST["items"]=_scan_history(limit); _HIST["tip"]=tip
    return _HIST["items"]

def _scan_history(limit):
    """Lich su giao dich cua vi: da dao / da nhan / da gui (quet toan chuoi)."""
    ch=NODE.chain; me=NODE.addr
    outmap={}                                   # (txid,vout) -> (value,addr)
    for blk in ch.blocks:
        for tx in blk.txs:
            tid=tx.txid()
            for vo,o in enumerate(tx.vout): outmap[(tid,vo)]=(o.value,o.address)
    items=[]
    for blk in ch.blocks:
        for tx in blk.txs:
            out_me=sum(o.value for o in tx.vout if o.address==me)
            memo=next((o.memo for o in tx.vout if o.memo), "")
            if tx.coinbase:
                if out_me>0:
                    items.append({"kind":"mined","amount":out_me/COIN,"h":blk.index,"memo":""})
                continue
            in_me=sum(outmap.get((i.txid,i.vout),(0,""))[0] for i in tx.vin if outmap.get((i.txid,i.vout),(0,""))[1]==me)
            if in_me>0:                          # minh la NGUOI GUI
                to=next((o.address for o in tx.vout if o.address!=me), me)
                sent=sum(o.value for o in tx.vout if o.address!=me)
                items.append({"kind":"sent","amount":sent/COIN,"party":to,"h":blk.index,"memo":memo})
            elif out_me>0:                       # minh la NGUOI NHAN
                frm=outmap.get((tx.vin[0].txid,tx.vin[0].vout),(0,"?"))[1]
                items.append({"kind":"received","amount":out_me/COIN,"party":frm,"h":blk.index,"memo":memo})
    return items[-limit:][::-1]                  # moi nhat len dau

class Handler(BaseHTTPRequestHandler):
    def _send(s, code, body, ctype="application/json"):
        b=body if isinstance(body,bytes) else body.encode()
        s.send_response(code); s.send_header("Content-Type",ctype+"; charset=utf-8")
        s.send_header("Content-Length",str(len(b)))
        s.send_header("Cache-Control","no-store"); s.send_header("X-Frame-Options","DENY")
        s.send_header("Referrer-Policy","no-referrer")
        s.end_headers(); s.wfile.write(b)
    def _read_body(s):
        """Read the whole request body first: replying while it is unread makes Windows reset the connection."""
        try: n=int(s.headers.get("Content-Length",0))
        except ValueError: n=-1
        if not 0<=n<=65536: s.close_connection=True; return None
        return s.rfile.read(n)
    def _json(s):
        d=json.loads(s._body or b"{}")
        if type(d) is not dict: raise ValueError("bad request")
        return d
    def _host_ok(s):
        """Only answer requests addressed to this machine (blocks DNS-rebinding attacks)."""
        return s.headers.get("Host","") in {f"localhost:{WEB_PORT}", f"127.0.0.1:{WEB_PORT}", f"[::1]:{WEB_PORT}"}
    def _auth_ok(s):
        k=s.headers.get("X-BGC-Token","")
        if not k and "?" in s.path:
            from urllib.parse import parse_qs
            k=(parse_qs(s.path.split("?",1)[1]).get("k") or [""])[0]
        return hmac.compare_digest(k.encode(), TOKEN.encode())
    def do_GET(s):
        if not s._host_ok(): s._send(403,"{}"); return
        if s.path=="/" or s.path.startswith("/index"):
            s._send(200,PAGE.replace("__BGC_TOKEN__",TOKEN),"text/html"); return
        if not s.path.startswith("/api/"): s._send(404,"{}"); return
        if not s._auth_ok(): s._send(403,"{}"); return
        if s.path.startswith("/api/status"): s._send(200,json.dumps(status()))
        elif s.path.startswith("/api/history"): s._send(200,json.dumps(history()))
        elif s.path.startswith("/api/qr"):
            if not HAS_QR: s.send_response(204); s.end_headers(); return
            import io
            q=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
            q.add_data(NODE.addr); q.make(fit=True)
            buf=io.BytesIO(); q.make_image(image_factory=qrcode.image.svg.SvgPathImage).save(buf)
            s._send(200, buf.getvalue(), "image/svg+xml")
        else: s._send(404,"{}")
    def do_POST(s):
        s._body=s._read_body()
        if s._body is None: s._send(413,"{}"); return
        if not s._host_ok() or not s._auth_ok(): s._send(403,"{}"); return
        if not s.headers.get("Content-Type","").startswith("application/json"): s._send(415,"{}"); return
        try:
            if s.path=="/api/mine":
                on=s._json().get("on",True)
                if on and not NODE.mining: NODE.start_mining(); NODE._log("start")
                elif not on and NODE.mining: NODE.mining=False; NODE._log("stop")
                s._send(200,json.dumps({"ok":True}))
            elif s.path=="/api/send":
                d=s._json(); to=str(d.get("to","")).strip(); amount=str(d.get("amount","")).strip()
                tx=NODE.w.send(NODE.chain,to,amount,memo=str(d.get("memo","") or "send"))
                ok,m=NODE.submit_tx(tx)
                if ok: NODE._log("send",amount=amount,to=to)
                s._send(200,json.dumps({"ok":ok,"msg":m}))
            elif s.path=="/api/connect":
                d=s._json(); host,port=d["peer"].rsplit(":",1); NODE.connect(host,int(port))
                s._send(200,json.dumps({"ok":True}))
            else: s._send(404,"{}")
        except Exception as e:
            s._send(200,json.dumps({"ok":False,"msg":str(e)}))
    def log_message(s,*a): pass

def main():
    global NODE, PEERS_CFG, WEB_PORT
    ap=argparse.ArgumentParser(description="BGC Miner App (giao dien trinh duyet).")
    ap.add_argument("--web-port", type=int, default=7000)
    ap.add_argument("--port", type=int, default=9333)
    ap.add_argument("--name", default=(os.environ.get("COMPUTERNAME") or "tho")[:12])
    ap.add_argument("--peers", default="")
    ap.add_argument("--datadir", default=os.path.join(HERE,"bgcfl_data"))
    ap.add_argument("--wallet", default=os.path.join(HERE,"my_bgc_wallet.json"))
    ap.add_argument("--regtest", action="store_true", help="mang thu nghiem rieng (do kho thap, coin KHONG co gia tri)")
    ap.add_argument("--no-open", action="store_true")
    a=ap.parse_args()

    os.makedirs(a.datadir, exist_ok=True)
    print("[khoi dong] dang nap vi va kiem tra lai chuoi da luu...")
    w=Wallet(a.wallet)
    NODE=R.MinerNode(a.name, w, a.datadir, a.port, params=REGTEST if a.regtest else MAIN)
    R.load_genesis(NODE.chain)
    PEERS_CFG=R.parse_peers(a.peers)
    if PEERS_CFG: R.start_reconnector(NODE, PEERS_CFG)

    WEB_PORT=a.web_port
    srv=ThreadingHTTPServer(("127.0.0.1",a.web_port),Handler)
    url=f"http://localhost:{a.web_port}"
    print("="*68); print(" BGC Miner App dang chay.  Mo trinh duyet:", url); print("="*68)
    print(f"   mang: {NODE.chain.p.name} | vi: {NODE.addr}")
    print(f"   cong P2P: {NODE.port} | seed: {PEERS_CFG or '(dao solo)'}")
    if not a.no_open:
        try: threading.Timer(1.0, lambda: webbrowser.open(url)).start()
        except Exception: pass
    try: srv.serve_forever()
    except KeyboardInterrupt: pass
    NODE.close(); srv.shutdown()
    return 0

if __name__=="__main__": sys.exit(main())
