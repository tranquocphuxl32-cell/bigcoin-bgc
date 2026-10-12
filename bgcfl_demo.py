#!/usr/bin/env python3
# =====================================================================
#  BGC-FL DEMO - FAIR LAUNCH kieu BITCOIN: khong premine, PoW ai cung dao, halving,
#  21tr ra dan, fork-choice chainwork, chu ky khang luong tu. Tu kiem chung.
# =====================================================================
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bigcoin_pq import XmssKey
import bgcfl_engine as E
from bgcfl_engine import Chain, Block, Tx, TxIn, TxOut, mine, subsidy, COIN, MAX_SUPPLY, HALVING, INITIAL, addr_of

def cb(height, miner_addr, memo="", fees=0, extra=None):
    txs=[Tx([], [TxOut(subsidy(height)+fees, miner_addr, memo)], coinbase=True)]
    if extra: txs+=extra
    return txs
def mk(chain, height, miner_addr, extra=None, fees=0):
    b=Block(height, chain.tip(), cb(height,miner_addr,f"mined by block {height}",fees,extra))
    return mine(b)

def main():
    print("="*76); print(" BGC-FL - FAIR LAUNCH kieu BITCOIN: KHONG premine, PoW, halving, khang luong tu"); print("="*76)
    print(f"\n[0] THONG SO PHAT HANH (nhu BTC, demo thu nho):")
    print(f"    subsidy ban dau = {INITIAL//COIN} BGC/khoi | halving moi {HALVING} khoi | tong toi da = {MAX_SUPPLY/COIN:,.4f} BGC")

    # cac THO DAO doc lap (ai cung tao vi + dao, khong xin phep)
    mA=XmssKey(h=8); mB=XmssKey(h=8); mC=XmssKey(h=8); bob=XmssKey(h=6)
    A,B,C,BOB = addr_of(mA.root),addr_of(mB.root),addr_of(mC.root),addr_of(bob.root)
    nm={A:"ThoA",B:"ThoB",C:"ThoC",BOB:"Bob"}
    chain=Chain()

    print(f"\n[1] KHONG PREMINE: genesis cung chi la 1 khoi DAO ra subsidy, cho nguoi dao genesis.")
    g=mk(chain,0,A); ok,m,_=chain.add_block(g)
    print(f"    genesis dao boi ThoA: {'OK' if ok else m} | ThoA nhan {chain.balance(A)/COIN} BGC (= subsidy, KHONG phai 21tr)")
    print(f"    tong cung sau genesis = {chain.audit_supply()/COIN} BGC (ra DAN, khong ai co 21tr san)")

    print(f"\n[2] PERMISSIONLESS: 3 tho thay nhau dao (ai tim nonce truoc thi duoc), khong authority:")
    import random; random.seed(1)
    miners=[(A,mA),(B,mB),(C,mC)]
    for h in range(1,12):
        who,_=random.choice(miners)            # mo phong: tho ngau nhien tim duoc khoi
        ok,m,_=chain.add_block(mk(chain,h,who))
    seq=[nm[chain.store[hh].txs[0].vout[0].address] for hh in chain.active]
    print(f"    nguoi dao moi khoi: {seq}")
    print(f"    -> nhieu tho khac nhau dao duoc; khong ai xin phep ai.")

    print(f"\n[3] HALVING: subsidy giam mot nua sau moi {HALVING} khoi:")
    for h in [0, HALVING-1, HALVING, 2*HALVING]:
        print(f"    khoi {h:>3}: subsidy = {subsidy(h)/COIN} BGC")
    print(f"    tong cung hien tai (height {chain.height()}) = {chain.audit_supply()/COIN:,.1f} BGC / toi da {MAX_SUPPLY/COIN:,.1f}")

    print(f"\n[4] CHONG LAM PHAT (21tr cung): coinbase doi NHIEU HON subsidy -> BI TU CHOI:")
    greedy=mine(Block(chain.height(), chain.tip(), [Tx([],[TxOut(subsidy(chain.height())+999*COIN, C,"tham lam")],coinbase=True)]))
    chain.add_block(greedy)
    greedy_active = greedy.hash() in chain.active
    print(f"    coinbase doi +999 BGC ngoai subsidy -> {'LOT (vao chuoi!)' if greedy_active else 'CHAN (khong vao chuoi active)'}")

    print(f"\n[5] FORK-CHOICE THEO CHAINWORK (reorg nhu BTC):")
    h0=chain.height(); tip0=chain.tip()
    fork_from=chain.active[h0-3]
    br=[]; prev=fork_from
    for i in range(h0-2, h0+2):           # dai hon chuoi hien tai -> nhieu chainwork hon
        b=mine(Block(i, prev, cb(i, C, f"fork {i}"))); br.append(b); prev=b.hash()
    for b in br: chain.add_block(b)
    reorged = chain.tip()!=tip0
    print(f"    nap nhanh doi thu dai hon -> reorg? {reorged} (height {h0} -> {chain.height()})")
    print(f"    tong cung sau reorg = {chain.audit_supply()/COIN:,.1f} BGC (<= 21tr? {chain.audit_supply()<=MAX_SUPPLY})")

    print(f"\n[6] TIEU TIEN (chu ky KHANG LUONG TU) + memo cho AI/robot (sau reorg):")
    au=[(k,v) for k,v in chain.utxo.items() if v[1]==A][0]
    tx=Tx([TxIn(au[0][0],au[0][1],mA.root.hex())],[TxOut(au[1][0], BOB, "nguoi tra AI qua BGC")])
    tx.vin[0].sig=mA.sign(tx.sighash())
    chain.add_mempool(tx)
    ok,m,_=chain.add_block(mine(Block(chain.height(), chain.tip(), cb(chain.height(), B, "ThoB dao")+[tx])))
    print(f"    ThoA -> Bob: {'OK' if ok else m} | Bob = {chain.balance(BOB)/COIN:.0f} BGC (chu ky XMSS hop le)")

    print(f"\n[7] CONG BANG (fair launch - diem mau chot phap ly):")
    bals={nm[a]:v/COIN for (v,a) in [(chain.balance(x),x) for x in (A,B,C,BOB)]}
    print(f"    so du: {bals}")
    print(f"    => KHONG ai duoc PHAT SAN 21tr; moi BGC deu DAO ra cong khai. Khong co nguoi BAN.")
    print(f"       Day la ly do BTC khong bi coi la chung khoan - BGC-FL di dung con duong do.")

    print("\n"+"="*76); print(" KET LUAN")
    print("  - KHONG PREMINE: coin ra dan qua PoW + halving (~21tr), giong het BTC.")
    print("  - PERMISSIONLESS: ai cung dao, khong authority, khong xin phep.")
    print("  - 21tr cung: coinbase > subsidy bi tu choi; fork-choice theo chainwork; reorg an toan.")
    print("  - Chu ky khang luong tu + memo AI/robot van giu.")
    print("  *** LUU Y ***")
    print("  - Demo dung target PoW co dinh (de); BTC that dieu chinh do kho moi 2016 khoi.")
    print("  - Coinbase maturity (BTC: 100 khoi moi tieu duoc) chua ap - nen them cho production.")
    print("  - Fair launch GIAM MANH rui ro chung khoan (khong nguoi ban) nhung KHONG mien tru;")
    print("    chuyen tien/AML van co the ap. Van nen hoi luat su truoc khi cham toi nguoi My.")
    print("="*76)
    checks=[chain.audit_supply()<=MAX_SUPPLY, reorged, not greedy_active, chain.balance(BOB)>0, chain.height()>=10]
    return 0 if all(checks) else 1

if __name__=="__main__": sys.exit(main())
