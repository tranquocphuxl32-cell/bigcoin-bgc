#!/usr/bin/env python3
# =====================================================================
#  BGC INIT - tao MOT LAN: vi authority + vi AI + GENESIS CHUAN + cau hinh tung may.
#  Chay 1 lan de "khai sinh" mang BGC, roi copy file toi tung may chay run_node.py.
#  Moi may PHAI dung CUNG genesis.json va CUNG danh sach authorities -> moi hoi tu.
#  Dung: python bgc_init.py <so_authority> [so_may]
# =====================================================================
import os, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bgc_wallet import Wallet
from bgc_engine import Chain, Block, Tx, TxOut, GEN_FOUNDER, GEN_AI, MAX_SUPPLY, COIN

OUT="bgc_net"   # thu muc chua toan bo file khoi tao

def main():
    n_auth=int(sys.argv[1]) if len(sys.argv)>1 else 3
    os.makedirs(OUT, exist_ok=True)
    print("="*72); print(f" BGC INIT - khai sinh mang voi {n_auth} authority"); print("="*72)

    # 1. tao vi authority + vi AI
    auth_wallets=[Wallet(f"{OUT}/auth{i}.wallet", h=12) for i in range(n_auth)]
    ai=Wallet(f"{OUT}/ai.wallet", h=12)
    founder=auth_wallets[0]            # authority 0 giu 11tr (founder) + ky genesis
    AUTHS=sorted(w.key.root.hex() for w in auth_wallets)
    print(f"\n[1] Tao {n_auth} vi authority + 1 vi AI (khang luong tu).")
    print(f"    Founder (auth giu 11tr) = {founder.address[:28]}..")
    print(f"    AI treasury             = {ai.address[:28]}..")

    # 2. GENESIS CHUAN: 11tr founder (KHOA vesting), 10tr AI. Ky boi authority[0] cua rotation.
    UNLOCK=0   # anh doi thanh chieu cao mo khoa that (vd ~ vai nam) truoc khi phat hanh that
    chain=Chain(AUTHS)
    signer_root=chain.expected_auth(0)                      # authority dung luot o khoi 0
    signer=next(w for w in auth_wallets if w.key.root.hex()==signer_root)
    g=Tx([],[TxOut(GEN_FOUNDER, founder.address, "BGC genesis: founder 11tr (KHOA vesting)", UNLOCK),
             TxOut(GEN_AI, ai.address, "BGC genesis: AI treasury 10tr")], coinbase=True)
    gb=Block(0, "0"*64, [g], signer.key.root.hex(), ts=1_700_000_000)   # ts co dinh -> genesis TAT DINH
    gb.sig=signer.sign(gb.sighash())
    ok,m,_=chain.add_block(gb)
    assert ok and chain.audit_supply()==MAX_SUPPLY, m
    json.dump(gb.to_d(), open(f"{OUT}/genesis.json","w"))
    print(f"\n[2] GENESIS CHUAN da tao & ky (sum = {chain.audit_supply()/COIN:,.0f} BGC).")
    print(f"    luu: {OUT}/genesis.json  (MOI may dung chung file nay)")

    # 3. cau hinh moi may (authority node). peers de placeholder de anh dien IP that.
    base_port=9333
    for i,w in enumerate(auth_wallets):
        cfg={
            "name": f"auth{i}",
            "listen_port": base_port,
            "wallet": f"auth{i}.wallet",
            "is_authority": True,
            "authorities": AUTHS,
            "genesis": "genesis.json",
            "peers": [f"<IP_may_khac>:{base_port}" for j in range(n_auth) if j!=i],
            "datadir": f"data_auth{i}",
            "block_time": 0.5
        }
        json.dump(cfg, open(f"{OUT}/node_auth{i}.json","w"), indent=2)
    # them 1 cau hinh node QUAN SAT (khong ky) lam vi du
    json.dump({"name":"observer","listen_port":base_port,"wallet":None,"is_authority":False,
               "authorities":AUTHS,"genesis":"genesis.json","peers":[f"<IP_authority>:{base_port}"],
               "datadir":"data_observer","block_time":0.5}, open(f"{OUT}/node_observer.json","w"), indent=2)
    print(f"\n[3] Da tao cau hinh: node_auth0.json .. node_auth{n_auth-1}.json + node_observer.json")

    print("\n"+"="*72); print(" HUONG DAN CHAY LIEN MAY")
    print(f"  1. Copy CA thu muc '{OUT}/' + cac file bgc_*.py, bigcoin_pq.py, btclib.py sang moi may.")
    print( "  2. Tren moi may, sua 'peers' trong node_authX.json: thay <IP_may_khac> bang IP LAN/WAN that.")
    print( "     (Moi may giu vi auth cua minh; KHONG chia se file auth*.wallet cho may khac.)")
    print( "  3. Chay:  python run_node.py bgc_net/node_auth0.json   (may 0)")
    print(f"            python run_node.py bgc_net/node_auth1.json   (may 1) ...")
    print( "  4. Cac node tu noi, dong bo tu genesis.json, va authority tu dao luan phien.")
    print( "  LUU Y: mo cong firewall cho listen_port; dung IP LAN de thu trong nha truoc.")
    print( "  LUU Y: genesis.json + authorities phai GIONG HET tren moi may, neu khong se khong hoi tu.")
    print("="*72)

if __name__=="__main__": main()
