#!/usr/bin/env python3
# =====================================================================
#  BIGCOIN-M2M - tang kinh te MAY-VOI-MAY (AI <-> robot) tren BGC khang luong tu
#  Dung chung engine bigcoin_pq.py (cung thu muc) -> ca folder Bigcoin-BGC la 1 khoi doc lap.
#  --------------------------------------------------------------------
#  LUU Y ANH DAN:
#   (1) BGC phuc vu AI VA ROBOT: moi AI-agent / robot la MOT VI tu tri, tu ky giao
#       dich (chu ky hash-based khang luong tu), tu tra tien cho nhau de thue dich vu.
#   (2) 21,000,000 CO DINH: kiem chung sau MOI khoi bang 'supply guard' - neu tong
#       lech 21tr thi node TU CHOI khoi do (khong the in them du 1 satoshi).
#  Vong gia tri minh hoa: Nguoi -> AI-agent -> Robot giao hang -> Tram sac (robot).
#  Tien chay qua chuoi may moc tu dong, 21tr luon bao toan.
# =====================================================================
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bigcoin_pq import (XmssKey, NodePQ, Tx, TxIn, TxOut, spend, mk_block, addr_of,
                        COIN, MAX_SUPPLY, GEN_AI, GEN_FOUNDER)

def supply_guard(node, where):
    """CONG DONG YEU CAU: sau MOI khoi, tong cung PHAI = 21tr. Khong thi bao dong."""
    s=node.audit_supply()
    ok = (s==MAX_SUPPLY)
    print(f"      [supply-guard] sau {where}: {s/COIN:,.0f} BGC  {'OK (=21tr)' if ok else '!!! VI PHAM 21tr !!!'}")
    return ok

def pay(node, frm_key, frm_name, to_addr, to_name, amount, memo, auth):
    tx=spend(node, frm_key, to_addr, amount*COIN, memo=memo)
    ok,m=node.apply_block(mk_block(node,[tx],auth))
    tag=f"{frm_name} -> {to_name}: {amount} BGC"
    print(f"    {tag:<42} | memo: \"{memo}\"  [{'OK' if ok else m}]")
    return ok

