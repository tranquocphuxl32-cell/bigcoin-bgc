#!/usr/bin/env python3
# =====================================================================
#  BGC-FL WALLET - a POST-QUANTUM wallet for the fair-launch chain (bgcfl_engine).
#  - Signatures are HASH-BASED (XMSS) -> a quantum computer cannot forge them.
#  - XMSS is a "one-time, stateful" scheme: a leaf must NEVER sign twice. The wallet
#    reserves the leaf (writes next+1 to disk) BEFORE signing, so a crash or restart
#    can only skip a leaf, never reuse one.
#  - NEVER restore an old copy of the wallet file and keep using it: the old 'next'
#    would reuse leaves. After restoring a backup, move the coins to a NEW wallet.
#  - Fully compatible with bgcfl_engine (COIN, Tx/TxIn/TxOut, coinbase maturity).
#  Standalone: python bgcfl_wallet.py <wallet_file.json>   (create / show the address)
# =====================================================================
import os, sys, json
from decimal import Decimal, InvalidOperation
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bigcoin_pq import XmssKey, addr_of
from bgcfl_engine import Tx, TxIn, TxOut, COIN, MAX_MONEY, MAX_MEMO_BYTES, valid_address

LOW_SIGNATURES=100      # warn the user when fewer signatures than this are left

def parse_amount(x):
    """'1.5' / 1.5 -> 150000000 base units. Exact decimal math (no float rounding)."""
    try: d=Decimal(str(x).strip())
    except InvalidOperation: raise ValueError("invalid amount")
    if not d.is_finite() or d<=0: raise ValueError("amount must be > 0")
    units=d*COIN
    if units!=units.to_integral_value(): raise ValueError("at most 8 decimal places")
    units=int(units)
    if units>MAX_MONEY: raise ValueError("amount too large")
    return units

class Wallet:
    """A durable wallet: stores the master seed + the leaf index 'next'. h=12 -> 4096 signatures/wallet."""
    def __init__(s, path, h=12):
        s.path=path
        if os.path.exists(path):
            with open(path) as f: d=json.load(f)
            s.key=XmssKey(master=bytes.fromhex(d["master"]), h=d["h"]); s.key.next=d["next"]
        else:
            s.key=XmssKey(h=h); s._flush()
    def _flush(s):
        tmp=s.path+".tmp"
        with open(tmp,"w") as f:
            json.dump({"master":s.key.master.hex(),"h":s.key.h,"next":s.key.next}, f)
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp, s.path)                 # atomic replace (survives power loss)
        try: os.chmod(s.path, 0o600)            # owner-only on Linux/macOS (no-op on Windows)
        except OSError: pass
    @property
    def address(s): return addr_of(s.key.root)
    def remaining(s): return (1<<s.key.h)-s.key.next   # signatures left
    def sign(s, sighash):
        k=s.key.next
        if k>=(1<<s.key.h):
            raise RuntimeError("wallet has no signatures left: create a new wallet and move the coins")
        s.key.next=k+1; s._flush()              # reserve the leaf on disk FIRST
        return s.key.sign_at(k, sighash)
    def spendable(s, chain):
        """My UTXOs that are mature and not already used by one of my pending transactions."""
        return chain.spendable(s.address)
    def balance(s, chain):
        return chain.balance(s.address)/COIN
    def balance_spendable(s, chain):
        return sum(val for _,val in s.spendable(chain))/COIN
    def send(s, chain, to_addr, amount_bgc, memo="", fee_bgc=0):
        if not valid_address(to_addr): raise ValueError("invalid address (expected BGCQ + 64 hex characters)")
        if len(memo.encode("utf-8"))>MAX_MEMO_BYTES: raise ValueError(f"memo longer than {MAX_MEMO_BYTES} bytes")
        amt=parse_amount(amount_bgc); fee=parse_amount(fee_bgc) if fee_bgc else 0
        me=s.address; picks=[]; got=0
        for k,val in sorted(s.spendable(chain), key=lambda kv:-kv[1]):   # largest first -> fewer inputs
            picks.append(k); got+=val
            if got>=amt+fee or len(picks)>=64: break
        if got<amt+fee:
            raise RuntimeError(f"not enough mature BGC (need {(amt+fee)/COIN:g}, have {got/COIN:g})")
        vin=[TxIn(t,v,s.key.root.hex()) for t,v in picks]
        vout=[TxOut(amt, to_addr, memo)]
        if got-amt-fee>0: vout.append(TxOut(got-amt-fee, me, "change"))
        tx=Tx(vin, vout)
        sig=s.sign(tx.sighash(chain.p.magic))  # one signature covers every input (same key, same message)
        for i in tx.vin: i.sig=sig
        return tx

def main():
    path=sys.argv[1] if len(sys.argv)>1 else "my_bgc_wallet.json"
    w=Wallet(path)
    print(f"Wallet: {path}")
    print(f"Address (receive BGC): {w.address}")
    print(f"Signatures left      : {w.remaining():,} (XMSS h={w.key.h})")
    print("Give this address to others to receive BGC. KEEP the wallet file safe - losing it loses the coins.")
    print("Never keep using an OLD copy of this file (it would reuse one-time keys).")
    return 0

if __name__=="__main__": sys.exit(main())
