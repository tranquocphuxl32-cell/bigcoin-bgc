#!/usr/bin/env python3
# =====================================================================
#  BGC-FL NET - mang FAIR LAUNCH nhieu THO DAO that, P2P MA HOA, PoW tu dao, hoi tu chainwork
#  Reuse bgc_secure (ECDH+ChaCha20-Poly1305) + bgcfl_engine (PoW/retarget/maturity).
#  Chung minh: nhieu tho doc lap tu dao, gossip khoi qua kenh ma hoa, hoi tu 1 chuoi.
# =====================================================================
import os, sys, json, time, socket, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bigcoin_pq import XmssKey
from bgcfl_engine import Chain, Block, Tx, TxOut, subsidy, COIN, MAX_SUPPLY, addr_of
from bgc_secure import SecureSocket, _recvn   # kenh ma hoa da co

class Peer:
    def __init__(s,sec): s.sec=sec; s.lock=threading.Lock()
    def send(s,msg):
        try:
            with s.lock: s.sec.send(json.dumps(msg).encode())
        except Exception: pass

class Miner:
    def __init__(s, name, port=0):
        s.name=name; s.key=XmssKey(h=12); s.addr=addr_of(s.key.root)
        s.chain=Chain(); s.peers=[]; s.lock=threading.Lock(); s.stop=False; s.mine_stop=False; s.out=set()
        s.srv=socket.socket(); s.srv.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        s.srv.bind(("127.0.0.1",port)); s.port=s.srv.getsockname()[1]; s.srv.listen(8)
        threading.Thread(target=s._accept,daemon=True).start()
        threading.Thread(target=s._ticker,daemon=True).start()
    def _accept(s):
        while not s.stop:
            try: c,_=s.srv.accept()
            except OSError: break
            threading.Thread(target=s._serve,args=(c,False,None),daemon=True).start()
    def connect(s,port):
        tgt=("127.0.0.1",port)
        with s.lock:
            if tgt in s.out: return
            s.out.add(tgt)
        try:
            c=socket.create_connection(tgt,timeout=3)
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
            while not s.stop:
                s._on(p, json.loads(sec.recv()))
        except Exception: pass
        with s.lock:
            if p in s.peers: s.peers.remove(p)
            if tgt: s.out.discard(tgt)
    def _ticker(s):
        while not s.stop:
            time.sleep(0.4); s._bcast({"t":"hello","h":s.chain.height()})
    def _bcast(s,msg):
        with s.lock: ps=list(s.peers)
        for p in ps: p.send(msg)
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
    def start_mining(s): threading.Thread(target=s._mine,daemon=True).start()
    def _mine(s):
        while not s.mine_stop and not s.stop:
            h=s.chain.height(); prev=s.chain.tip(); tgt=s.chain.next_target()
            cb=Tx([],[TxOut(subsidy(h), s.addr, f"cb {s.name} h{h}")],coinbase=True)
            blk=Block(h, prev, [cb], ts=int(time.time()), target=tgt)
            found=False
            for _ in range(4000):                     # dao tung dot, bo neu co khoi moi toi
                if s.chain.tip()!=prev: break
                if blk.pow_ok(): found=True; break
                blk.nonce+=1
            if found and s.chain.tip()==prev:
                ok,_,_=s.chain.add_block(blk)
                if ok: s._bcast({"t":"block","b":blk.to_d()})
            else:
                time.sleep(0.01)
    def close(s):
        s.stop=True
        try: s.srv.close()
        except OSError: pass

def main():
    print("="*74); print(" BGC-FL NET - nhieu THO DAO that, P2P MA HOA, PoW tu dao, hoi tu chainwork"); print("="*74)
    A=Miner("ThoA"); B=Miner("ThoB"); C=Miner("ThoC")
    ms=[A,B,C]
    print(f"\n[1] 3 tho dao doc lap (vi rieng, khong xin phep). Cong: {[m.port for m in ms]}")
    for i,m in enumerate(ms):
        for o in ms[i+1:]: m.connect(o.port)      # moi cap 1 ket noi (tranh trung)
    time.sleep(0.6)
    print(f"[2] Noi luoi P2P ma hoa xong. Bat dau TU DAO (PoW)...")
    for m in ms: m.start_mining()
    # chay toi khi dat ~10 khoi hoac het 12s
    t0=time.time()
    while time.time()-t0<12 and max(m.chain.height() for m in ms)<11: time.sleep(0.3)
    for m in ms: m.mine_stop=True              # DUNG DAO nhung GIU mang + ticker de hoi tu
    time.sleep(3.0)                            # ticker dong bo not
    print(f"\n[3] KET QUA sau khi dao:")
    for m in ms:
        print(f"    {m.name}: height={m.chain.height()} chainwork={m.chain.chainwork():.3e} "
              f"supply={m.chain.audit_supply()/COIN:,.1f} tip={m.chain.tip()[:12]}..")
    tips=set(m.chain.tip() for m in ms); heights=set(m.chain.height() for m in ms)
    # phan bo coin cho tung tho (cong khai, khong ai premine)
    who={}
    for m in ms:
        for v,a,_ in m.chain.utxo.values(): who[a]=who.get(a,0)+v
        break
    print(f"\n[4] PHAN BO (fair - moi coin deu DAO ra, KHONG premine):")
    for m in ms: print(f"    {m.name} dao duoc: {m.chain.balance(m.addr)/COIN:,.1f} BGC")
    print(f"    tong cung = {A.chain.audit_supply()/COIN:,.1f} BGC (ra dan theo so khoi, <= 21tr: {A.chain.audit_supply()<=MAX_SUPPLY})")
    conv = (len(tips)==1 and len(heights)==1)
    print(f"\n[5] HOI TU: 3 tho cung 1 tip & height? {conv}")
    for m in ms: m.close()
    print("\n"+"="*74)
    print(f" KET QUA: {'TAT CA PASS - mang fair-launch nhieu tho dao CHAY THAT' if conv and A.chain.audit_supply()<=MAX_SUPPLY else 'CO LOI'}")
    print("  - Nhieu tho doc lap TU dao (PoW), gossip khoi qua kenh MA HOA, hoi tu theo chainwork.")
    print("  - KHONG premine: moi coin do dao ra; khong ai xin phep ai (permissionless).")
    print("  - Lien may that: doi 127.0.0.1 thanh IP LAN/WAN va mo cong la chay dc giua cac may.")
    print("="*74)
    return 0 if (conv and A.chain.audit_supply()<=MAX_SUPPLY) else 1

if __name__=="__main__": sys.exit(main())
