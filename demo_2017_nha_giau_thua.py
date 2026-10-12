#!/usr/bin/env python3
# =====================================================================
#  DEMO: "CUOC CHIEN 2017" thu nho — PHE NHA GIAU (nhieu tien + nhieu hashrate,
#  doi luat tu in them tien) VAN THUA mang NGUOI DUNG chay node.
#
#  Y tuong: node nguoi dung chi chap nhan khoi THEO LUAT (coinbase <= phan thuong).
#  Phe giau dao NHANH HON (nhieu khoi hon = nhieu "hashrate"/chainwork hon) nhung
#  moi khoi tu thuong qua muc (lam phat). Node nguoi dung VUT BO -> phe giau tu
#  tach thanh chuoi rieng, khong ai theo. Tien nhieu + suc dao nhieu KHONG mua
#  duoc quyen doi luat.
#  Chay:  python demo_2017_nha_giau_thua.py
# =====================================================================
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bgcfl_engine import Chain, Block, Tx, TxOut, mine, subsidy, COIN, MAX_SUPPLY, addr_of
from bigcoin_pq import XmssKey

LINE="="*74

def make_block(prev_chain_blocks, prev_hash, height, miner_addr, reward, target):
    cb = Tx([], [TxOut(reward, miner_addr, f"cb h{height}")], coinbase=True)
    blk = Block(height, prev_hash, [cb], ts=1000+height, target=target)
    return mine(blk)   # giai PoW

def main():
    print(LINE); print(" DEMO 2017: PHE NHA GIAU (nhieu tien + hashrate, doi luat) VAN THUA NGUOI DUNG"); print(LINE)

    nguoi_dung = XmssKey(h=6); phe_giau = XmssKey(h=6)
    ND = addr_of(nguoi_dung.root); PG = addr_of(phe_giau.root)

    # ---- Chuoi THEO LUAT (node nguoi dung) ----
    honest = Chain()
    tgt = (1<<248)-1
    # tao genesis chung hop luat
    g = make_block([], "00"*32, 0, ND, subsidy(0), tgt)
    honest.add_block(g)
    for h in range(1, 6):
        b = make_block(honest.blocks, honest.tip(), h, ND, subsidy(h), honest.next_target())
        honest.add_block(b)
    print(f"\n[1] MANG NGUOI DUNG dao 6 khoi THEO LUAT (phan thuong dung = {subsidy(0)//COIN} coin/khoi).")
    print(f"    Chieu cao: {honest.height()} | tong cung: {honest.audit_supply()/COIN:,.0f} coin (dung luat).")

    # ---- PHE GIAU: nhieu hashrate hon (dao 10 khoi, DAI HON) + doi luat tu thuong 500 ----
    GREEDY = 500*COIN
    rebel_blocks = [g]                       # cung xuat phat tu genesis
    prev = g.hash()
    rebels = [g]
    # dung mot chain tam de tinh target cho nhanh phe giau (theo dung luat retarget)
    tmp = Chain(); tmp.add_block(g)
    for h in range(1, 11):                    # 10 khoi > 6 khoi => "nhieu hashrate hon"
        b = make_block(tmp.blocks, tmp.tip(), h, PG, GREEDY, tmp.next_target())
        # nhet thang vao store cua tmp de tinh tiep (tmp khong kiem luat vi ta tu add)
        tmp.store[b.hash()] = b; tmp.active.append(b.hash())
        rebels.append(b)
    print(f"\n[2] PHE NHA GIAU bom HASHRATE manh hon -> dao 10 khoi (DAI HON mang nguoi dung),")
    print(f"    nhung moi khoi TU THUONG {GREEDY//COIN} coin (doi luat -> lam phat).")
    print(f"    Neu 'ai manh hon thi thang', phe giau phai thang (10 khoi > 6 khoi).")

    # ---- Node nguoi dung NHAN HET khoi cua phe giau roi tu quyet ----
    print(f"\n[3] Node nguoi dung NHAN TAT CA 10 khoi cua phe giau, roi ap LUAT CUA MINH:")
    for b in rebels[1:]:
        honest.add_block(b)                   # nhan vao; _reorg se tu danh gia
    print(f"    Sau khi nhan het: node nguoi dung dang o chuoi nao?")
    print(f"      -> Chieu cao: {honest.height()} (VAN la chuoi 6 khoi theo luat, KHONG theo phe giau)")
    print(f"      -> Tong cung: {honest.audit_supply()/COIN:,.0f} coin (KHONG he bi lam phat)")
    on_honest_tip = honest.tip()
    followed_rebel = any(honest.tip()==rb.hash() for rb in rebels[1:])
    print(f"      -> Node nguoi dung co ĐI THEO phe giau khong? {followed_rebel}")

    # ---- Chung minh: khoi phe giau bi coi la KHONG HOP LE ----
    print(f"\n[4] Vi sao? Thu kiem mot khoi cua phe giau theo luat nguoi dung:")
    branch = [honest.store[honest.active[0]]] + rebels[1:2]  # genesis + 1 khoi phe giau
    ok, _, _ = honest._replay(branch)
    print(f"      _replay(nhanh phe giau) hop le? {ok}  -> khoi lam phat BI TU CHOI ('coinbase > phan thuong').")

    print("\n"+LINE); print(" KET QUA")
    print(LINE)
    print(f"  - Phe giau co NHIEU hashrate hon (10 khoi > 6) + NHIEU tien hon + doi duoc code CUA HO.")
    print(f"  - Nhung node nguoi dung CHAY LUAT CUA MINH -> vut bo moi khoi lam phat.")
    print(f"  - Phe giau khong keo duoc ai theo -> TU TACH thanh 'dong coin rieng' (nhu Bitcoin Cash 2017).")
    print(f"  - Chuoi ma SO DONG NGUOI DUNG cong nhan van la 'that' (6 khoi, dung luat).")
    print(f"  => 'Ai tra tien / ai manh hon' KHONG mua duoc quyen doi luat.")
    print(f"     Quyen quyet nam o NGUOI CHON CHAY PHAN MEM NAO, khong o tien hay hashrate.")
    print(LINE)
    good = (honest.height()==6 and not followed_rebel and honest.audit_supply()<=MAX_SUPPLY and not ok)
    print(f"\n  Ket qua demo: {'PASS - nguoi dung thang phe giau' if good else 'CHECK'}")
    return 0 if good else 1

if __name__=="__main__": sys.exit(main())
