#!/usr/bin/env python3
# =====================================================================
#  BGC - TRAO DOI QUA MANG THAT giua 2 NODE (An  <->  Binh)
#  Khac file bgc_trao_doi.py (mo phong 1 chuoi): day la HAI NODE RIENG, noi
#  nhau qua KENH P2P MA HOA (ECDH + ChaCha20-Poly1305). Giao dich cua An
#  LAN qua mang toi Binh, duoc dao vao khoi, va CA HAI NODE cung thay ket qua.
#  Giong het khi 2 nguoi o 2 may khac nhau trao doi BGC (mang REGTEST, demo nhanh).
#  Chay:  python bgc_trao_doi_mang.py
# =====================================================================
import os, sys, time, shutil, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_miner as R
from bgcfl_wallet import Wallet
from bgcfl_engine import COIN, REGTEST, MAIN

P=REGTEST
LINE="="*74
def hdr(x): print("\n"+x)

def wait(cond, t=15):
    t0=time.time()
    while time.time()-t0<t and not cond(): time.sleep(0.2)
    return cond()

def confirmed(chain, tx, vout, value):
    return chain.utxo.get((tx.txid(),vout),(0,))[0]==value

def main():
    print(LINE); print(" BGC - TRAO DOI QUA MANG THAT: node An  <->  node Binh (P2P ma hoa)"); print(LINE)
    tmp=tempfile.mkdtemp(prefix="bgc_mang_")

    def node(name):
        w=Wallet(os.path.join(tmp,name+".json"), h=6)
        n=R.MinerNode(name, w, os.path.join(tmp,"d_"+name), 0, params=P, bind="127.0.0.1")
        return n,w
    An, wa = node("An")
    Binh, wb = node("Binh")
    hdr(f"[1] Hai NODE doc lap (nhu 2 may rieng), moi node 1 vi khang luong tu:")
    print(f"    An  : cong {An.port}  vi {wa.address[:34]}..")
    print(f"    Binh: cong {Binh.port}  vi {wb.address[:34]}..")

    # Binh ket noi toi An qua kenh MA HOA
    Binh.connect("127.0.0.1", An.port)
    ok=wait(lambda: len(An.peers)>=1 and len(Binh.peers)>=1, 8)
    print(f"\n[2] Noi mang P2P MA HOA giua 2 node: {'XONG' if ok else 'chua noi duoc'} "
          f"(An {len(An.peers)} peer, Binh {len(Binh.peers)} peer)")

    # An dao de co BGC; ca 2 node se dong bo chieu cao
    hdr(f"[3] An bat dau DAO (PoW). Khoi lan qua mang toi Binh (du Binh khong dao)...")
    An.start_mining()
    wait(lambda: An.chain.height()>=P.maturity+4, 30)
    An.stop_mining(wait=True)
    wait(lambda: Binh.chain.tip()==An.chain.tip(), 10)
    print(f"    An  : cao {An.chain.height()}  so du An = {wa.balance(An.chain):,.0f} BGC")
    print(f"    Binh: cao {Binh.chain.height()}  (dong bo tu An qua mang ma hoa)")
    print(f"    => Hai node cung chieu cao? {An.chain.height()==Binh.chain.height()}")

    # ---- TRAO DOI: An gui 100 BGC cho Binh ----
    hdr(f"[4] An GUI 100 BGC cho Binh (giao dich lan qua mang -> mempool cua Binh):")
    tx=wa.send(An.chain, wb.address, "100", memo="An tra Binh qua mang")
    okm,msg=An.submit_tx(tx)                 # phat len mang (ma hoa)
    print(f"    An ky (khang luong tu) + phat len mang. An nhan vao mempool? {okm} ({msg})")
    got=wait(lambda: tx.txid() in Binh.chain.mempool, 8)
    print(f"    Binh NHAN duoc giao dich qua kenh ma hoa (vao mempool)? {got}")

    hdr(f"[5] Co tho dao dua giao dich vao khoi -> XAC NHAN (ca 2 node cung thay):")
    An.start_mining()
    conf=wait(lambda: confirmed(An.chain,tx,0,100*COIN) and confirmed(Binh.chain,tx,0,100*COIN), 30)
    An.stop_mining(wait=True)
    print(f"    Sau xac nhan:")
    print(f"      tren node An  : An={wa.balance(An.chain):,.0f}  Binh={wb.balance(An.chain):,.0f} BGC")
    print(f"      tren node Binh: An={wa.balance(Binh.chain):,.0f}  Binh={wb.balance(Binh.chain):,.0f} BGC")
    print(f"    => Binh da nhan 100 BGC, CA HAI node deu thay giong nhau? {conf}")

    # ---- CHIEU NGUOC LAI: Binh gui tra An 40 BGC ----
    hdr(f"[6] CHIEU NGUOC LAI - Binh GUI tra An 40 BGC (Binh dao de tu xac nhan):")
    tx2=wb.send(Binh.chain, wa.address, "40", memo="Binh tra An")
    ok2,msg2=Binh.submit_tx(tx2)
    print(f"    Binh ky + phat len mang: {ok2} ({msg2})")
    Binh.start_mining()
    back=wait(lambda: confirmed(An.chain,tx2,0,40*COIN) and confirmed(Binh.chain,tx2,0,40*COIN), 30)
    Binh.stop_mining(wait=True)
    same=wait(lambda: An.chain.tip()==Binh.chain.tip(), 15)
    print(f"      tren node An  : An={wa.balance(An.chain):,.0f}  Binh={wb.balance(An.chain):,.0f} BGC")
    print(f"      tren node Binh: An={wa.balance(Binh.chain):,.0f}  Binh={wb.balance(Binh.chain):,.0f} BGC")

    print("\n"+LINE); print(" KET QUA")
    print(LINE)
    print(f"  - Hai node noi nhau qua kenh MA HOA; khoi va giao dich tu lan khap mang (gossip).")
    print(f"  - An -> Binh roi Binh -> An: so du cap nhat GIONG NHAU tren ca 2 node? {conf and back}")
    print(f"  - Hai node cuoi cung cung 1 tip & chieu cao (dong thuan)? {same}")
    print(f"  - Tong cung <= 21tr nguyen ven? {An.chain.audit_supply()<=MAIN.max_supply()}")
    print(f"  - That te: doi 127.0.0.1 thanh IP may that + mo cong la 2 NGUOI o 2 MAY trao doi duoc.")
    print(LINE)
    An.close(); Binh.close()
    shutil.rmtree(tmp, ignore_errors=True)
    good = conf and back and same and An.chain.audit_supply()<=MAIN.max_supply()
    print(f"\n  Kiem thu tong the: {'PASS' if good else 'CHECK'}")
    return 0 if good else 1

if __name__=="__main__": sys.exit(main())
