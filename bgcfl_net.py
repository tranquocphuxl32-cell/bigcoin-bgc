#!/usr/bin/env python3
# =====================================================================
#  BGC-FL NET - mang FAIR LAUNCH nhieu THO DAO that, P2P MA HOA, PoW tu dao, hoi tu chainwork
#  Dung dung node that (run_miner.MinerNode) tren mang REGTEST, ket noi qua 127.0.0.1.
#  Chung minh: nhieu tho doc lap tu dao, gossip khoi qua kenh ma hoa, hoi tu 1 chuoi.
# =====================================================================
import os, sys, time, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_miner as R
from bgcfl_engine import REGTEST, MAIN, COIN
from bgcfl_wallet import Wallet

def wait(cond, t):
    end=time.time()+t
    while time.time()<end and not cond(): time.sleep(0.2)
    return cond()

def main():
    print("="*74); print(" BGC-FL NET - nhieu THO DAO that, P2P MA HOA, PoW tu dao, hoi tu chainwork"); print("="*74)
    tmp=tempfile.mkdtemp(prefix="bgcfl_net_")
    ms=[]
    for name in ("ThoA","ThoB","ThoC"):
        w=Wallet(os.path.join(tmp,name+".json"), h=6)
        ms.append(R.MinerNode(name, w, os.path.join(tmp,"d_"+name), 0, params=REGTEST, bind="127.0.0.1"))
    A,B,C=ms
    print(f"\n[1] 3 tho dao doc lap (vi rieng, khong xin phep). Cong: {[m.port for m in ms]}")
    for i,m in enumerate(ms):
        for o in ms[i+1:]: m.connect("127.0.0.1", o.port)   # moi cap 1 ket noi
    wait(lambda: all(len(m.peers)>=2 for m in ms), 8)
    print(f"[2] Noi luoi P2P ma hoa xong ({[len(m.peers) for m in ms]} peer). Bat dau TU DAO (PoW)...")
    for m in ms: m.start_mining()
    wait(lambda: max(m.chain.height() for m in ms)>=12, 30)
    for m in ms: m.stop_mining(wait=True)       # DUNG DAO nhung GIU mang de hoi tu
    conv=wait(lambda: len({m.chain.tip() for m in ms})==1, 5)
    # neu 2 tho cung tim duoc khoi cung luc (hoa), 1 khoi nua se phan dinh - nhu Bitcoin
    for _ in range(3):
        if conv: break
        A.start_mining(); h0=A.chain.height()
        wait(lambda: A.chain.height()>h0, 20); A.stop_mining(wait=True)
        conv=wait(lambda: len({m.chain.tip() for m in ms})==1, 10)
    print(f"\n[3] KET QUA sau khi dao:")
    for m in ms:
        print(f"    {m.name}: height={m.chain.height()} chainwork={m.chain.chainwork():.3e} "
              f"supply={m.chain.audit_supply()/COIN:,.1f} tip={m.chain.tip()[:12]}..")
    print(f"\n[4] PHAN BO (fair - moi coin deu DAO ra, KHONG premine):")
    for m in ms: print(f"    {m.name} dao duoc: {A.chain.balance(m.addr)/COIN:,.1f} BGC")
    sup=A.chain.audit_supply()
    print(f"    tong cung = {sup/COIN:,.1f} BGC (ra dan theo so khoi, <= 21tr: {sup<=MAIN.max_supply()})")
    print(f"\n[5] HOI TU: 3 tho cung 1 tip & height? {conv}")
    for m in ms: m.close()
    shutil.rmtree(tmp, ignore_errors=True)
    ok=conv and sup<=MAIN.max_supply() and A.chain.height()>=12
    print("\n"+"="*74)
    print(f" KET QUA: {'TAT CA PASS - mang fair-launch nhieu tho dao CHAY THAT' if ok else 'CO LOI'}")
    print("  - Nhieu tho doc lap TU dao (PoW), gossip khoi qua kenh MA HOA, hoi tu theo chainwork.")
    print("  - KHONG premine: moi coin do dao ra; khong ai xin phep ai (permissionless).")
    print("  - Lien may that: chay run_miner.py / bgc_app.py voi --peers IP:9333 va mo cong 9333.")
    print("="*74)
    return 0 if ok else 1

if __name__=="__main__": sys.exit(main())