def main():
    print("="*78); print(" BIGCOIN-M2M - kinh te MAY-VOI-MAY (AI <-> robot), khang luong tu, 21tr co dinh"); print("="*78)

    # --- cac tac nhan: moi AI/robot la 1 vi tu tri (XMSS khang luong tu) ---
    founder=XmssKey(h=6); ai_treasury=XmssKey(h=5); auth=founder
    human   =XmssKey(h=5)   # con nguoi (Alice)
    ai_agent=XmssKey(h=6)   # AI-agent dieu phoi (nhan viec, thue robot)
    robot_dlv=XmssKey(h=6)  # robot giao hang
    robot_chg=XmssKey(h=5)  # tram sac (cung la 1 robot/dich vu)
    A=lambda k:addr_of(k.root)
    names={A(founder):"Founder",A(ai_treasury):"AI-Treasury",A(human):"Human",
           A(ai_agent):"AI-Agent",A(robot_dlv):"Robot-Giao",A(robot_chg):"Tram-Sac"}
    print("\n[1] CAC TAC NHAN (moi cai 1 vi tu tri, chu ky hash-based):")
    for a,n in names.items(): print(f"    {n:<12} {a[:30]}..")

    node=NodePQ(auth.root)
    gen=Tx([],[TxOut(GEN_FOUNDER,A(founder),"genesis founder 11tr"),
               TxOut(GEN_AI,A(ai_treasury),"genesis AI 10tr")],coinbase=True)
    node.apply_block(mk_block(node,[gen],auth))
    print("\n[2] GENESIS premine 21tr (11tr founder + 10tr AI):")
    supply_guard(node,"genesis")

    # --- nap von ban dau cho cac may (tu founder/AI) ---
    print("\n[3] NAP VON cho nguoi va cac may:")
    pay(node, founder, "Founder", A(human),    "Human",    1000, "cap von nguoi dung", auth)
    pay(node, founder, "Founder", A(ai_agent), "AI-Agent", 500,  "von van hanh AI-agent", auth)
    pay(node, ai_treasury, "AI-Treasury", A(robot_dlv), "Robot-Giao", 300, "trien khai robot giao hang", auth)
    pay(node, ai_treasury, "AI-Treasury", A(robot_chg), "Tram-Sac",   200, "trien khai tram sac", auth)
    supply_guard(node,"nap von")

    # --- VONG KINH TE M2M: Nguoi -> AI -> Robot -> Tram sac ---
    print("\n[4] VONG KINH TE MAY-VOI-MAY (tu dong, moi buoc ky khang luong tu):")
    pay(node, human,     "Human",      A(ai_agent),  "AI-Agent",  50, "Nguoi thue AI: giao goi hang toi Q1", auth)
    pay(node, ai_agent,  "AI-Agent",   A(robot_dlv), "Robot-Giao",30, "AI thue robot giao hang (M2M)",       auth)
    pay(node, robot_dlv, "Robot-Giao", A(robot_chg), "Tram-Sac",  8,  "Robot tra tien sac pin (M2M)",        auth)
    pay(node, robot_chg, "Tram-Sac",   A(ai_treasury),"AI-Treasury",2,"Tram sac dong gop quy phat trien AI", auth)
    supply_guard(node,"vong M2M")

    print("\n[5] SO DU SAU VONG CHAY (tien chay qua chuoi may, 21tr bao toan):")
    for a,n in names.items(): print(f"    {n:<12}: {node.balance(a)/COIN:>14,.0f} BGC")
    print(f"    {'TONG':<12}: {node.audit_supply()/COIN:>14,.0f} BGC")

    print("\n[6] DOC YEU CAU ON-CHAIN (AI/robot quet chuoi de biet viec):")
    jobs=[(o.memo) for blk in node.chain for tx in blk.txs for o in tx.vout if "M2M" in o.memo or "thue" in o.memo.lower()]
    for j in jobs: print(f"    - {j}")

    print("\n[7] CHUNG MINH 21tr KHONG THE TANG (supply guard chan khoi vi pham):")
    # mo phong 1 khoi gian lan: coinbase tu tao coin -> check_tx + guard deu chan
    bad=Tx([],[TxOut(1*COIN, A(human),"in lau 1 BGC")],coinbase=True)
    ok,m=node.check_tx(bad)
    print(f"    coinbase tu in 1 BGC -> {'CHAN' if not ok else 'LOT'}: {m}")
    before=node.audit_supply()
    print(f"    tong cung KHONG doi: {before/COIN:,.0f} BGC (van 21tr). Khong co duong nao tang.")

    print("\n[8] NODE MOI tu xac minh lai + supply guard tung khoi:")
    fresh=NodePQ(auth.root); good=True
    for blk in node.chain:
        ok,m=fresh.apply_block(blk)
        if not ok or fresh.audit_supply()!=MAX_SUPPLY: good=False; print("   loi:",m); break
    print(f"    {len(node.chain)} khoi: {'HOP LE & LUON = 21tr' if good else 'LOI'}")

    print("\n"+"="*78); print(" KET LUAN & LUU Y CHO ANH")
    print("  - BGC phuc vu AI VA ROBOT: moi may la 1 vi tu tri, tu ky (khang luong tu), tu")
    print("    tra tien cho nhau (M2M). Vong: Nguoi -> AI -> Robot giao -> Tram sac -> quy AI.")
    print("  - 21,000,000 CO DINH: supply-guard kiem sau MOI khoi; khong duong nao in them.")
    print("  *** LUU Y QUAN TRONG (an ninh may tu tri) ***")
    print("  1. Chu ky one-time (XMSS) la STATEFUL: moi robot/AI PHAI luu chi so leaf 'next'")
    print("     xuong bo nho KHONG BAY (flash/disk). Robot reboot/crash ma QUEN -> ky lai cung")
    print("     leaf -> LO KHOA -> mat sach tien. Day la rui ro so 1 cho thiet bi tu tri.")
    print("     (Giai phap: luu 'next' nguyen tu truoc khi ky; hoac dung SPHINCS+ khong trang thai.)")
    print("  2. Khoa cua robot nam TREN robot -> robot bi chiem = tien bi chiem. Can vi cung/TEE.")
    print("  3. 21tr chi vung neu NGUOI DUNG tu chay node kiem (dung tin may phat).")
    print("  4. Premine + PoA: van phai tin founder (giu 11tr, ky khoi). Xem whitepaper muc 6.")
    print("  5. May tra tien tu dong -> dat HAN MUC/quy tac chi tieu, keo robot loi tieu sach quy.")
    print("="*78)
    return 0 if (good and node.audit_supply()==MAX_SUPPLY) else 1

if __name__=="__main__": sys.exit(main())
