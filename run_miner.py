#!/usr/bin/env python3
# =====================================================================
#  RUN_MINER - mine BGC easily, Bitcoin-style (anyone can mine).
#
#  Like Bitcoin:
#    - Fair launch, NO premine: every coin is mined (PoW).
#    - Permissionless: no approval needed, just plug in a machine and mine.
#    - Halving + difficulty retarget + coinbase maturity + fork-choice by chainwork.
#  Unlike Bitcoin (stronger):
#    - HASH-BASED signatures (XMSS) -> QUANTUM-RESISTANT.
#    - P2P MA HOA dau-cuoi (ECDH + ChaCha20-Poly1305).
#
#  Dung (de nhat):
#    python run_miner.py                         # tao vi, dao solo, cong 9333
#    python run_miner.py --peers IP:9333         # tham gia mang qua 1 seed
#    python run_miner.py --name An --port 9333 --peers a.b.c.d:9333,e.f.g.h:9333
#
#  Khi chay: tu nap genesis chuan, noi seed, TU DAO vao vi cua ban, in trang thai.
#  Lenh go vao: bal | addr | send <dia_chi> <so_BGC> [memo] | peers | stop | quit
# =====================================================================
import os, sys, json, time, socket, threading, argparse, functools
print=functools.partial(print, flush=True)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bigcoin_pq import H
from bgcfl_engine import Chain, Block, Tx, TxOut, subsidy, COIN, MAX_SUPPLY, MATURITY
from bgcfl_wallet import Wallet
from bgc_secure import SecureSocket

HERE=os.path.dirname(os.path.abspath(__file__))
MSG="BGC: dong tien hau luong tu, sinh ra cho ky nguyen AI va robot."

# ---------- nap / tao genesis chuan (chung moi may) ----------
def load_genesis(chain, gpath):
    if not os.path.exists(gpath):
        import bgcfl_genesis
        json.dump(bgcfl_genesis.build().to_d(), open(gpath,"w"))
        print(f"[genesis] chua co -> tu tao {os.path.basename(gpath)}")
    gb=Block.from_d(json.load(open(gpath)))
    if chain.height()==0:
        ok,m,_=chain.add_block(gb)
        print(f"[genesis] nap khoi 0: {'OK' if ok else 'LOI '+m} hash={gb.hash()[:16]}..")

# ---------- mang P2P ma hoa ----------
class Peer:
    def __init__(s,sec): s.sec=sec; s.lock=threading.Lock()
    def send(s,msg):
        try:
            with s.lock: s.sec.send(json.dumps(msg).encode())
        except Exception: pass

class MinerNode:
    def __init__(s, name, wallet, datadir, port):
        s.name=name; s.w=wallet; s.addr=wallet.address
        s.chain=Chain(datadir=datadir); s.chain.load()
        s.peers=[]; s.out=set(); s.lock=threading.Lock()
        s.stop=False; s.mining=False
        s.events=[]                          # nhat ky su kien (cho giao dien app doc)
        s.srv=socket.socket(); s.srv.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        s.srv.bind(("0.0.0.0",port)); s.port=s.srv.getsockname()[1]; s.srv.listen(16)
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
            if tgt in s.out: return
            s.out.add(tgt)
        try:
            c=socket.create_connection(tgt,timeout=4)
            threading.Thread(target=s._serve,args=(c,True,tgt),daemon=True).start()
        except OSError:
            with s.lock: s.out.discard(tgt)
    def _serve(s,sock,initiator,tgt):
        try: sec=SecureSocket(sock,initiator=initiator)
        except Exception:
            if tgt:
                with s.lock: s.out.discard(tgt)
            return
        p=Peer(sec)
        with s.lock: s.peers.append(p)
        p.send({"t":"hello","h":s.chain.height()})
        try:
            while not s.stop: s._on(p, json.loads(sec.recv()))
        except Exception: pass
        with s.lock:
            if p in s.peers: s.peers.remove(p)
            if tgt: s.out.discard(tgt)
    def _ticker(s):
        while not s.stop:
            time.sleep(0.5); s._bcast({"t":"hello","h":s.chain.height()})
    def _bcast(s,msg):
        with s.lock: ps=list(s.peers)
        for p in ps: p.send(msg)
    def _log(s, kind, **kw):                 # su kien co cau truc (app tu dich ngon ngu)
        ev={"t":time.time(),"kind":kind}; ev.update(kw)
        s.events.append(ev); s.events=s.events[-200:]
    def _on(s,p,msg):
        t=msg.get("t")
        if t=="hello":
            if msg["h"]>s.chain.height(): p.send({"t":"getblocks"})
            elif msg["h"]<s.chain.height(): p.send({"t":"blocks","b":[b.to_d() for b in s.chain.blocks]})
        elif t=="getblocks": p.send({"t":"blocks","b":[b.to_d() for b in s.chain.blocks]})
        elif t=="blocks":
            for bd in msg["b"]: s.chain.add_block(Block.from_d(bd))
        elif t=="block":
            before=s.chain.height(); s.chain.add_block(Block.from_d(msg["b"]))
            if s.chain.height()>before: s._bcast(msg)
            if s.chain.height()<msg["b"]["i"]+1: p.send({"t":"getblocks"})
        elif t=="tx":
            try: s.chain.add_mempool(Tx.from_d(msg["x"]))
            except Exception: pass
    def submit_tx(s, tx):
        ok,m=s.chain.add_mempool(tx)
        if ok: s._bcast({"t":"tx","x":tx.to_d()})
        return ok,m
    # --- dao (PoW) ---
    def start_mining(s):
        s.mining=True; threading.Thread(target=s._mine,daemon=True).start()
    def _mine(s):
        while s.mining and not s.stop:
            h=s.chain.height(); prev=s.chain.tip(); tgt=s.chain.next_target()
            # lay giao dich tu mempool (don gian: tat ca hop le)
            extra=list(s.chain.mempool.values())[:50]
            fees=0
            for tx in extra:
                insum=sum(s.chain.utxo.get((i.txid,i.vout),(0,"",-1))[0] for i in tx.vin)
                fees+=insum-sum(o.value for o in tx.vout)
            fees=max(0,fees)
            cb=Tx([],[TxOut(subsidy(h)+fees, s.addr, f"BGC {s.name} h{h}")],coinbase=True)
            blk=Block(h, prev, [cb]+extra, ts=int(time.time()), target=tgt)
            found=False
            for _ in range(6000):                 # dao tung dot; bo neu co khoi moi toi
                if s.chain.tip()!=prev or s.stop or not s.mining: break
                if blk.pow_ok(): found=True; break
                blk.nonce+=1
            if found and s.chain.tip()==prev:
                ok,_,_=s.chain.add_block(blk)
                if ok:
                    s._bcast({"t":"block","b":blk.to_d()})
                    s._log("mined", h=h, reward=subsidy(h)/COIN, tip=blk.hash()[:12])
                    print(f"  ⛏  DAO DUOC khoi #{h}  (+{subsidy(h)/COIN:g} BGC)  tip={blk.hash()[:12]}..")
            else:
                time.sleep(0.01)
    def close(s):
        s.stop=True; s.mining=False
        try: s.srv.close()
        except OSError: pass

