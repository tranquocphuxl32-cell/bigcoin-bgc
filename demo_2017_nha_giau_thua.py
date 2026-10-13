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
#  Chay tren mang REGTEST (do kho thap).   Chay:  python demo_2017_nha_giau_thua.py
# =====================================================================
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bgcfl_engine import Chain, Params, REGTEST, MAIN, COIN, addr_of
from bigcoin_pq import XmssKey

LINE="="*74
GREEDY=500*COIN

class GreedyRules(Params):
    """Phan mem DA SUA cua phe giau: tu thuong 500 coin/khoi (moi thu khac giong het)."""
    def subsidy(s, height): return GREEDY

def main():
    print(LINE); print(" DEMO 2017: PHE NHA GIAU (nhieu tien + hashrate, doi luat) VAN THUA NGUOI DUNG"); print(LINE)

    nguoi_dung = XmssKey(h=4); phe_giau = XmssKey(h=4)
    ND = addr_of(nguoi_dung.root); PG = addr_of(phe_giau.root)
    P=REGTEST

    # ---- Chuoi THEO LUAT (node nguoi dung) ----
    honest = Chain(params=P)
    for _ in range(5):
        ok,m,_=honest.add_block(honest.make_block(ND)); assert ok, m
    print(f"\n[1] MANG NGUOI DUNG dao {honest.height()-1} khoi THEO LUAT (phan thuong dung = {P.subsidy(1)//COIN} coin/khoi).")
    print(f"    Chieu cao: {honest.height()} | tong cung: {honest.audit_supply()/COIN:,.0f} coin (dung luat).")

    # ---- PHE GIAU: chay phan mem DA SUA luat, dao 10 khoi (DAI HON) ----
    greedy_rules = GreedyRules(P.name, P.magic, P.halving, P.interval, P.maturity, P.pow_limit, P.window)
    rebel_chain = Chain(params=greedy_rules)               # cung genesis, khac luat phat hanh
    rebels=[]
    for _ in range(10):                                     # 10 khoi > 5 khoi => "nhieu hashrate hon"
        b=rebel_chain.make_block(PG, ts=rebel_chain.blocks[-1].ts+P.interval+1)
        ok,m,_=rebel_chain.add_block(b); assert ok, m
        rebels.append(b)
    print(f"\n[2] PHE NHA GIAU bom HASHRATE manh hon -> dao 10 khoi (DAI HON mang nguoi dung),")
    print(f"    nhung moi khoi TU THUONG {GREEDY//COIN} coin (doi luat -> lam phat).")
    print(f"    Theo phan mem cua ho: tong cung = {rebel_chain.audit_supply()/COIN:,.0f} coin.")
    print(f"    Neu 'ai manh hon thi thang', phe giau phai thang (10 khoi > 5 khoi).")

    # ---- Node nguoi dung NHAN HET khoi cua phe giau roi tu quyet ----
    print(f"\n[3] Node nguoi dung NHAN TAT CA 10 khoi cua phe giau, roi ap LUAT CUA MINH:")
    reason=""
    for b in rebels:
        ok,m,_=honest.add_block(b)
        if "inflation" in m or "invalid" in m: reason=reason or m
    print(f"    Sau khi nhan het: node nguoi dung dang o chuoi nao?")
    print(f"      -> Chieu cao: {honest.height()} (VAN la chuoi theo luat, KHONG theo phe giau)")
    print(f"      -> Tong cung: {honest.audit_supply()/COIN:,.0f} coin (KHONG he bi lam phat)")
    followed_rebel = any(honest.tip()==rb.hash() for rb in rebels)
    print(f"      -> Node nguoi dung co ĐI THEO phe giau khong? {followed_rebel}")

    # ---- Chung minh: khoi phe giau bi coi la KHONG HOP LE ----
    print(f"\n[4] Vi sao? Ly do node nguoi dung tu choi nhanh phe giau:")
    print(f"      '{reason}'  -> khoi lam phat BI TU CHOI ('coinbase > phan thuong').")

    print("\n"+LINE); print(" KET QUA")
    print(LINE)
    print(f"  - Phe giau co NHIEU hashrate hon (10 khoi > 5) + NHIEU tien hon + doi duoc code CUA HO.")
    print(f"  - Nhung node nguoi dung CHAY LUAT CUA MINH -> vut bo moi khoi lam phat.")
    print(f"  - Phe giau khong keo duoc ai theo -> TU TACH thanh 'dong coin rieng' (nhu Bitcoin Cash 2017).")
    print(f"  - Chuoi ma SO DONG NGUOI DUNG cong nhan van la 'that' (dung luat).")
    print(f"  => 'Ai tra tien / ai manh hon' KHONG mua duoc quyen doi luat.")
    print(f"     Quyen quyet nam o NGUOI CHON CHAY PHAN MEM NAO, khong o tien hay hashrate.")
    print(LINE)
    good = (honest.height()==6 and not followed_rebel and honest.audit_supply()<=MAIN.max_supply() and "inflation" in reason)
    print(f"\n  Ket qua demo: {'PASS - nguoi dung thang phe giau' if good else 'CHECK'}")
    return 0 if good else 1

if __name__=="__main__": sys.exit(main())
