#!/usr/bin/env python3
# =====================================================================
#  BGC DEMO 2 - (A) P2P MA HOA (BIP324-style) + (B) FORK-CHOICE / REORG
#  Chung minh BGC da san sang cho mang nhieu node khong tin nhau.
# =====================================================================
import os, sys, time, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bgc_node import Node
from bgc_wallet import Wallet
from bgc_engine import Chain, Block, Tx, TxOut, GEN_FOUNDER, GEN_AI, MAX_SUPPLY, COIN
import bgc_secure

BASE="/home/claude/deep/bgc_data2"
def fresh(p):
    if os.path.exists(p): shutil.rmtree(p)
    os.makedirs(p)

def main():
    print("="*76); print(" BGC DEMO 2 - P2P MA HOA + FORK-CHOICE/REORG (san sang nhieu node)"); print("="*76)
    fresh(BASE)
    founder=Wallet(f"{BASE}/founder.wallet",h=8); ai=Wallet(f"{BASE}/ai.wallet",h=8); alice=Wallet(f"{BASE}/alice.wallet",h=6)
    AUTH=founder.key.root.hex()

    # ---------- (A) P2P MA HOA ----------
    print("\n[A] KENH P2P MA HOA (ECDH secp256k1 + ChaCha20-Poly1305):")
    g,r=bgc_secure.self_test()
    print(f"    tu kiem transport: A->B \"{g.decode()}\" | B->A \"{r.decode()}\"  -> ma hoa OK")
    A=Node("A", AUTH, f"{BASE}/nodeA", port=0, authority_wallet=founder)   # encrypted P2P mac dinh
    B=Node("B", AUTH, f"{BASE}/nodeB", port=0)
    print(f"    node A cong {A.p2p.port} | node B cong {B.p2p.port} | ma hoa = {A.p2p.enc}")
    B.connect(A.p2p.port); time.sleep(0.5)
    g_=Tx([],[TxOut(GEN_FOUNDER,founder.address,"founder 11tr KHOA",8),TxOut(GEN_AI,ai.address,"AI 10tr")],coinbase=True)
    A.mine(extra_txs=[g_]); time.sleep(0.5)
    tx=ai.send(A.chain, alice.address, 100, memo="AI cap von (qua kenh ma hoa)")
    A.submit_tx(tx); time.sleep(0.3); A.mine(); time.sleep(0.6)
    print(f"    A height={A.chain.height()} supply={A.chain.audit_supply()/COIN:,.0f}")
    print(f"    B height={B.chain.height()} supply={B.chain.audit_supply()/COIN:,.0f}  (dong bo qua kenh MA HOA)")
    print(f"    Alice tren A={A.chain.balance(alice.address)/COIN:.0f}, tren B={B.chain.balance(alice.address)/COIN:.0f}  (KHOP)")
    encA=(A.chain.audit_supply()==MAX_SUPPLY and A.chain.tip()==B.chain.tip())
    A.close(); B.close(); time.sleep(0.2)

    # ---------- (B) FORK-CHOICE / REORG (muc engine, tat dinh) ----------
    print("\n[B] FORK-CHOICE / REORG - nap 2 nhanh canh tranh, node chon nhanh DAI HON:")
    C=Chain(AUTH)   # chuoi sach
    def sign_block(index, prev, txs):
        b=Block(index, prev, txs, AUTH); b.sig=founder.sign(b.sighash()); return b
    # genesis + 1 khoi chung C1
    fw=Wallet(f"{BASE}/f2.wallet",h=8); aiw=Wallet(f"{BASE}/ai2.wallet",h=8); al=Wallet(f"{BASE}/al2.wallet",h=6)
    AUTH2=fw.key.root.hex(); C=Chain(AUTH2)
    def sb(index,prev,txs):
        b=Block(index,prev,txs,AUTH2); b.sig=fw.sign(b.sighash()); return b
    gen=Tx([],[TxOut(GEN_FOUNDER,fw.address,"f11"),TxOut(GEN_AI,aiw.address,"ai10")],coinbase=True)
    C.add_block(sb(0,"0"*64,[gen]))
    C.add_block(sb(1,C.tip(),[]))               # khoi chung C1
    common_tip=C.tip(); common_h=C.height()
    print(f"    chuoi chung: height={common_h}, tip={common_tip[:14]}..")

    # txA: AI -> Alice 100 (chi xuat hien o nhanh X)
    txA=aiw.send(C, al.address, 100, memo="chi co o nhanh X")
    blkX=sb(2, common_tip, [txA])               # NHANH X: 1 khoi (height se = 3)
    C.add_block(blkX)
    print(f"\n    + nap NHANH X (1 khoi, co txA): height={C.height()} | Alice={C.balance(al.address)/COIN:.0f} | tip={C.tip()[:14]}..")

    # NHANH Y: 2 khoi tren CUNG common_tip, KHONG co txA -> dai hon (height 4)
    blkY1=sb(2, common_tip, [])
    blkY2=sb(3, blkY1.hash(), [])
    C.add_block(blkY1)
    print(f"    + nap Y1 (bang chieu cao X): height={C.height()} | tip van X? {C.tip()==blkX.hash()}  (hoa -> giu X, first-seen)")
    _,_,reorged=C.add_block(blkY2)
    print(f"    + nap Y2 (nhanh Y dai hon) -> REORG={reorged}: height={C.height()} | tip=Y2? {C.tip()==blkY2.hash()}")
    print(f"      Alice sau reorg = {C.balance(al.address)/COIN:.0f} (txA bi bo khoi chuoi)")
    print(f"      txA quay lai mempool? {txA.txid() in C.mempool}  | supply van = {C.audit_supply()/COIN:,.0f} (21tr? {C.audit_supply()==MAX_SUPPLY})")

    # chung minh double-spend bi reorg vo hieu, nhung khong tao/mat coin
    checks=[("A: P2P ma hoa dong bo + 21tr", encA),
            ("B: reorg sang nhanh dai hon", reorged and C.tip()==blkY2.hash()),
            ("B: txA bi loai khoi chuoi active", C.balance(al.address)==0),
            ("B: txA tro lai mempool", txA.txid() in C.mempool),
            ("B: supply van 21tr sau reorg", C.audit_supply()==MAX_SUPPLY)]
    allok=all(v for _,v in checks)
    print("\n[C] KIEM CHUNG:")
    for k,v in checks: print(f"    [{'OK' if v else 'FAIL'}] {k}")

    print("\n"+"="*76); print(f" KET QUA: {'TAT CA PASS' if allok else 'CO LOI'}")
    print("  - P2P MA HOA: 2 node dong bo qua kenh ChaCha20-Poly1305 (ke nghe len mu).")
    print("  - FORK-CHOICE: node tu chon nhanh dai nhat hop le; reorg bo nhanh ngan, tx tro lai mempool.")
    print("  - Reorg KHONG tao/mat coin: 21tr bat bien suot. San sang cho mang nhieu node khong tin nhau.")
    print("  *** LUU Y ***")
    print("  - Fork-choice o day = 'nhanh dai nhat' (PoA). That te can them: chong spam khoi, gioi han")
    print("    do sau reorg, va nhieu authority luan phien de khong 1 ben doc quyen tao nhanh.")
    print("  - Ma hoa KENH dung ECDH co dien (lo luong tu chi lo metadata mang, KHONG lo tien);")
    print("    coin van ky hash-based PQ. Co the nang KEM hau luong tu (ML-KEM) sau.")
    print("="*76)
    return 0 if allok else 1

if __name__=="__main__": sys.exit(main())
