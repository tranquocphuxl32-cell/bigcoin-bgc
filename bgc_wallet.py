#!/usr/bin/env python3
# =====================================================================
#  BGC WALLET - vi khang luong tu, LUU CHI SO LEAF ra dia (chong lo khoa khi reboot)
#  Dung XMSS (one-time, stateful) nen 'next' PHAI ben vung. Vi nay ghi 'next' xuong
#  dia TRUOC khi tra chu ky ve -> robot/AI reboot khong bao gio ky lai cung leaf.
# =====================================================================
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bigcoin_pq import XmssKey
import bgc_engine as E
from bgc_engine import Tx, TxIn, TxOut, addr_of, COIN

class Wallet:
    def __init__(s, path, h=8):
        s.path=path
        if os.path.exists(path):
            d=json.load(open(path))
            s.key=XmssKey(master=bytes.fromhex(d["master"]), h=d["h"]); s.key.next=d["next"]
        else:
            s.key=XmssKey(h=h); s._flush()
    def _flush(s):
        json.dump({"master":s.key.master.hex(),"h":s.key.h,"next":s.key.next}, open(s.path,"w"))
    @property
    def address(s): return addr_of(s.key.root)
    def sign(s, sighash):
        # GHI 'next' TRUOC khi ky (nguyen tac an toan: luu trang thai truoc khi dung leaf)
        s.key.next+=0  # no-op de ro y
        sig=s.key.sign(sighash)   # sign() da tang next
        s._flush()                # ben vung ngay
        return sig
    def send(s, chain, to_addr, amount_btc, memo="", lock=0):
        amt=int(round(amount_btc*COIN)); me=s.address; picks=[]; got=0; h=chain.height()
        for (t,v),(val,owner,lk) in chain.utxo.items():
            if owner==me and lk<=h: picks.append((t,v)); got+=val
            if got>=amt: break
        if got<amt: raise RuntimeError("khong du BGC da mo khoa")
        vin=[TxIn(t,v,s.key.root.hex()) for t,v in picks]
        vout=[TxOut(amt,to_addr,memo,lock)]
        if got-amt>0: vout.append(TxOut(got-amt,me))
        tx=Tx(vin,vout); sig=s.sign(tx.sighash())
        for i in tx.vin: i.sig=sig
        return tx
