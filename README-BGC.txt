======================================================================
   BIGCOIN (BGC) - HE HOAN CHINH (bo file doc lap trong thu muc nay)
   Tac gia: Phu  |  D:\BitcoinCore\Bigcoin-BGC\
======================================================================

DAY LA GI: mot dong tien day du, gop tat ca tinh nang da xay:
  - Khang luong tu (chu ky hash-based XMSS/WOTS+, chi SHA-256)
  - Tong cung 21,000,000 CO DINH (supply-guard kiem sau MOI khoi)
  - Timelock: 11tr founder KHOA on-chain (vesting) - cong dong verify duoc
  - Memo on-chain: kinh te AI <-> nguoi <-> robot (M2M)
  - PoA: authority ky khoi, xac nhan gan tuc thi (nhanh)
  - LUU DIA: chuoi ghi ra file; nap lai = tu xac minh lai tu genesis
  - MANG P2P: nhieu node noi nhau (TCP), dong bo khoi + lan truyen giao dich
  - VI: khang luong tu, LUU chi so leaf ra dia (chong lo khoa khi reboot)
  - EXPLORER: xuat trang HTML cho cong dong "thay" chuoi + bang chung 21tr

CAC FILE (chay tren Python 3, Windows/Linux):
  bigcoin_pq.py   - thu vien crypto khang luong tu (XMSS/WOTS+), nen tang
  bgc_engine.py   - model + luat dong thuan (21tr, timelock, PoA) + luu dia
  bgc_wallet.py   - vi khang luong tu, luu leaf index ra dia
  bgc_p2p.py      - mang ngang hang (TCP), dong bo + relay
  bgc_node.py     - 1 node hoan chinh (engine + P2P + dao PoA)
  bgc_explorer.py - xuat trang HTML explorer
  bgc_demo.py     - CHAY THU: 2 node noi nhau, giao dich, luu dia, explorer

CACH CHAY DEMO:
  cd D:\BitcoinCore\Bigcoin-BGC
  python bgc_demo.py
  -> chay 2 node that, dong bo P2P, in [10] kiem chung TAT CA PASS,
     va sinh file bgc_explorer.html (mo bang trinh duyet de xem chuoi).

KET QUA DEMO (da chay): 2 node A&B dong bo qua P2P; 21tr co dinh o ca 2;
  11tr founder khoa som -> CHAN, sau mo khoa -> tieu duoc; nap lai tu dia = 21tr.

*** LUU Y QUAN TRONG ***
  1. Day la PROTOTYPE hoc tap/trinh dien: P2P don gian (JSON/TCP, chua ma hoa,
     chua chong DoS manh, chua fork-choice phuc tap). TRUOC khi dung that can:
     ma hoa P2P (BIP324), gioi han ban tin, xu ly reorg, kiem thu ky luong.
  2. Chu ky one-time STATEFUL: vi da luu 'next' ra dia; tuyet doi khong copy file
     vi roi ky song song 2 noi (se lo khoa). Robot/AI cang phai ky luat cho nay.
  3. PoA = tap trung (authority duy nhat ky khoi). Lo trinh: nhieu authority luan phien.
  4. Phap ly: neu phat hanh/ban ra cong chung -> tu van phap ly truoc (xem WHITEPAPER muc 7).
  5. 21tr co dinh la bat bien trong code; genesis dat 11tr/10tr + lock -> chon ky, khong sua duoc.
======================================================================
==========================================================================
 BGC - HE HOAN CHINH: 2 node P2P + PQ + 21tr + timelock + memo + luu dia
==========================================================================

[1] Vi tao xong (khang luong tu, luu leaf ra dia). Authority = Founder.
    Founder BGCQ43a0d58c52d69d0333.. | AI BGCQ51959599ad4f223ba8.. | Alice BGCQ5607f706f871623ba6..

[2] Node A (authority) cong 39007 | Node B cong 41755

[3] GENESIS tren A (21tr): A height=1 supply=21,000,000
    -> P2P dong bo sang B: B height=1 supply=21,000,000  (=21tr? True)

[4] AI -> Alice 100 BGC (truyen P2P, A dao):
    A: Alice=100 | B: Alice=100  (2 node KHOP)

[5] Alice -> AI 5 BGC + yeu cau on-chain. AI treasury=9,999,905

[6] Founder thu tieu 11tr KHOA som (height 3 < 8):
    -> CHAN ngay khi tao tx: khong du BGC da mo khoa

[7] Dao toi khoi 8 -> 11tr mo khoa. Founder tieu duoc=11,000,000
    B dong bo: height=8 supply=21,000,000

[8] LUU DIA + NAP LAI (node moi doc file, tu xac minh lai tu genesis):
    nap 8 khoi tu dia; supply tu tinh lai = 21,000,000 (=21tr? True)

[9] EXPLORER xuat: /mnt/user-data/outputs/bgc_explorer.html

[10] KIEM CHUNG CUOI:
    [OK] A supply=21tr
    [OK] B supply=21tr
    [OK] A==B height
    [OK] A==B tip
    [OK] nap lai dia=21tr
    [OK] Alice khop 2 node

==========================================================================
 KET QUA: TAT CA PASS - he BGC hop nhat CHAY THAT
  Node A & B dong bo qua P2P; 21tr co dinh (supply-guard moi khoi); 11tr khoa on-chain;
  chu ky khang luong tu; luu dia + nap lai tu kiem; explorer HTML cho cong dong.
==========================================================================
