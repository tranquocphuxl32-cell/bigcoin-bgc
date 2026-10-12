#!/usr/bin/env python3
# =====================================================================
#  BGC DEMO - chay 2 NODE THAT noi nhau qua P2P, dong bo, giao dich, luu dia, explorer.
#  Chung minh he BGC hop nhat (PQ + 21tr + timelock + memo + PoA + P2P + luu dia) CHAY.
# =====================================================================
import os, sys, time, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bgc_node import Node
from bgc_wallet import Wallet
from bgc_engine import COIN, MAX_SUPPLY, Chain
import bgc_explorer

BASE="/home/claude/deep/bgc_data"
def fresh(p):
    if os.path.exists(p): shutil.rmtree(p)
    os.makedirs(p)
def wait_sync(a,b,timeout=6.0):
    t0=time.time()
    while time.time()-t0<timeout:
        if a.chain.height()==b.chain.height() and a.chain.tip()==b.chain.tip(): return True
        time.sleep(0.1)
    return False

def main():
    print("="*74); print(" BGC - HE HOAN CHINH: 2 node P2P + PQ + 21tr + timelock + memo + luu dia"); print("="*74)
    fresh(BASE)
    # --- vi (co luu chi so leaf ra dia) ---
    founder=Wallet(f"{BASE}/founder.wallet",h=8)   # authority + giu 11tr
    ai     =Wallet(f"{BASE}/ai.wallet",h=8)        # quy AI 10tr
    alice  =Wallet(f"{BASE}/alice.wallet",h=6)
    UNLOCK=8
    print(f"\n[1] Vi tao xong (khang luong tu, luu leaf ra dia). Authority = Founder.")
    print(f"    Founder {founder.address[:22]}.. | AI {ai.address[:22]}.. | Alice {alice.address[:22]}..")

    # --- node A (authority) + node B (nguoi dung thuong), noi P2P ---
    A=Node("A", founder.key.root.hex(), f"{BASE}/nodeA", port=0, authority_wallet=founder)
    B=Node("B", founder.key.root.hex(), f"{BASE}/nodeB", port=0)
    A.founder_addr=founder.address; A.ai_addr=ai.address; A.unlock=UNLOCK
    print(f"\n[2] Node A (authority) cong {A.p2p.port} | Node B cong {B.p2p.port}")
    B.connect(A.p2p.port); time.sleep(0.4)

    # --- genesis tren A: 21tr, 11tr founder KHOA, 10tr AI ---
    from bgc_engine import Tx, TxOut, GEN_FOUNDER, GEN_AI
    g=Tx([],[TxOut(GEN_FOUNDER,founder.address,"founder 11tr - KHOA vesting",UNLOCK),
             TxOut(GEN_AI,ai.address,"AI treasury 10tr")],coinbase=True)
    A.mine(extra_txs=[g]); time.sleep(0.5)
    print(f"\n[3] GENESIS tren A (21tr): A height={A.chain.height()} supply={A.chain.audit_supply()/COIN:,.0f}")
    print(f"    -> P2P dong bo sang B: B height={B.chain.height()} supply={B.chain.audit_supply()/COIN:,.0f}  (=21tr? {B.chain.audit_supply()==MAX_SUPPLY})")

    # --- AI tra Alice qua mempool + relay P2P, A dao ---
    tx=ai.send(A.chain, alice.address, 100, memo="AI cap von cho nguoi dung")
    A.submit_tx(tx); time.sleep(0.3); A.mine(); time.sleep(0.5)
    print(f"\n[4] AI -> Alice 100 BGC (truyen P2P, A dao):")
    print(f"    A: Alice={A.chain.balance(alice.address)/COIN:.0f} | B: Alice={B.chain.balance(alice.address)/COIN:.0f}  (2 node KHOP)")

    # --- Alice nho AI lam viec (memo on-chain) ---
    tx=alice.send(A.chain, ai.address, 5, memo="AI oi giai thich XMSS (tra 5 BGC)")
    A.submit_tx(tx); time.sleep(0.3); A.mine(); time.sleep(0.5)
    print(f"\n[5] Alice -> AI 5 BGC + yeu cau on-chain. AI treasury={A.chain.balance(ai.address)/COIN:,.0f}")

    # --- founder thu tieu 11tr khoa som -> CHAN ---
    print(f"\n[6] Founder thu tieu 11tr KHOA som (height {A.chain.height()} < {UNLOCK}):")
    try:
        bad=founder.send(A.chain, alice.address, 1_000_000, memo="ban thao")
        ok,m=A.chain.check_tx(bad); print(f"    -> {'CHAN' if not ok else 'LOT'}: {m}")
    except RuntimeError as e: print(f"    -> CHAN ngay khi tao tx: {e}")

    # --- dao toi mo khoa ---
    while A.chain.height()<UNLOCK: A.mine(); time.sleep(0.15)
    wait_sync(A,B)
    print(f"\n[7] Dao toi khoi {A.chain.height()} -> 11tr mo khoa. Founder tieu duoc={A.chain.balance(founder.address,True)/COIN:,.0f}")
    print(f"    B dong bo: height={B.chain.height()} supply={B.chain.audit_supply()/COIN:,.0f}")

    # --- LUU DIA: nap lai tu dia vao node moi, tu kiem lai ---
    print(f"\n[8] LUU DIA + NAP LAI (node moi doc file, tu xac minh lai tu genesis):")
    C=Chain(founder.key.root.hex(), datadir=f"{BASE}/nodeA"); n=C.load()
    print(f"    nap {n} khoi tu dia; supply tu tinh lai = {C.audit_supply()/COIN:,.0f} (=21tr? {C.audit_supply()==MAX_SUPPLY})")

    # --- EXPLORER: xuat HTML cho cong dong xem ---
    out=bgc_explorer.render(A.chain, "/mnt/user-data/outputs/bgc_explorer.html")
    print(f"\n[9] EXPLORER xuat: {out}")

    print("\n[10] KIEM CHUNG CUOI:")
    wait_sync(A,B)
    print(f"    (A height={A.chain.height()} tip={A.chain.tip()[:12]}.. | B height={B.chain.height()} tip={B.chain.tip()[:12]}..)")
    checks=[("A supply=21tr",A.chain.audit_supply()==MAX_SUPPLY),
            ("B supply=21tr",B.chain.audit_supply()==MAX_SUPPLY),
            ("A==B height",A.chain.height()==B.chain.height()),
            ("A==B tip",A.chain.tip()==B.chain.tip()),
            ("nap lai dia=21tr",C.audit_supply()==MAX_SUPPLY),
            ("Alice khop 2 node",A.chain.balance(alice.address)==B.chain.balance(alice.address))]
    allok=all(v for _,v in checks)
    for k,v in checks: print(f"    [{'OK' if v else 'FAIL'}] {k}")
    wait_sync(A,B)
    A.close(); B.close()
    print("\n"+"="*74); print(f" KET QUA: {'TAT CA PASS - he BGC hop nhat CHAY THAT' if allok else 'CO LOI'}")
    print("  Node A & B dong bo qua P2P; 21tr co dinh (supply-guard moi khoi); 11tr khoa on-chain;")
    print("  chu ky khang luong tu; luu dia + nap lai tu kiem; explorer HTML cho cong dong.")
    print("="*74)
    return 0 if allok else 1

if __name__=="__main__": sys.exit(main())
