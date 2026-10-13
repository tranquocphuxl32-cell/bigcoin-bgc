#!/usr/bin/env python3
# =====================================================================
#  BGC-FL DEMO - FAIR LAUNCH kieu BITCOIN: khong premine, PoW ai cung dao, halving,
#  21tr ra dan, fork-choice chainwork, chu ky khang luong tu. Tu kiem chung.
#  Chay tren mang REGTEST (halving moi 150 khoi, do kho thap) de demo nhanh.
# =====================================================================
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bigcoin_pq import XmssKey
from bgcfl_engine import Chain, Block, Tx, TxIn, TxOut, mine, REGTEST, MAIN, COIN, INITIAL, addr_of

P=REGTEST

def main():
    print("="*76); print(" BGC-FL - FAIR LAUNCH kieu BITCOIN: KHONG premine, PoW, halving, khang luong tu"); print("="*76)
    print(f"\n[0] THONG SO PHAT HANH (mang that):")
    print(f"    subsidy ban dau = {INITIAL//COIN} BGC/khoi | halving moi {MAIN.halving:,} khoi | tong toi da = {MAIN.max_supply()/COIN:,.4f} BGC")

    # cac THO DAO doc lap (ai cung tao vi + dao, khong xin phep)
    mA=XmssKey(h=6); mB=XmssKey(h=6); mC=XmssKey(h=6); bob=XmssKey(h=4)
    A,B,C,BOB = addr_of(mA.root),addr_of(mB.root),addr_of(mC.root),addr_of(bob.root)
    nm={A:"ThoA",B:"ThoB",C:"ThoC",BOB:"Bob"}
    chain=Chain(params=P)

    print(f"\n[1] KHONG PREMINE: genesis (co dinh trong code) tra 0 BGC cho dia chi khong ai tieu duoc.")
    print(f"    tong cung sau genesis = {chain.audit_supply()/COIN} BGC (ra DAN, khong ai co 21tr san)")

    print(f"\n[2] PERMISSIONLESS: 3 tho thay nhau dao (ai tim nonce truoc thi duoc), khong authority:")
    random.seed(1)
    for _ in range(12):
        who=random.choice([A,B,C])                  # mo phong: tho ngau nhien tim duoc khoi
        ok,m,_=chain.add_block(chain.make_block(who)); assert ok, m
    seq=[nm[b.txs[0].vout[0].address] for b in chain.blocks[1:]]
    print(f"    nguoi dao moi khoi: {seq}")
    print(f"    -> nhieu tho khac nhau dao duoc; khong ai xin phep ai.")

    print(f"\n[3] HALVING: subsidy giam mot nua sau moi {MAIN.halving:,} khoi (mang that):")
    for h in [0, MAIN.halving-1, MAIN.halving, 2*MAIN.halving]:
        print(f"    khoi {h:>7,}: subsidy = {MAIN.subsidy(h)/COIN} BGC")
    print(f"    tong cung hien tai (height {chain.height()}) = {chain.audit_supply()/COIN:,.1f} BGC")

    print(f"\n[4] CHONG LAM PHAT (21tr cung): coinbase doi NHIEU HON subsidy -> BI TU CHOI:")
    greedy=chain.make_block(C, extra_reward=999*COIN, memo="tham lam")
    ok,why,_=chain.add_block(greedy)
    greedy_active=chain.tip()==greedy.hash()
    print(f"    coinbase doi +999 BGC ngoai subsidy -> {'LOT (vao chuoi!)' if greedy_active else 'CHAN: '+why}")

    print(f"\n[5] FORK-CHOICE THEO CHAINWORK (reorg nhu BTC):")
    h0=chain.height(); tip0=chain.tip()
    prev=chain.blocks[-3].hash()
    for i in range(4):                              # dai hon chuoi hien tai -> nhieu chainwork hon
        b=chain.make_block(C, parent=prev, memo=f"fork {i}")
        ok,m,_=chain.add_block(b); assert ok, m
        prev=b.hash()
    reorged=chain.tip()!=tip0
    print(f"    nap nhanh doi thu dai hon -> reorg? {reorged} (height {h0} -> {chain.height()})")
    print(f"    tong cung sau reorg = {chain.audit_supply()/COIN:,.1f} BGC (<= 21tr? {chain.audit_supply()<=MAIN.max_supply()})")

    print(f"\n[6] TIEU TIEN (chu ky KHANG LUONG TU) + memo cho AI/robot (sau reorg):")
    for _ in range(P.maturity):                     # cho coin cua ThoA truong thanh
        chain.add_block(chain.make_block(B))
    (t,v),val=next(iter(chain.spendable(A)))
    tx=Tx([TxIn(t,v,mA.root.hex())],[TxOut(val, BOB, "nguoi tra AI qua BGC")])
    tx.vin[0].sig=mA.sign(tx.sighash(P.magic))
    ok,m=chain.add_mempool(tx)
    if ok: ok,m,_=chain.add_block(chain.make_block(B, txs=[tx], memo="ThoB dao"))
    print(f"    ThoA -> Bob: {'OK' if ok else m} | Bob = {chain.balance(BOB)/COIN:.0f} BGC (chu ky XMSS hop le)")

    print(f"\n[7] CONG BANG (fair launch - diem mau chot phap ly):")
    bals={nm[a]:chain.balance(a)/COIN for a in (A,B,C,BOB)}
    print(f"    so du: {bals}")
    print(f"    => KHONG ai duoc PHAT SAN 21tr; moi BGC deu DAO ra cong khai. Khong co nguoi BAN.")

    print("\n"+"="*76); print(" KET LUAN")
    print("  - KHONG PREMINE: coin ra dan qua PoW + halving (~21tr), giong het BTC.")
    print("  - PERMISSIONLESS: ai cung dao, khong authority, khong xin phep.")
    print("  - 21tr cung: coinbase > subsidy bi tu choi; fork-choice theo chainwork; reorg an toan.")
    print("  - Do kho chinh moi khoi (LWMA); coinbase maturity; chu ky khang luong tu + memo AI/robot.")
    print("  *** LUU Y ***")
    print("  - Fair launch GIAM MANH rui ro chung khoan (khong nguoi ban) nhung KHONG mien tru;")
    print("    chuyen tien/AML van co the ap. Van nen hoi luat su truoc khi phat hanh.")
    print("="*76)
    checks=[chain.audit_supply()<=MAIN.max_supply(), reorged, not greedy_active, chain.balance(BOB)>0, chain.height()>=10]
    return 0 if all(checks) else 1

if __name__=="__main__": sys.exit(main())
