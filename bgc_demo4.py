#!/usr/bin/env python3
# =====================================================================
#  BGC DEMO 4 - LIVENESS kieu Clique: 1 authority OFFLINE, mang VAN chay
#  - 3 authority luan phien. Khi nguoi den luot offline, nguoi khac (khong ky
#    lien tiep) ky TRAI LUOT de chuoi khong ket. Khoi trai luot co trong so THAP.
#  - Fork-choice chon nhanh TONG TRONG SO cao nhat -> khi nguoi dung luot online lai,
#    nhanh "dung luot" (trong so cao) se thang -> tu dong uu tien trat tu chuan.
#  - Luat "khong ky lien tiep" (recent-signer) chong 1 nguoi doc chiem khi thieu nguoi.
# =====================================================================
import os, sys, time, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bgc_node import Node
from bgc_wallet import Wallet
from bgc_engine import Chain, Block, Tx, TxOut, GEN_FOUNDER, GEN_AI, MAX_SUPPLY, COIN, FINALITY

BASE="/home/claude/deep/bgc_data4"
def fresh(p):
    if os.path.exists(p): shutil.rmtree(p)
    os.makedirs(p)

def main():
    print("="*78); print(" BGC DEMO 4 - LIVENESS: 1 authority OFFLINE, mang van chay (Clique-style)"); print("="*78)
    fresh(BASE)
    w=[Wallet(f"{BASE}/a{i}.w",h=10) for i in range(3)]; ai=Wallet(f"{BASE}/ai.w",h=8); al=Wallet(f"{BASE}/al.w",h=6)
    AUTHS=[x.key.root.hex() for x in w]
    order=sorted(AUTHS); by={x.key.root.hex():x for x in w}
    N=len(order); LIMIT=N//2
    nm={order[0]:"Auth0",order[1]:"Auth1",order[2]:"Auth2"}
    print(f"\n[1] {N} authority: {[nm[o] for o in order]} | luat: khong ky lien tiep (LIMIT={LIMIT}), dung luot=2 diem / trai luot=1")

    # ---------- (A) ENGINE-LEVEL: Auth1 OFFLINE, chuoi van tien ----------
    print(f"\n[2] GIA LAP Auth1 OFFLINE. Dung signer: nguoi den luot neu online+khong recent, else nguoi khac:")
    D=Chain(AUTHS)
    online={order[0],order[2]}                        # Auth1 offline
    def choose(i, recent):
        exp=D.expected_auth(i); cand=[exp]+[a for a in order if a!=exp]
        for a in cand:
            if a in online and a!=recent: return a
        return None
    def sign(i,prev,txs,signer,ts):
        b=Block(i,prev,txs,signer,ts=ts); b.sig=by[signer].sign(b.sighash()); return b
    # genesis
    s0=choose(0,None); g=Tx([],[TxOut(GEN_FOUNDER,w[0].address,"f"),TxOut(GEN_AI,ai.address,"ai")],coinbase=True)
    D.add_block(sign(0,"0"*64,[g],s0,1000)); recent=s0; log=[(0,nm[D.expected_auth(0)],nm[s0])]
    for i in range(1,10):
        sgn=choose(i,recent)
        D.add_block(sign(i,D.tip(),[],sgn,1000+i)); log.append((i,nm[D.expected_auth(i)],nm[sgn])); recent=sgn
    print(f"    {'khoi':>4} {'den_luot':>10} {'nguoi_ky':>10} {'trang_thai':>12}")
    for i,exp,got in log:
        print(f"    {i:>4} {exp:>10} {got:>10} {'DUNG LUOT(2)' if exp==got else 'trai luot(1)':>12}")
    b_signed=sum(1 for _,_,g_ in log if g_=="Auth1")
    print(f"    -> height={D.height()}, Auth1 (offline) ky {b_signed} khoi, supply={D.audit_supply()/COIN:,.0f}")
    live_ok=(D.height()==10 and b_signed==0 and D.audit_supply()==MAX_SUPPLY)

    # ---------- (B) weight: nhanh 'dung luot' thang nhanh 'trai luot' ----------
    print(f"\n[3] Khi Auth1 ONLINE lai: nhanh DUNG LUOT (trong so cao) se thang nhanh trai luot:")
    _,_,w_off=D._replay([D.store[h] for h in D.active])
    # dung 1 nhanh thay the TU DAU, tat ca DUNG LUOT (Auth1 online) - cung do dai
    D2=Chain(AUTHS); online2=set(order)
    def sign2(i,prev,txs,signer,ts): b=Block(i,prev,txs,signer,ts=ts); b.sig=by[signer].sign(b.sighash()); return b
    s0=order[0]; D2.add_block(sign2(0,"0"*64,[Tx([],[TxOut(GEN_FOUNDER,w[0].address,"f"),TxOut(GEN_AI,ai.address,"ai")],coinbase=True)],s0,7000))
    for i in range(1,10): D2.add_block(sign2(i,D2.tip(),[],D2.expected_auth(i),7000+i))  # tat ca dung luot
    _,_,w_on=D2._replay([D2.store[h] for h in D2.active])
    print(f"    tong trong so nhanh CO Auth1 offline (trai luot): {w_off}")
    print(f"    tong trong so nhanh TAT CA dung luot (Auth1 online): {w_on}")
    print(f"    -> nhanh dung luot nang hon ({w_on} > {w_off}) nen fork-choice uu tien no khi co the.")
    weight_ok=(w_on>w_off)

    # ---------- (C) REAL NODES: Auth1 offline, Auth0 & Auth2 giu mang song ----------
    print(f"\n[4] 3 NODE THAT: Auth1 KHONG ket noi (offline). Auth0 & Auth2 dao, cung quan sat:")
    nodeA=Node("Auth0",AUTHS,f"{BASE}/nA",authority_wallet=by[order[0]])
    nodeC=Node("Auth2",AUTHS,f"{BASE}/nC",authority_wallet=by[order[2]])
    nodeA.connect(nodeC.p2p.port); time.sleep(0.4)
    onlineR={order[0],order[2]}; node_of={order[0]:nodeA,order[2]:nodeC}
    recent=None
    g=Tx([],[TxOut(GEN_FOUNDER,w[0].address,"f",0),TxOut(GEN_AI,ai.address,"ai")],coinbase=True)
    for i in range(9):
        sgn=None; exp=nodeA.chain.expected_auth(i); cand=[exp]+[a for a in order if a!=exp]
        for a in cand:
            if a in onlineR and a!=recent: sgn=a; break
        n=node_of[sgn]
        n.mine(extra_txs=[g] if i==0 else None, force=True); recent=sgn; time.sleep(0.3)
    time.sleep(1.0)
    print(f"    Auth0: height={nodeA.chain.height()} tip={nodeA.chain.tip()[:12]}..")
    print(f"    Auth2: height={nodeC.chain.height()} tip={nodeC.chain.tip()[:12]}..")
    real_ok=(nodeA.chain.height()>=8 and nodeA.chain.tip()==nodeC.chain.tip() and nodeA.chain.audit_supply()==MAX_SUPPLY)
    print(f"    -> 2/3 authority online van tien khoi & dong bo (Auth1 offline khong lam ket mang).")
    nodeA.close(); nodeC.close()

    checks=[("liveness: Auth1 offline, chuoi van cao 10", live_ok),
            ("weight: nhanh dung luot nang hon trai luot", weight_ok),
            ("real: 2/3 node online van dong bo + 21tr", real_ok),
            ("recent-signer: khong ai ky 2 khoi lien tiep", all(log[i][2]!=log[i+1][2] for i in range(len(log)-1)))]
    allok=all(v for _,v in checks)
    print("\n[5] KIEM CHUNG:")
    for k,v in checks: print(f"    [{'OK' if v else 'FAIL'}] {k}")
    print("\n"+"="*78); print(f" KET QUA: {'TAT CA PASS' if allok else 'CO LOI'}")
    print("  - LIVENESS: nguoi den luot offline -> nguoi khac ky trai luot -> mang KHONG ket.")
    print("  - Khoi trai luot trong so 1 < dung luot 2 -> fork-choice uu tien trat tu chuan khi du nguoi.")
    print("  - Luat khong-ky-lien-tiep: can DA SO authority online (N=3 chiu duoc 1 offline).")
    print("  *** LUU Y ***")
    print("  - Neu qua nua authority offline -> mang ket (dung thiet ke: can da so trung thuc online).")
    print("  - That te can them: timeout thuc (khi nao duoc ky trai luot), phat authority khong hoat dong,")
    print("    va co che them/bot authority. Day van la federation, chua phai phi tap trung mo.")
    print("="*78)
    return 0 if allok else 1

if __name__=="__main__": sys.exit(main())
