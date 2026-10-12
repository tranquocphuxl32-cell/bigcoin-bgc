#!/usr/bin/env python3
# =====================================================================
#  BGC-FL v2 DEMO - DIEU CHINH DO KHO (retarget) + COINBASE MATURITY + CHAINWORK
# =====================================================================
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bigcoin_pq import XmssKey
from bgcfl_engine import (Chain, Block, Tx, TxIn, TxOut, mine, subsidy, COIN, MAX_SUPPLY,
                          HALVING, RETARGET, BLOCK_INTERVAL, MATURITY, GENESIS_TARGET, addr_of, work_of)

def mineblk(chain, miner_addr, ts, extra=None, fees=0):
    h=chain.height(); tgt=chain.next_target()
    txs=[Tx([],[TxOut(subsidy(h)+fees, miner_addr, f"cb{h}")],coinbase=True)]+(extra or [])
    return mine(Block(h, chain.tip(), txs, ts=ts, target=tgt))

def main():
    print("="*76); print(" BGC-FL v2 - RETARGET (dieu chinh do kho) + COINBASE MATURITY + CHAINWORK"); print("="*76)
    print(f"\n[0] THAM SO: retarget moi {RETARGET} khoi | muc tieu {BLOCK_INTERVAL}s/khoi | maturity {MATURITY} khoi")

    m=XmssKey(h=10); M=addr_of(m.root)

    # ---------- [1] RETARGET ----------
    print(f"\n[1] DIEU CHINH DO KHO theo thoi gian thuc (target NHO = KHO hon):")
    chain=Chain(); clock=1000
    # lich thoi gian: 0..7 DAO NHANH (5s), 8..15 DAO CHAM (20s), 16.. binh thuong (10s)
    def interval(h): return 5 if h<RETARGET else (20 if h<2*RETARGET else 10)
    for h in range(2*RETARGET+1):
        ok,msg,_=chain.add_block(mineblk(chain, M, clock))
        assert ok, msg
        clock+=interval(h+1)
    t0=chain.blocks[0].target; t8=chain.blocks[RETARGET].target; t16=chain.blocks[2*RETARGET].target
    print(f"    target khoi 0  (genesis)        = {t0:#x}")
    print(f"    target khoi {RETARGET} (sau cua so DAO NHANH) = {t8:#x}  -> {'KHO HON' if t8<t0 else 'de hon'} (dao nhanh -> siet)")
    print(f"    target khoi {2*RETARGET} (sau cua so DAO CHAM) = {t16:#x}  -> {'DE HON' if t16>t8 else 'kho hon'} (dao cham -> noi)")
    retarget_ok = (t8<t0 and t16>t8)
    print(f"    => do kho TU DIEU CHINH dung huong: {retarget_ok}")

    # ---------- [2] COINBASE MATURITY ----------
    print(f"\n[2] COINBASE MATURITY: coin vua dao phai cho {MATURITY} khoi moi tieu duoc:")
    c2=Chain(); clk=1000
    c2.add_block(mineblk(c2, M, clk)); clk+=10          # khoi 0: M dao duoc subsidy
    cb_h=0
    # thu tieu coinbase khoi 0 ngay o khoi 1
    au=[(k,v) for k,v in c2.utxo.items() if v[1]==M][0]
    bob=XmssKey(h=6); BOB=addr_of(bob.root)
    def spend_tx():
        tx=Tx([TxIn(au[0][0],au[0][1],m.root.hex())],[TxOut(au[1][0], BOB, "tra bob")]); tx.vin[0].sig=m.sign(tx.sighash()); return tx
    early=c2._check_tx(spend_tx(), c2.utxo, c2.height())
    print(f"    tieu coinbase ngay (sau {c2.height()-cb_h} khoi) -> {'CHAN' if not early[0] else 'LOT'}: {early[1]}")
    # dao them cho du MATURITY khoi roi tieu
    while c2.height()-cb_h<MATURITY: c2.add_block(mineblk(c2, M, clk)); clk+=10
    late=c2._check_tx(spend_tx(), c2.utxo, c2.height())
    print(f"    tieu coinbase sau {c2.height()-cb_h} khoi (>= {MATURITY}) -> {'OK' if late[0] else 'CHAN: '+late[1]}")
    maturity_ok = (not early[0]) and late[0]

    # ---------- [3] CHAINWORK ----------
    print(f"\n[3] FORK-CHOICE THEO CHAINWORK (tong do kho, khong phai so khoi):")
    print(f"    chuoi [1] chainwork hien tai = {chain.chainwork():.3e} (height {chain.height()})")
    tipA=chain.tip()
    # nhanh doi thu dai hon tu height-3 -> nhieu chainwork hon -> thang
    forkbase=chain.active[chain.height()-4]; prev=forkbase; clk=9000
    br=[]
    # tai dung do kho cua tung height tren nhanh moi (phai dung luat retarget)
    tmp=Chain()
    for hh in chain.active[:chain.height()-3]: tmp.store[hh]=chain.store[hh]
    tmp.active=chain.active[:chain.height()-3]
    for i in range(chain.height()-3, chain.height()+2):
        b=mineblk_on(tmp, M, clk); br.append(b)
        tmp.add_block(b); clk+=10
    for b in br: chain.add_block(b)
    reorged=chain.tip()!=tipA
    print(f"    nap nhanh dai hon -> reorg? {reorged} | chainwork moi = {chain.chainwork():.3e} height {chain.height()}")
    print(f"    tong cung <= 21tr? {chain.audit_supply()<=MAX_SUPPLY}")

    print("\n"+"="*76); print(" KET QUA")
    checks=[("retarget dung huong (nhanh->kho, cham->de)", retarget_ok),
            ("coinbase maturity chan tieu som, cho phep sau", maturity_ok),
            ("chainwork reorg + 21tr nguyen", reorged and chain.audit_supply()<=MAX_SUPPLY)]
    for k,v in checks: print(f"    [{'OK' if v else 'FAIL'}] {k}")
    allok=all(v for _,v in checks)
    print("\n  - Do kho TU DIEU CHINH (nhu BTC/2016 khoi) -> khoi ra deu du hashrate len/xuong.")
    print("  - Coinbase maturity chong trom coin vua dao khi co reorg.")
    print("  - Fork-choice theo CHAINWORK (tong do kho) - dung tieu chuan BTC.")
    print("="*76)
    return 0 if allok else 1

# helper dao tren 1 chain tam (cho nhanh doi thu)
def mineblk_on(chain, miner_addr, ts):
    h=chain.height(); tgt=chain.next_target()
    txs=[Tx([],[TxOut(subsidy(h), miner_addr, f"fork-cb{h}")],coinbase=True)]
    return mine(Block(h, chain.tip(), txs, ts=ts, target=tgt))

if __name__=="__main__": sys.exit(main())
