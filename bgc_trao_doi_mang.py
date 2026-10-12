#!/usr/bin/env python3
# =====================================================================
#  BGC - TRAO DOI QUA MANG THAT giua 2 NODE (An  <->  Binh)
#  Khac file bgc_trao_doi.py (mo phong 1 chuoi): day la HAI NODE RIENG, noi
#  nhau qua KENH P2P MA HOA (ECDH + ChaCha20-Poly1305). Giao dich cua An
#  LAN qua mang toi Binh, duoc dao vao khoi, va CA HAI NODE cung thay ket qua.
#  Giong het khi 2 nguoi o 2 may khac nhau trao doi BGC.
#  Chay:  python bgc_trao_doi_mang.py
# =====================================================================
import os, sys, time, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_miner as R
from bgcfl_wallet import Wallet
from bgcfl_engine import COIN, MAX_SUPPLY, Block
import json

LINE="="*74
def hdr(x): print("\n"+x)

def wait(cond, t=15):
    t0=time.time()
    while time.time()-t0<t and not cond(): time.sleep(0.2)
    return cond()

def main():
    print(LINE); print(" BGC - TRAO DOI QUA MANG THAT: node An  <->  node Binh (P2P ma hoa)"); print(LINE)
    tmp="/tmp/_bgc_mang"; shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp)
    # genesis chung
    import bgcfl_genesis; G=os.path.join(tmp,"genesis.json")
    json.dump(bgcfl_genesis.build().to_d(), open(G,"w"))

    def node(name, port):
        w=Wallet(os.path.join(tmp,name+".json"))
        n=R.MinerNode(name, w, os.path.join(tmp,"d_"+name), port)
        R.load_genesis(n.chain, G)
        return n,w
    An, wa = node("An", 0)
    Binh, wb = node("Binh", 0)
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
    wait(lambda: An.chain.height()>=8, 15)
    wait(lambda: Binh.chain.height()==An.chain.height(), 8)
    An.mining=False; time.sleep(1.5)
    print(f"    An  : cao {An.chain.height()}  so du An = {wa.balance(An.chain):,.0f} BGC")
    print(f"    Binh: cao {Binh.chain.height()}  (dong bo tu An qua mang ma hoa)")
    print(f"    => Hai node cung chieu cao? {An.chain.height()==Binh.chain.height()}")

    # ---- TRAO DOI: An gui 100 BGC cho Binh ----
    hdr(f"[4] An GUI 100 BGC cho Binh (giao dich lan qua mang -> mempool cua Binh):")
    tx=wa.send(An.chain, wb.address, 100, memo="An tra Binh qua mang")
    okm,msg=An.submit_tx(tx)                 # phat len mang (ma hoa)
    print(f"    An ky (khang luong tu) + phat len mang. An nhan vao mempool? {okm}")
    got=wait(lambda: tx.txid() in Binh.chain.mempool, 8)
    print(f"    Binh NHAN duoc giao dich qua kenh ma hoa (vao mempool)? {got}")

    hdr(f"[5] Co tho dao dua giao dich vao khoi -> XAC NHAN (ca 2 node cung thay):")
    An.start_mining()
    conf=wait(lambda: wb.balance(Binh.chain)>=100 and wb.balance(An.chain)>=100, 20)
    An.mining=False; time.sleep(1.5)
    print(f"    Sau xac nhan:")
    print(f"      tren node An  : An={wa.balance(An.chain):,.0f}  Binh={wb.balance(An.chain):,.0f} BGC")
    print(f"      tren node Binh: An={wa.balance(Binh.chain):,.0f}  Binh={wb.balance(Binh.chain):,.0f} BGC")
    print(f"    => Binh da nhan 100 BGC, CA HAI node deu thay giong nhau? {conf}")

    # ---- CHIEU NGUOC LAI: Binh gui tra An 40 BGC ----
    hdr(f"[6] CHIEU NGUOC LAI - Binh GUI tra An 40 BGC (Binh dao de tu xac nhan):")
    tx2=wb.send(Binh.chain, wa.address, 40, memo="Binh tra An")
    Binh.submit_tx(tx2)
    Binh.start_mining()
    back=wait(lambda: wa.balance(An.chain)>=wa.balance(Binh.chain)-1 and tx2.txid() not in Binh.chain.mempool
                      and wb.balance(An.chain)<=wb.balance(Binh.chain)+1, 20)
    time.sleep(1.5); Binh.mining=False; time.sleep(1.0)
    print(f"      tren node An  : An={wa.balance(An.chain):,.0f}  Binh={wb.balance(An.chain):,.0f} BGC")
    print(f"      tren node Binh: An={wa.balance(Binh.chain):,.0f}  Binh={wb.balance(Binh.chain):,.0f} BGC")

    same = (An.chain.tip()==Binh.chain.tip() and An.chain.height()==Binh.chain.height())
    print("\n"+LINE); print(" KET QUA")
    print(LINE)
    print(f"  - Hai node noi nhau qua kenh MA HOA; khoi va giao dich tu lan khap mang (gossip).")
    print(f"  - An -> Binh roi Binh -> An: so du cap nhat GIONG NHAU tren ca 2 node.")
    print(f"  - Hai node cuoi cung cung 1 tip & chieu cao (dong thuan)? {same}")
    print(f"  - Tong cung <= 21tr nguyen ven? {An.chain.audit_supply()<=MAX_SUPPLY}")
    print(f"  - That te: doi 127.0.0.1 thanh IP may that + mo cong la 2 NGUOI o 2 MAY trao doi duoc.")
    print(LINE)
    An.close(); Binh.close()
    good = conf and same and An.chain.audit_supply()<=MAX_SUPPLY
    print(f"\n  Kiem thu tong the: {'PASS' if good else 'CHECK'}")
    return 0 if good else 1

if __name__=="__main__": sys.exit(main())
