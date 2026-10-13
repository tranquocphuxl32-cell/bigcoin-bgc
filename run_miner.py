#!/usr/bin/env python3
# =====================================================================
#  RUN_MINER - mine BGC easily, Bitcoin-style (anyone can mine).
#
#  Like Bitcoin:
#    - Fair launch, NO premine: every coin is mined (PoW).
#    - Permissionless: no approval needed, just plug in a machine and mine.
#    - Halving + per-block difficulty adjustment + coinbase maturity + fork-choice by chainwork.
#  Unlike Bitcoin (stronger):
#    - HASH-BASED signatures (XMSS) -> QUANTUM-RESISTANT.
#    - P2P MA HOA dau-cuoi (ECDH + ChaCha20-Poly1305).
#
#  Dung (de nhat):
#    python run_miner.py                         # tao vi, dao solo, cong 9333
#    python run_miner.py --peers IP:9333         # tham gia mang qua 1 seed
#    python run_miner.py --name An --port 9333 --peers a.b.c.d:9333,e.f.g.h:9333
#    python run_miner.py --regtest               # mang THU NGHIEM rieng (do kho rat thap)
#
#  Khi chay: genesis co san trong code, noi seed, TU DAO vao vi cua ban, in trang thai.
#  Lenh go vao: bal | addr | send <dia_chi> <so_BGC> [memo] | peers | stop | mine | quit
# =====================================================================
import os, sys, json, time, socket, threading, argparse, functools
print=functools.partial(print, flush=True)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bgcfl_engine import Chain, Block, Tx, MAIN, REGTEST, COIN, MATURITY, mine
from bgcfl_wallet import Wallet, LOW_SIGNATURES
from bgc_secure import SecureSocket

HERE=os.path.dirname(os.path.abspath(__file__))
MSG="BGC: dong tien hau luong tu, sinh ra cho ky nguyen AI va robot."
PROTO=2               # phien ban giao thuc P2P
MAX_PEERS=32          # so ket noi toi da
TIP_EVERY=15          # giay giua 2 lan bao dinh chuoi
MINE_BATCH=20_000     # so nonce moi dot (roi kiem tra khoi moi)
TEMPLATE_AGE=30       # giay: lam moi khoi mau (giao dich moi + timestamp)

def load_genesis(chain, gpath=None):
    """Genesis nay nam san trong code (giong nhau tren moi may) - chi in ra de kiem tra."""
    print(f"[genesis] khoi 0 ({chain.p.name}): hash={chain.genesis_hash[:16]}..")

# ---------- mang P2P ma hoa ----------
class Peer:
    def __init__(s,sec,addr): s.sec=sec; s.addr=addr; s.lock=threading.Lock(); s.ready=False; s.work=0; s.asked=0.0
    def send(s,msg):
        try:
            data=json.dumps(msg,separators=(",",":")).encode()
            with s.lock: s.sec.send(data)
            return True
        except Exception:
            s.sec.close(); return False

