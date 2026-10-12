#!/usr/bin/env python3
# =====================================================================
#  BGC DEMO 3 - 3 NODE + ROUND-ROBIN POA (nhieu authority luan phien) + FINALITY
#  (A) 2 authority luan phien ky khoi, node thu 3 chi quan sat -> ca 3 HOI TU.
#  (B) Finality: nhanh canh tranh fork SAU diem chot -> BI TU CHOI du dai hon & ky dung.
#  Y nghia: khong 1 authority nao mot minh viet lai lich su; khoi cu duoc "chot".
# =====================================================================
import os, sys, time, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bgc_node import Node
from bgc_wallet import Wallet
from bgc_engine import Chain, Block, Tx, TxOut, GEN_FOUNDER, GEN_AI, MAX_SUPPLY, COIN, FINALITY

BASE="/home/claude/deep/bgc_data3"
def fresh(p):
    if os.path.exists(p): shutil.rmtree(p)
    os.makedirs(p)
def wait_all(nodes, h, timeout=8):
    t0=time.time()
    while time.time()-t0<timeout:
        if all(n.chain.height()==h and n.chain.tip()==nodes[0].chain.tip() for n in nodes): return True
        time.sleep(0.1)
    return False

def main():
    print("="*76); print(" BGC DEMO 3 - 3 node + ROUND-ROBIN PoA (2 authority luan phien) + FINALITY"); print("="*76)
    fresh(BASE)
    w1=Wallet(f"{BASE}/a1.w",h=8); w2=Wallet(f"{BASE}/a2.w",h=8); ai=Wallet(f"{BASE}/ai.w",h=8); al=Wallet(f"{BASE}/al.w",h=6)
    AUTHS=[w1.key.root.hex(), w2.key.root.hex()]
    order=sorted(AUTHS)
    by_root={w1.key.root.hex():w1, w2.key.root.hex():w2}
    print(f"\n[1] 2 AUTHORITY luan phien (round-robin). Thu tu: #0={order[0][:12]}.. #1={order[1][:12]}..")

    A=Node("A", AUTHS, f"{BASE}/A", authority_wallet=w1)
    B=Node("B", AUTHS, f"{BASE}/B", authority_wallet=w2)
    C=Node("C", AUTHS, f"{BASE}/C")                       # node QUAN SAT (khong ky duoc)
    A.connect(B.p2p.port); C.connect(A.p2p.port); C.connect(B.p2p.port); time.sleep(0.5)
    print(f"[2] Node A(auth) B(auth) C(quan sat) da noi P2P ma hoa.")

    def mine_turn(extra=None):
        for n in (A,B):
            if n.my_turn():
                ok,m=n.mine(extra_txs=extra); return n.name,ok,m
        return None,False,"khong ai den luot"

    # genesis (index0 -> authority #0 ky)
    g=Tx([],[TxOut(GEN_FOUNDER,w1.address,"founder 11tr",0),TxOut(GEN_AI,ai.address,"AI 10tr")],coinbase=True)
    who,ok,m=mine_turn([g]); time.sleep(0.5)
    print(f"\n[3] GENESIS do authority '{who}' ky (den luot index 0): {ok}")
    # vai giao dich + dao luan phien
    A.submit_tx(ai.send(A.chain, al.address, 100, memo="AI cap von")); time.sleep(0.3)
    heights_log=[]
    for _ in range(7):
        who,ok,m=mine_turn(); time.sleep(0.35); heights_log.append(who)
    wait_all([A,B,C], A.chain.height())
    print(f"[4] Dao {len(heights_log)} khoi, nguoi ky luan phien: {heights_log}")
    print(f"    (thay A,B xen ke -> round-robin; khong ai ky 2 khoi lien tiep)")
    print(f"\n[5] CA 3 NODE HOI TU:")
    for n in (A,B,C): print(f"    {n.name}: height={n.chain.height()} tip={n.chain.tip()[:14]}.. supply={n.chain.audit_supply()/COIN:,.0f}")
    conv=(A.chain.tip()==B.chain.tip()==C.chain.tip() and A.chain.audit_supply()==MAX_SUPPLY)

    # ---------- (B) FINALITY: nhanh fork SAU diem chot bi tu choi ----------
    print(f"\n[6] FINALITY (chot sau {FINALITY} khoi) - thu reorg SAU va GAN diem chot:")
    # dung chuoi tat dinh de kiem soat (ky round-robin bang ca 2 khoa)
    D=Chain(AUTHS)
    def sign(index,prev,txs,ts=None):   # ts rieng -> khoi fork KHAC khoi chinh (hash khac)
        w=by_root[D.expected_auth(index)]; b=Block(index,prev,txs,w.key.root.hex(),ts=ts); b.sig=w.sign(b.sighash()); return b
    g2=Tx([],[TxOut(GEN_FOUNDER,w1.address,"f"),TxOut(GEN_AI,ai.address,"ai")],coinbase=True)
    D.add_block(sign(0,"0"*64,[g2],ts=1000))
    for i in range(1,10): D.add_block(sign(i,D.tip(),[],ts=1000+i))   # chuoi chinh cao 10
    print(f"    chuoi chinh: height={D.height()}, tip={D.tip()[:14]}..")
    main_tip=D.tip()

    # (b1) fork GAN tip (do sau 2 < FINALITY) + dai hon 1 -> DUOC reorg
    fork_at=D.height()-2                                   # fork trong vung chua chot
    prev=D.active[fork_at-1]
    br=[]; p=prev
    for i in range(fork_at, D.height()+1):                 # dai hon chuoi chinh 1 khoi
        b=sign(i,p,[],ts=4000+i); br.append(b); p=b.hash()
    for b in br: _,_,re=D.add_block(b)
    print(f"    (b1) fork o do sau 2 (< {FINALITY}), dai hon 1 -> reorg? {D.tip()!=main_tip} (height={D.height()})")
    shallow_ok=(D.tip()!=main_tip)

    # (b2) fork SAU diem chot (do sau > FINALITY): fork tu khoi 1 -> rat dai -> VAN BI TU CHOI
    deep_prev=D.active[0]                                  # fork ngay sau genesis (do sau ~ toan chuoi)
    br2=[]; p=deep_prev
    for i in range(1, D.height()+5):                       # dai hon han chuoi hien tai
        b=sign(i,p,[],ts=5000+i); br2.append(b); p=b.hash()
    tip_before=D.tip(); h_before=D.height()
    for b in br2: D.add_block(b)
    deep_rejected=(D.tip()==tip_before and D.height()==h_before)
    print(f"    (b2) fork SAU diem chot (do sau > {FINALITY}), dai hon NHIEU -> reorg? {not deep_rejected}")
    print(f"         -> finality {'BAO VE: tu choi reorg sau (tip khong doi)' if deep_rejected else 'THAT BAI'}")

    # round-robin: doc chuoi da hoi tu, moi khoi PHAI do dung authority[index%2] ky, va ca 2 deu ky
    sig_seq=[blk.auth for blk in A.chain.blocks]
    rr_ok = all(sig_seq[i]==A.chain.expected_auth(i) for i in range(len(sig_seq))) and len(set(sig_seq))==2 \
            and all(sig_seq[i]!=sig_seq[i+1] for i in range(len(sig_seq)-1))
    checks=[("3 node hoi tu + 21tr", conv),
            ("round-robin: khoi i do authority[i%2] ky, ca 2 xen ke", rr_ok),
            ("finality: reorg NONG (<F) duoc", shallow_ok),
            ("finality: reorg SAU (>F) bi tu choi", deep_rejected),
            ("21tr giu nguyen", D.audit_supply()==MAX_SUPPLY)]
    allok=all(v for _,v in checks)
    print("\n[7] KIEM CHUNG:")
    for k,v in checks: print(f"    [{'OK' if v else 'FAIL'}] {k}")
    A.close(); B.close(); C.close()
    print("\n"+"="*76); print(f" KET QUA: {'TAT CA PASS' if allok else 'CO LOI'}")
    print("  - Round-robin PoA: khoi index i PHAI do authority[i % N] ky -> 1 authority KHONG the")
    print("    mot minh dao chuoi dai (can khoa cua ca nhom) -> giam doc quyen/kiem duyet.")
    print("  - Finality: khoi cu hon FINALITY duoc CHOT -> khong the bi reorg -> chong 'viet lai lich su'.")
    print("  - 3 node (2 ky + 1 quan sat) hoi tu cung 1 chuoi qua P2P ma hoa.")
    print("  *** LUU Y ***")
    print("  - Round-robin can co che 'bo luot' neu 1 authority offline (liveness) - chua lam o day.")
    print("  - Nhieu authority = tin cay PHAN TAN hon 1 nguoi, nhung VAN la tap cho phep (federation),")
    print("    chua phai phi tap trung mo nhu PoW/PoS. Lo trinh: mo rong tap authority / chuyen co che.")
    print("="*76)
    return 0 if allok else 1

if __name__=="__main__": sys.exit(main())
