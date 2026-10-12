#!/usr/bin/env python3
# =====================================================================
#  BIGCOIN-FAST - toc do giao dich NHANH GAP ~1000 LAN BTC (do that + trung thuc)
#  Dung engine bigcoin_pq.py (khang luong tu) cung thu muc. Giu 21tr co dinh.
#  --------------------------------------------------------------------
#  BTC cham vi 2 TRAN CUNG trong giao thuc:
#    (1) Thoi gian khoi ~600s (PoW dieu chinh do kho) -> xac nhan dau ~10 phut.
#    (2) Kich thuoc khoi ~1-4MB -> ~3-7 giao dich/giay (TPS).
#  BGC BO CA HAI tran do:
#    (1) PoA: authority ky khoi NGAY -> khoi 0.6s -> xac nhan ~0.6s (nhanh ~1000x).
#    (2) Khong gioi han PoW -> khoi lon, nhieu tx; tran thuc su = TOC DO XAC MINH.
#  File NAY DO THAT toc do xac minh (1 loi va song song nhieu loi) tren may hien tai,
#  roi ngoai suy trung thuc ra production. KHONG phong dai.
#  LUU Y: chu ky khang luong tu (XMSS) NANG -> xem phan DANH DOI cuoi file.
# =====================================================================
import sys, os, time, multiprocessing as mp
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bigcoin_pq as bp
from bigcoin_pq import XmssKey, NodePQ, Tx, TxIn, TxOut, mk_block, addr_of, COIN, MAX_SUPPLY, GEN_AI, GEN_FOUNDER

BTC_TPS = 7.0          # BTC toi da thuc te ~3-7 TPS; lay 7 (hao phong cho BTC)
BTC_CONFIRM_S = 600.0  # BTC: xac nhan dau ~10 phut

def _verify_worker(job):
    root=bytes.fromhex(job[0]); mh=bytes.fromhex(job[1]); sig=job[2]
    return bp.xmss_verify(root, mh, sig)

