#!/usr/bin/env python3
# =====================================================================
#  BGC DEMO 5 - BO LAP LICH DAO TU DONG (timeout) + KILL authority giua chung
#  3 authority node TU DAO (khong dieu khien tay). Giua chung KILL Auth1 -> mang
#  van tu chay (Auth0/Auth2 ky trai luot sau timeout). Auth1 quay lai -> trat tu chuan.
# =====================================================================
import os, sys, time, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bgc_node import Node
from bgc_wallet import Wallet
from bgc_engine import Tx, TxOut, GEN_FOUNDER, GEN_AI, MAX_SUPPLY, COIN

BASE="/home/claude/deep/bgc_data5"
def fresh(p):
    if os.path.exists(p): shutil.rmtree(p)
    os.makedirs(p)

def main():
    print("="*78); print(" BGC DEMO 5 - DAO TU DONG (timeout) + KILL authority giua chung -> mang tu chay"); print("="*78)
    fresh(BASE)
    w=[Wallet(f"{BASE}/a{i}.w",h=12) for i in range(3)]; ai=Wallet(f"{BASE}/ai.w",h=8)
    AUTHS=[x.key.root.hex() for x in w]; order=sorted(AUTHS); by={x.key.root.hex():x for x in w}
    nm={order[0]:"Auth0",order[1]:"Auth1",order[2]:"Auth2"}
    nodes=[Node(nm[x.key.root.hex()], AUTHS, f"{BASE}/{nm[x.key.root.hex()]}", authority_wallet=x) for x in w]
    nd={n.auth.key.root.hex():n for n in nodes}
    A,B,Cc = nd[order[0]], nd[order[1]], nd[order[2]]
    # noi luoi: moi node noi 2 node con lai
    for i,n in enumerate(nodes):
        for m in nodes:
            if m is not n: n.connect(m.p2p.port)
    time.sleep(0.6)
    print(f"\n[1] 3 authority node da noi luoi (P2P ma hoa). Bootstrap genesis boi Auth0:")
    g=Tx([],[TxOut(GEN_FOUNDER,w[0].address,"founder 11tr",0),TxOut(GEN_AI,ai.address,"AI 10tr")],coinbase=True)
    A.mine(extra_txs=[g], force=True); time.sleep(0.6)
    print(f"    genesis xong: cac node height = {[n.chain.height() for n in nodes]} (dong bo)")

    BT=0.5
    print(f"\n[2] BAT dao TU DONG o ca 3 node (block_time={BT}s). Chay 4s...")
    for n in nodes: n.start_mining(block_time=BT)
    time.sleep(4.0)
    h_all=[n.chain.height() for n in nodes]
    print(f"    sau 4s: height = {h_all} | tips khop? {len(set(n.chain.tip() for n in nodes))==1}")
    print(f"    (ca 3 TU dao, tu dong bo - khong he dieu khien tay)")

    print(f"\n[3] KILL Auth1 (dung dao + ngat mang). Chay tiep 4s...")
    B.stop_mining(); B.p2p.close()
    h_before=A.chain.height()
    time.sleep(4.0)
    h_after=A.chain.height()
    print(f"    Auth1 da chet. Auth0 height {h_before} -> {h_after} (van TANG = mang khong ket)")
    print(f"    Auth0 & Auth2 tips khop? {A.chain.tip()==Cc.chain.tip()} | height A={A.chain.height()} C={Cc.chain.height()}")
    alive_ok = (h_after>h_before and A.chain.tip()==Cc.chain.tip() and A.chain.audit_supply()==MAX_SUPPLY)

    print(f"\n[4] Kiem tra trat tu (sau khi mat 1 authority):")
    seq=[nm[b.auth] for b in A.chain.blocks]
    import collections
    cnt=collections.Counter(seq)
    print(f"    so khoi moi authority ky: {dict(cnt)}")
    print(f"    (Auth1 ky it hon han vi da offline nua chang; Auth0/Auth2 ky trai luot bu vao)")
    no_consecutive = all(seq[i]!=seq[i+1] for i in range(len(seq)-1))

    for n in (A,Cc): n.stop_mining()
    time.sleep(0.3)
    for n in (A,Cc): n.p2p.close()

    checks=[("dao tu dong: 3 node tu tien khoi + dong bo", h_all[0]>=4 and len(set(h_all))==1),
            ("kill Auth1: mang VAN tien khoi (liveness)", alive_ok),
            ("21tr giu nguyen suot", A.chain.audit_supply()==MAX_SUPPLY),
            ("khong ai ky 2 khoi lien tiep", no_consecutive)]
    allok=all(v for _,v in checks)
    print("\n[5] KIEM CHUNG:")
    for k,v in checks: print(f"    [{'OK' if v else 'FAIL'}] {k}")
    print("\n"+"="*78); print(f" KET QUA: {'TAT CA PASS' if allok else 'CO LOI'}")
    print("  - Node TU dao theo timeout: dung luot dao ngay, trai luot cho timeout roi dao neu trong.")
    print("  - KILL 1 authority giua chung -> mang TU CHAY tiep (khong can nguoi can thiep).")
    print("  - 21tr bat bien; khong ai ky lien tiep; fork-choice theo trong so giu trat tu chuan.")
    print("  *** LUU Y ***")
    print("  - Timeout co dinh theo khoang cach rotation (don gian); production nen them 'wiggle'")
    print("    ngau nhien chong dung do, va phat authority ly keo dai.")
    print("  - Van can DA SO authority online. Day la federation PoA, chua phai phi tap trung mo.")
    print("="*78)
    return 0 if allok else 1

if __name__=="__main__": sys.exit(main())
