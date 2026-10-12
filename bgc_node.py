#!/usr/bin/env python3
# =====================================================================
#  BGC NODE - gop engine + P2P + vi + dao (PoA) + BO LAP LICH DAO TU DONG (timeout).
#  1 doi tuong = 1 node BGC hoan chinh.
# =====================================================================
import os, sys, time, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bgc_engine import Chain, Block, Tx, TxOut, GEN_FOUNDER, GEN_AI, MAX_SUPPLY, COIN
from bgc_p2p import P2P
from bgc_wallet import Wallet

class Node:
    def __init__(s, name, authorities, datadir, port=0, authority_wallet=None):
        s.name=name; s.chain=Chain(authorities, datadir=datadir)
        if datadir: s.chain.load()
        s.auth=authority_wallet            # neu la node authority (duoc ky khoi)
        s.p2p=P2P(s, port=port)
    def connect(s, port): s.p2p.connect("127.0.0.1", port)
    def connect_peer(s, host, port): s.p2p.connect(host, port)
    def my_turn(s):
        return bool(s.auth) and s.chain.expected_auth(s.chain.height())==s.auth.key.root.hex()
    # --- authority dao 1 khoi KHI DEN LUOT (round-robin) tu mempool (+ tx truyen vao) ---
    def mine(s, extra_txs=None, force=False):
        assert s.auth, "chi node authority moi dao duoc"
        if not force and not s.my_turn(): return False,"chua den luot authority nay"
        txs=list(extra_txs or [])+list(s.chain.mempool.values())
        blk=Block(s.chain.height(), s.chain.tip(), txs, s.auth.key.root.hex())
        blk.sig=s.auth.sign(blk.sighash())
        ok,m,_=s.chain.add_block(blk)
        if ok: s.p2p.broadcast({"t":"block","b":blk.to_d()})
        return ok,m
    def submit_tx(s, tx):
        ok,m=s.chain.add_mempool(tx)
        if ok: s.p2p.broadcast({"t":"tx","tx":tx.to_d()})
        return ok,m

    # ---- BO LAP LICH DAO TU DONG (timeout-based liveness, kieu Clique) ----
    def _recent_signers(s):
        LIMIT=len(s.chain.auth_list)//2
        return [b.auth for b in s.chain.blocks[-LIMIT:]] if LIMIT>0 else []
    def start_mining(s, block_time=0.5):
        assert s.auth, "chi authority moi dao"
        s._mine_stop=False
        threading.Thread(target=s._mine_loop, args=(block_time,), daemon=True).start()
    def stop_mining(s): s._mine_stop=True
    def _mine_loop(s, bt):
        me=s.auth.key.root.hex(); N=len(s.chain.auth_list)
        while not getattr(s,"_mine_stop",True):
            h=s.chain.height()
            if h==0: time.sleep(bt*0.2); continue        # cho genesis (bootstrap rieng)
            if me in s._recent_signers(): time.sleep(bt*0.3); continue   # vua ky -> cho luot
            exp=s.chain.expected_auth(h)
            dist=(s.chain.auth_list.index(me)-s.chain.auth_list.index(exp))%N
            delay = 0.0 if dist==0 else bt*(1.0+0.6*dist)  # dung luot: ngay; trai luot: cho tang dan
            start=h; time.sleep(max(0.01,delay))
            if s.chain.height()!=start: continue          # da co nguoi ra khoi -> lam lai
            s.mine(force=True)                             # den luot minh (dung hoac trai luot)
            time.sleep(bt*0.3)
    def close(s):
        s._mine_stop=True; s.p2p.close()
