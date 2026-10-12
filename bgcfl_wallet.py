#!/usr/bin/env python3
# =====================================================================
#  BGC-FL WALLET - a POST-QUANTUM wallet for the fair-launch chain (bgcfl_engine).
#  - Signatures are HASH-BASED (XMSS) -> a quantum computer cannot forge them.
#  - XMSS is a "one-time, stateful" scheme: the leaf index 'next' MUST be persisted to
#    disk BEFORE signing, otherwise a restart could reuse a leaf and leak the key.
#    This wallet does exactly that.
#  - Fully compatible with bgcfl_engine (COIN, Tx/TxIn/TxOut, coinbase maturity).
#  Standalone: python bgcfl_wallet.py <wallet_file.json>   (create / show the address)
# =====================================================================
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bigcoin_pq import XmssKey, addr_of
from bgcfl_engine import Tx, TxIn, TxOut, COIN, MATURITY

class Wallet:
    """A durable wallet: stores the master seed + the leaf index 'next'. h=12 -> 4096 signatures/wallet."""
    def __init__(s, path, h=12):
        s.path=path
        if os.path.exists(path):
            d=json.load(open(path))
            s.key=XmssKey(master=bytes.fromhex(d["master"]), h=d["h"]); s.key.next=d["next"]
        else:
            s.key=XmssKey(h=h); s._flush()
    def _flush(s):
        tmp=s.path+".tmp"
        json.dump({"master":s.key.master.hex(),"h":s.key.h,"next":s.key.next}, open(tmp,"w"))
        os.replace(tmp, s.path)                 # atomic write (survives power loss)
    @property
    def address(s): return addr_of(s.key.root)
    def remaining(s): return (1<<s.key.h)-s.key.next   # signatures left
    def sign(s, sighash):
        s._flush_before()                       # persist 'next' before consuming the leaf
        sig=s.key.sign(sighash)                 # sign() advances next
        s._flush()                              # persist the new 'next' -> durable
        return sig
    def _flush_before(s):
        # make sure the state "about to use leaf s.key.next" is on disk before signing
        s._flush()
    def spendable(s, chain):
        """My UTXOs that are MATURE (coinbase has waited MATURITY blocks)."""
        me=s.address; h=chain.height(); outs=[]
        for (t,v),(val,owner,cbh) in chain.utxo.items():
            if owner!=me: continue
            if cbh>=0 and h-cbh<MATURITY: continue     # freshly mined coin not mature yet
            outs.append(((t,v),val))
        return outs
    def balance(s, chain):
        return sum(v for v,o,_ in chain.utxo.values() if o==s.address)/COIN
    def balance_spendable(s, chain):
        return sum(val for _,val in s.spendable(chain))/COIN
    def send(s, chain, to_addr, amount_bgc, memo=""):
        amt=int(round(amount_bgc*COIN)); me=s.address
        picks=[]; got=0
        for k,val in s.spendable(chain):
            picks.append(k); got+=val
            if got>=amt: break
        if got<amt:
            raise RuntimeError(f"not enough mature BGC (need {amount_bgc}, have {got/COIN})")
        vin=[TxIn(t,v,s.key.root.hex()) for t,v in picks]
        vout=[TxOut(amt, to_addr, memo)]
        if got-amt>0: vout.append(TxOut(got-amt, me, "change"))
        tx=Tx(vin, vout)
        sig=s.sign(tx.sighash())
        for i in tx.vin: i.sig=sig
        return tx

def main():
    path=sys.argv[1] if len(sys.argv)>1 else "my_bgc_wallet.json"
    w=Wallet(path)
    print(f"Wallet: {path}")
    print(f"Address (receive BGC): {w.address}")
    print(f"Signatures left      : {w.remaining():,} (XMSS h={w.key.h})")
    print("Give this address to others to receive BGC. KEEP the wallet file safe - losing it loses the coins.")
    return 0

if __name__=="__main__": sys.exit(main())