class MinerNode:
    def __init__(s, name, wallet, datadir, port, params=MAIN, bind="0.0.0.0"):
        s.name=name; s.w=wallet; s.addr=wallet.address
        s.chain=Chain(datadir=datadir, params=params); s.chain.load()
        s.peers=[]; s.out=set(); s.lock=threading.Lock()
        s.stop=False; s.mining=False; s._miner=None; s.hashrate=0.0
        s.events=[]                          # nhat ky su kien (cho giao dien app doc)
        s.srv=socket.socket(); s.srv.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        s.srv.bind((bind,port)); s.port=s.srv.getsockname()[1]; s.srv.listen(16)
        threading.Thread(target=s._accept,daemon=True).start()
        threading.Thread(target=s._ticker,daemon=True).start()
    # --- ket noi ---
    def _accept(s):
        while not s.stop:
            try: c,_=s.srv.accept()
            except OSError: break
            threading.Thread(target=s._serve,args=(c,False,None),daemon=True).start()
    def connect(s,host,port):
        tgt=(host,int(port))
        with s.lock:
            if tgt in s.out or len(s.peers)>=MAX_PEERS: return
            s.out.add(tgt)
        try:
            c=socket.create_connection(tgt,timeout=4)
            threading.Thread(target=s._serve,args=(c,True,tgt),daemon=True).start()
        except OSError:
            with s.lock: s.out.discard(tgt)
    def _serve(s,sock,initiator,tgt):
        p=None
        try:
            sec=SecureSocket(sock,initiator=initiator)
            p=Peer(sec, tgt)
            with s.lock:
                if len(s.peers)>=MAX_PEERS: return
                s.peers.append(p)
            h,work,tip=s.chain.tip_info()
            p.send({"t":"version","v":PROTO,"net":s.chain.p.magic,"g":s.chain.genesis_hash,"h":h,"w":hex(work),"tip":tip})
            while not s.stop:
                msg=json.loads(sec.recv())
                if type(msg) is not dict or not s._on(p,msg): break   # du lieu xau -> ngat ket noi
        except Exception: pass
        finally:
            try: sock.close()
            except OSError: pass
            with s.lock:
                if p in s.peers: s.peers.remove(p)
                if tgt: s.out.discard(tgt)
    def _ticker(s):
        while not s.stop:
            time.sleep(TIP_EVERY); s._bcast(s._tip_msg())
    def _tip_msg(s):
        h,work,tip=s.chain.tip_info(); return {"t":"tip","h":h,"w":hex(work),"tip":tip}
    def _bcast(s,msg,skip=None):
        with s.lock: ps=[p for p in s.peers if p.ready and p is not skip]
        for p in ps: p.send(msg)
    def _log(s, kind, **kw):                 # su kien co cau truc (app tu dich ngon ngu)
        ev={"t":time.time(),"kind":kind}; ev.update(kw)
        with s.lock: s.events=(s.events+[ev])[-200:]
    # --- dong bo ---
    def _ask(s,p,soon=False):
        """Xin khoi tiep theo bang 'locator' (danh sach hash cua minh), co gioi han tan suat."""
        if time.time()-p.asked<(2 if soon else 10): return
        p.asked=time.time(); p.send({"t":"getblocks","loc":s.chain.locator()})
    def _note_tip(s,p,msg):
        try: p.work=int(msg.get("w"),16)
        except (TypeError,ValueError): return False
        if p.work>s.chain.chainwork(): s._ask(p)
        return True
    def _add(s,bd,p):
        """True: khoi moi duoc nhan | False: vo hai (trung/mo coi/tuong lai) | None: khoi SAI luat."""
        try: blk=Block.from_d(bd)
        except Exception: return None
        ok,m,_=s.chain.add_block(blk)
        if ok: return True
        if m.startswith("orphan"): s._ask(p,soon=True); return False
        if m=="already have it" or "future" in m: return False
        return None
    def _on(s,p,msg):
        t=msg.get("t")
        if t=="version":
            if msg.get("net")!=s.chain.p.magic or msg.get("g")!=s.chain.genesis_hash: return False  # mang khac
            p.ready=True
            with s.chain.lock: txs=[tx.to_d() for tx in list(s.chain.mempool.values())[:500]]
            if txs: p.send({"t":"txs","x":txs})
            return s._note_tip(p,msg)
        if not p.ready: return False
        if t=="tip": return s._note_tip(p,msg)
        if t=="getblocks":
            loc=msg.get("loc")
            if type(loc) is not list: return False
            p.send({"t":"blocks","b":s.chain.blocks_after(loc[:64])})
        elif t=="blocks":
            bl=msg.get("b")
            if type(bl) is not list: return False
            p.asked=0.0; progressed=False
            for bd in bl:
                r=s._add(bd,p)
                if r is None: return False
                progressed|=r
            if progressed:
                s._bcast(s._tip_msg(),skip=p)
                if p.work>s.chain.chainwork(): s._ask(p,soon=True)
        elif t=="block":
            r=s._add(msg.get("b"),p)
            if r is None: return False
            if r: s._bcast(msg,skip=p)
        elif t in ("tx","txs"):
            items=[msg.get("x")] if t=="tx" else msg.get("x")
            if type(items) is not list: return False
            for x in items[:500]:
                try: tx=Tx.from_d(x)
                except Exception: return False
                ok,_=s.chain.add_mempool(tx)
                if ok: s._bcast({"t":"tx","x":x},skip=p)
        return True
    def submit_tx(s, tx):
        ok,m=s.chain.add_mempool(tx)
        if ok: s._bcast({"t":"tx","x":tx.to_d()})
        return ok,m
    # --- dao (PoW) ---
    def start_mining(s):
        s.mining=True
        if s._miner is None or not s._miner.is_alive():
            s._miner=threading.Thread(target=s._mine,daemon=True); s._miner.start()
    def stop_mining(s, wait=False):
        """Dung dao. wait=True: cho luong dao ket thuc han (khoi vua tim duoc van duoc phat)."""
        s.mining=False
        if wait and s._miner is not None: s._miner.join(10)
    def _mine(s):
        memo=f"BGC {s.name}"[:64]
        while s.mining and not s.stop:
            blk=s.chain.block_template(s.addr, memo); t0=time.time(); tries=0; found=None
            while s.mining and not s.stop and s.chain.tip()==blk.prev and time.time()-t0<TEMPLATE_AGE:
                found=mine(blk, MINE_BATCH); tries+=MINE_BATCH
                if found: break
            dt=time.time()-t0
            if dt>0.5: s.hashrate=tries/dt
            if not found: continue
            ok,_,_=s.chain.add_block(found)
            if ok and s.chain.tip()==found.hash():
                s._bcast({"t":"block","b":found.to_d()})
                reward=found.txs[0].vout[0].value/COIN
                s._log("mined", h=found.index, reward=reward, tip=found.hash()[:12])
                print(f"  ⛏  DAO DUOC khoi #{found.index}  (+{reward:g} BGC)  tip={found.hash()[:12]}..")
    def close(s):
        s.stop=True; s.mining=False
        try: s.srv.close()
        except OSError: pass
        with s.lock: ps=list(s.peers)
        for p in ps: p.sec.close()

