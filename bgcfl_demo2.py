#!/usr/bin/env python3
# =====================================================================
#  BGC-FL v2 DEMO - DIEU CHINH DO KHO (LWMA moi khoi) + COINBASE MATURITY + CHAINWORK
#  Chay tren mang REGTEST (do kho thap) de demo nhanh; luat giong het mang that.
# =====================================================================
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bigcoin_pq import XmssKey
from bgcfl_engine import Chain, Tx, TxIn, TxOut, REGTEST, MAIN, COIN, addr_of

P=REGTEST

def main():
    print("="*76); print(" BGC-FL v2 - DIEU CHINH DO KHO + COINBASE MATURITY + CHAINWORK"); print("="*76)
    print(f"\n[0] THAM SO (regtest): do kho chinh MOI KHOI theo {P.window} khoi gan nhat (LWMA) | "
          f"muc tieu {P.interval}s/khoi | maturity {P.maturity} khoi")
    print(f"    mang that: {MAIN.interval}s/khoi, LWMA {MAIN.window} khoi, maturity {MAIN.maturity}, halving {MAIN.halving:,} khoi")

    m=XmssKey(h=6); M=addr_of(m.root)

    # ---------- [1] DIEU CHINH DO KHO ----------
    print(f"\n[1] DIEU CHINH DO KHO theo thoi gian thuc (target NHO = KHO hon):")
    chain=Chain(params=P)
    t0=chain.next_target()
    for _ in range(P.window):                                   # DAO NHANH: 2s/khoi (muc tieu 10s)
        ok,msg,_=chain.add_block(chain.make_block(M, ts=chain.blocks[-1].ts+2)); assert ok, msg
    t_fast=chain.next_target()
    for _ in range(P.window):                                   # DAO CHAM: 30s/khoi
        ok,msg,_=chain.add_block(chain.make_block(M, ts=chain.blocks[-1].ts+30)); assert ok, msg
    t_slow=chain.next_target()
    print(f"    target ban dau                 = {t0:#x}")
    print(f"    target sau {P.window} khoi DAO NHANH  = {t_fast:#x}  -> {'KHO HON' if t_fast<t0 else 'de hon'} (dao nhanh -> siet)")
    print(f"    target sau {P.window} khoi DAO CHAM   = {t_slow:#x}  -> {'DE HON' if t_slow>t_fast else 'kho hon'} (dao cham -> noi)")
    retarget_ok=(t_fast<t0 and t_slow>t_fast)
    print(f"    => do kho TU DIEU CHINH dung huong: {retarget_ok}")

    # ---------- [2] COINBASE MATURITY ----------
    print(f"\n[2] COINBASE MATURITY: coin vua dao phai cho {P.maturity} khoi moi tieu duoc:")
    c2=Chain(params=P)
    ok,msg,_=c2.add_block(c2.make_block(M)); assert ok, msg
    cb=c2.blocks[-1].txs[0]; cb_h=c2.blocks[-1].index
    bob=XmssKey(h=4); BOB=addr_of(bob.root)
    def spend_tx():
        tx=Tx([TxIn(cb.txid(),0,m.root.hex())],[TxOut(cb.vout[0].value, BOB, "tra bob")])
        tx.vin[0].sig=m.sign(tx.sighash(P.magic)); return tx
    early=c2.add_mempool(spend_tx())
    print(f"    tieu coinbase ngay (sau {c2.height()-cb_h} khoi) -> {'CHAN' if not early[0] else 'LOT'}: {early[1]}")
    while c2.height()-cb_h<P.maturity:
        ok,msg,_=c2.add_block(c2.make_block(BOB)); assert ok, msg
    late=c2.add_mempool(spend_tx())
    print(f"    tieu coinbase sau {c2.height()-cb_h} khoi (>= {P.maturity}) -> {'OK' if late[0] else 'CHAN: '+late[1]}")
    maturity_ok=(not early[0]) and late[0]

    # ---------- [3] CHAINWORK ----------
    print(f"\n[3] FORK-CHOICE THEO CHAINWORK (tong do kho, khong phai so khoi):")
    print(f"    chuoi [1] chainwork hien tai = {chain.chainwork():.3e} (height {chain.height()})")
    tipA=chain.tip()
    prev=chain.blocks[-4].hash()                                # nhanh doi thu tu 3 khoi truoc dinh
    for i in range(5):                                          # dai hon -> nhieu chainwork hon
        b=chain.make_block(BOB, parent=prev, memo=f"fork {i}")
        ok,msg,_=chain.add_block(b); assert ok, msg
        prev=b.hash()
    reorged=chain.tip()!=tipA
    print(f"    nap nhanh dai hon -> reorg? {reorged} | chainwork moi = {chain.chainwork():.3e} height {chain.height()}")
    print(f"    tong cung <= 21tr? {chain.audit_supply()<=MAIN.max_supply()}")

    print("\n"+"="*76); print(" KET QUA")
    checks=[("do kho dieu chinh dung huong (nhanh->kho, cham->de)", retarget_ok),
            ("coinbase maturity chan tieu som, cho phep sau", maturity_ok),
            ("chainwork reorg + 21tr nguyen", reorged and chain.audit_supply()<=MAIN.max_supply())]
    for k,v in checks: print(f"    [{'OK' if v else 'FAIL'}] {k}")
    allok=all(v for _,v in checks)
    print("\n  - Do kho TU DIEU CHINH moi khoi (LWMA) -> khoi ra deu du hashrate len/xuong.")
    print("  - Coinbase maturity chong trom coin vua dao khi co reorg.")
    print("  - Fork-choice theo CHAINWORK (tong do kho) - dung tieu chuan BTC.")
    print("="*76)
    return 0 if allok else 1

if __name__=="__main__": sys.exit(main())