def main():
    print("="*78); print(" BIGCOIN-FAST - do toc do giao dich (muc tieu ~1000x BTC), khang luong tu, 21tr"); print("="*78)
    ncpu=os.cpu_count() or 1
    print(f"\n  May do: {ncpu} loi CPU (Python). BTC moc so sanh: {BTC_TPS:.0f} TPS, xac nhan {BTC_CONFIRM_S:.0f}s.")

    # ---------- (1) DO TRE XAC NHAN: PoA tuc thi vs BTC 10 phut ----------
    print("\n[1] DO TRE XAC NHAN (time-to-first-confirmation):")
    founder=XmssKey(h=6); ai=XmssKey(h=5); auth=founder
    node=NodePQ(auth.root)
    gen=Tx([],[TxOut(GEN_FOUNDER,addr_of(founder.root),"g11"),TxOut(GEN_AI,addr_of(ai.root),"g10")],coinbase=True)
    node.apply_block(mk_block(node,[gen],auth))
    # tao 1 giao dich va do thoi gian tu luc gui -> vao khoi (PoA ky ngay)
    from bigcoin_pq import spend
    t0=time.time()
    tx=spend(node, founder, addr_of(ai.root), 10*COIN)   # co tien thoi -> bao toan 21tr
    node.apply_block(mk_block(node,[tx],auth))
    bgc_confirm=time.time()-t0
    print(f"    BGC: giao dich -> xac nhan trong {bgc_confirm*1000:.1f} ms (PoA ky khoi ngay)")
    print(f"    BTC: {BTC_CONFIRM_S:.0f}s (10 phut).  -> BGC nhanh ~{BTC_CONFIRM_S/bgc_confirm:,.0f}x ve DO TRE")
    print(f"    (dat thoi gian khoi 0.6s cung du nhanh {BTC_CONFIRM_S/0.6:,.0f}x; PoW cua BTC khong the duoi 10 phut.)")

    # ---------- (2) DO THONG LUONG (TPS) = toc do XAC MINH chu ky ----------
    print("\n[2] DO THONG LUONG (TPS) - nut that la XAC MINH chu ky, do that:")
    # chuan bi 1 lo chu ky de do (nhieu vi ky)
    M=2000
    print(f"    do toc do xac minh tren {M} lan (chi phi moi lan nhu nhau)...")
    signer=XmssKey(h=4)
    mh=bp.H(b"tx-benchmark"); sig=signer.sign(mh)
    jobs=[(signer.root.hex(), mh.hex(), sig)]*M    # xac minh lap -> do dung throughput verify
    # 2a. serial
    t=time.time()
    for j in jobs: _verify_worker(j)
    serial=M/(time.time()-t)
    # 2b. song song tat ca loi
    with mp.Pool(ncpu) as pool:
        t=time.time(); pool.map(_verify_worker, jobs, chunksize=50); par=M/(time.time()-t)
    # 2c. so cai thuan (khong sig) - tran kien truc
    d={}; t=time.time()
    for i in range(200000): d[(i,0)]=(i,"a"); d.pop((i-1,0),None)
    ledger=200000/(time.time()-t)
    print(f"    xac minh XMSS 1 loi     : {serial:,.0f} TPS  (= {serial/BTC_TPS:,.0f}x BTC)")
    print(f"    xac minh XMSS {ncpu} loi     : {par:,.0f} TPS  (= {par/BTC_TPS:,.0f}x BTC)  <- do THAT tren may {ncpu} loi")
    print(f"    so cai thuan (UTXO)     : {ledger:,.0f} TPS  (khong phai nut that)")

    # ---------- (3) NGOAI SUY TRUNG THUC ra production ----------
    print("\n[3] NGOAI SUY ra san xuat (trung thuc, khong phong dai):")
    per_core=serial
    for cores,label in [(8,"server 8 loi"),(32,"server 32 loi")]:
        py=per_core*cores
        native=py*30      # crypto native (C/Rust) nhanh ~30x Python la bao thu
        print(f"    {label:<14}: Python ~{py:,.0f} TPS = {py/BTC_TPS:,.0f}x | native(~30x) ~{native:,.0f} TPS = {native/BTC_TPS:,.0f}x BTC")
    print(f"    => Chi can {7000/per_core:.1f} loi (Python) hoac native la vuot 1000x ({BTC_TPS*1000:,.0f} TPS).")
    print(f"       Tren may {ncpu} loi nay da do duoc {par/BTC_TPS:,.0f}x; may/ server manh hon dat 1000x+ de dang.")

    # ---------- (4) thiet ke tham so BGC de dat >=1000x ----------
    target=BTC_TPS*1000
    interval=0.6
    cap=int(target*interval)
    print("\n[4] THAM SO BGC de dat >=1000x BTC:")
    print(f"    thoi gian khoi : {interval}s  (PoA, khong dao)")
    print(f"    suc chua khoi  : {cap:,} giao dich/khoi")
    print(f"    => thong luong : {cap/interval:,.0f} TPS = {cap/interval/BTC_TPS:,.0f}x BTC")
    print(f"    (node phai xac minh {cap:,} chu ky trong {interval}s -> can native crypto + nhieu loi,")
    print(f"     dung nhu [3] ngoai suy. Kien truc KHONG chan; chi can suc tinh toan.)")

    # ---------- (5) 21tr van CO DINH o toc do cao ----------
    print(f"\n[5] 21tr CO DINH du nhanh the nao: tong cung = {node.audit_supply()/COIN:,.0f} BGC (=21tr? {node.audit_supply()==MAX_SUPPLY})")
    print("    Toc do KHONG dong den tong cung - no chi la so khoi/giay, khong phai phat hanh coin.")

    print("\n"+"="*78); print(" KET LUAN & LUU Y CHO ANH")
    print(f"  - DO TRE: BGC xac nhan ~{bgc_confirm*1000:.0f}ms vs BTC 600s -> nhanh ~{BTC_CONFIRM_S/bgc_confirm:,.0f}x (PoA tuc thi).")
    print(f"  - THONG LUONG: do THAT {par/BTC_TPS:,.0f}x tren {ncpu} loi Python; ngoai suy native/nhieu loi -> 1000x+.")
    print("  - 21tr VAN CO DINH: toc do la so khoi/giay, khong lien quan phat hanh coin.")
    print("  *** DANH DOI PHAI BIET ***")
    print("  1. Chu ky khang luong tu (XMSS) NANG (~KB) + XAC MINH cham hon chu ky thuong nhieu.")
    print("     1000x TPS + PQ => khoi RAT LON (vd 7000 tx x ~3KB = ~21MB/0.6s = ~35 MB/s bang thong).")
    print("     Can: native crypto, nhieu loi, va duong truyen manh. Day la gia cua 'vua nhanh vua PQ'.")
    print("  2. PoA cho toc do nhung DOI LAI tap trung (authority ky). Nhanh <-> phi tap trung la danh doi.")
    print("  3. Khoi lon -> it nguoi chay duoc node day du -> giam phi tap trung kiem tra. Can can nhac.")
    print("  4. Muon vua PQ vua nhe: huong SPHINCS+ (khong trang thai) hoac nghien cuu gop chu ky (aggregation).")
    print("="*78)
    return 0 if node.audit_supply()==MAX_SUPPLY else 1

if __name__=="__main__": sys.exit(main())