def banner(name, port, addr, net):
    print("="*72)
    print(f" ⬡  {MSG}")
    print("="*72)
    print(" DAO BGC - fair-launch, khang luong tu, P2P ma hoa (giong BTC, manh hon)")
    print(f"   mang    : {net}")
    print(f"   tho dao : {name}   |   cong : {port}")
    print(f"   vi cua ban (nhan BGC): {addr}")
    print("="*72)

def parse_peers(text):
    return [p.strip() for p in text.split(",") if p.strip() and "<" not in p]

def start_reconnector(node, peers, every=10):
    def loop():
        while not node.stop:
            for p in peers:
                try: host,port=p.rsplit(":",1); node.connect(host,int(port))
                except Exception: pass
            time.sleep(every)
    threading.Thread(target=loop,daemon=True).start()

def main():
    ap=argparse.ArgumentParser(description="Dao BGC de dang, giong Bitcoin.")
    ap.add_argument("--name", default=socket.gethostname()[:12] or "tho")
    ap.add_argument("--port", type=int, default=9333)
    ap.add_argument("--peers", default="", help="danh sach seed: ip:cong,ip:cong")
    ap.add_argument("--datadir", default=os.path.join(HERE,"bgcfl_data"))
    ap.add_argument("--wallet", default=os.path.join(HERE,"my_bgc_wallet.json"))
    ap.add_argument("--regtest", action="store_true", help="mang thu nghiem rieng (do kho thap, coin KHONG co gia tri)")
    ap.add_argument("--no-mine", action="store_true", help="chi dong bo, khong dao (node quan sat)")
    a=ap.parse_args()

    params=REGTEST if a.regtest else MAIN
    os.makedirs(a.datadir, exist_ok=True)
    print("[khoi dong] dang nap vi va kiem tra lai chuoi da luu...")
    w=Wallet(a.wallet)
    node=MinerNode(a.name, w, a.datadir, a.port, params=params)
    load_genesis(node.chain)
    banner(a.name, node.port, node.addr, params.name)

    peers=parse_peers(a.peers)
    if peers:
        print(f"[mang] seed: {peers} (tu noi lai moi 10s)")
        start_reconnector(node, peers)
        time.sleep(1.2)
    else:
        print("[mang] khong co seed -> dao SOLO. Them --peers IP:9333 de tham gia mang.")

    if not a.no_mine:
        node.start_mining(); print("[dao] bat dau TU DAO (PoW) vao vi cua ban...")
    else:
        print("[dao] che do quan sat (khong dao).")

    def monitor():
        last=-1
        while not node.stop:
            time.sleep(6)
            h=node.chain.height()
            if h==last: continue
            last=h
            sup=node.chain.audit_supply()
            print(f"[trang thai] cao={h} peer={len(node.peers)} thuong={params.subsidy(h)/COIN:g} "
                  f"tong={sup/COIN:,.0f}/{params.max_supply()/COIN:,.0f} BGC | vi ban={w.balance(node.chain):,.4f} "
                  f"(tieu duoc {w.balance_spendable(node.chain):,.4f}) | {node.hashrate:,.0f} H/s")
    threading.Thread(target=monitor,daemon=True).start()

    print("\nLenh: bal | addr | send <dia_chi> <so_BGC> [memo] | peers | stop | mine | quit\n")
    try:
        for line in sys.stdin:
            parts=line.strip().split()
            if not parts: continue
            c=parts[0].lower()
            if c=="quit": break
            elif c=="bal":
                print(f"  so du: {w.balance(node.chain):,.4f} BGC  (tieu duoc: {w.balance_spendable(node.chain):,.4f}; "
                      f"coinbase can {params.maturity} khoi moi truong thanh)")
            elif c=="addr":
                print(f"  dia chi nhan BGC: {node.addr}  | chu ky con: {w.remaining():,}")
                if w.remaining()<LOW_SIGNATURES: print("  CANH BAO: vi sap het chu ky - tao vi moi va chuyen coin sang.")
            elif c=="peers":
                print(f"  {len(node.peers)} peer | cao {node.chain.height()} | chainwork {node.chain.chainwork():.3e} | {node.hashrate:,.0f} H/s")
            elif c=="stop": node.mining=False; print("  da dung dao (van dong bo).")
            elif c=="mine":
                if not node.mining: node.start_mining(); print("  tiep tuc dao.")
            elif c=="send" and len(parts)>=3:
                to=parts[1]; memo=" ".join(parts[3:]) or "send"
                try:
                    tx=w.send(node.chain, to, parts[2], memo=memo); ok,m=node.submit_tx(tx)
                    print(f"  gui {parts[2]} BGC -> {to[:20]}.. : {'da phat len mang' if ok else 'LOI: '+m}")
                except Exception as e: print("  loi gui:",e)
            else:
                print("  lenh: bal | addr | send <dia_chi> <so_BGC> [memo] | peers | stop | mine | quit")
    except KeyboardInterrupt: pass
    node.close(); print(f"[{a.name}] da dung.")
    return 0

if __name__=="__main__": sys.exit(main())