def banner(name, port, addr):
    print("="*72)
    print(f" ⬡  {MSG}")
    print("="*72)
    print(" DAO BGC - fair-launch, khang luong tu, P2P ma hoa (giong BTC, manh hon)")
    print(f"   tho dao : {name}   |   cong : {port}")
    print(f"   vi cua ban (nhan BGC): {addr}")
    print("="*72)

def main():
    ap=argparse.ArgumentParser(description="Dao BGC de dang, giong Bitcoin.")
    ap.add_argument("--name", default=socket.gethostname()[:12] or "tho")
    ap.add_argument("--port", type=int, default=9333)
    ap.add_argument("--peers", default="", help="danh sach seed: ip:cong,ip:cong")
    ap.add_argument("--datadir", default=os.path.join(HERE,"bgcfl_data"))
    ap.add_argument("--wallet", default=os.path.join(HERE,"my_bgc_wallet.json"))
    ap.add_argument("--genesis", default=os.path.join(HERE,"bgcfl_genesis.json"))
    ap.add_argument("--no-mine", action="store_true", help="chi dong bo, khong dao (node quan sat)")
    a=ap.parse_args()

    os.makedirs(a.datadir, exist_ok=True)
    w=Wallet(a.wallet)
    node=MinerNode(a.name, w, a.datadir, a.port)
    load_genesis(node.chain, a.genesis)
    banner(a.name, node.port, node.addr)

    peers=[p.strip() for p in a.peers.split(",") if p.strip() and "<" not in p]
    def reconnector():
        while not node.stop:
            for p in peers:
                try: host,port=p.rsplit(":",1); node.connect(host,int(port))
                except Exception: pass
            time.sleep(5)
    if peers:
        print(f"[mang] seed: {peers} (tu noi lai moi 5s)")
        threading.Thread(target=reconnector,daemon=True).start()
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
            print(f"[trang thai] cao={h} peer={len(node.peers)} thuong={subsidy(h)/COIN:g} "
                  f"tong={sup/COIN:,.0f}/{MAX_SUPPLY/COIN:,.0f} BGC | vi ban={w.balance(node.chain):,.4f} "
                  f"(tieu duoc {w.balance_spendable(node.chain):,.4f})")
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
                      f"coinbase can {MATURITY} khoi moi truong thanh)")
            elif c=="addr":
                print(f"  dia chi nhan BGC: {node.addr}  | chu ky con: {w.remaining():,}")
            elif c=="peers":
                print(f"  {len(node.peers)} peer | cao {node.chain.height()} | chainwork {node.chain.chainwork():.3e}")
            elif c=="stop": node.mining=False; print("  da dung dao (van dong bo).")
            elif c=="mine":
                if not node.mining: node.start_mining(); print("  tiep tuc dao.")
            elif c=="send" and len(parts)>=3:
                to=parts[1]; amt=float(parts[2]); memo=" ".join(parts[3:]) or "send"
                try:
                    tx=w.send(node.chain, to, amt, memo=memo); ok,m=node.submit_tx(tx)
                    print(f"  gui {amt} BGC -> {to[:20]}.. : {'da phat len mang' if ok else 'LOI: '+m}")
                except Exception as e: print("  loi gui:",e)
            else:
                print("  lenh: bal | addr | send <dia_chi> <so_BGC> [memo] | peers | stop | mine | quit")
    except KeyboardInterrupt: pass
    node.close(); print(f"[{a.name}] da dung.")
    return 0

if __name__=="__main__": sys.exit(main())
