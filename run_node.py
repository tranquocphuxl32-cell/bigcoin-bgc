#!/usr/bin/env python3
# =====================================================================
#  RUN_NODE - chay 1 node BGC that tu file cau hinh (de chay LIEN MAY).
#  Dung: python run_node.py <cau_hinh.json>
#  - Nap genesis.json (chung cho moi may) -> dong bo tu do.
#  - Tu noi peers (reconnect dinh ky neu peer chua len).
#  - Neu la authority: tu dao luan phien (timeout liveness).
#  - In trang thai dinh ky + sinh explorer.html; nhan lenh: bal | send <dc> <so> [memo] | peers | quit
# =====================================================================
import os, sys, json, time, threading, functools
print=functools.partial(print, flush=True)   # in ngay, khong buffer (de theo doi lien may)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bgc_node import Node
from bgc_wallet import Wallet
from bgc_engine import Block, COIN, MAX_SUPPLY
import bgc_explorer

def main():
    if len(sys.argv)<2: print("Dung: python run_node.py <cau_hinh.json>"); return 1
    cfgpath=sys.argv[1]; cfgdir=os.path.dirname(os.path.abspath(cfgpath))
    cfg=json.load(open(cfgpath))
    def rel(p): return p if os.path.isabs(p) else os.path.join(cfgdir,p)

    authw = Wallet(rel(cfg["wallet"])) if cfg.get("is_authority") and cfg.get("wallet") else None
    node=Node(cfg["name"], cfg["authorities"], rel(cfg["datadir"]),
              port=cfg.get("listen_port",0), authority_wallet=authw)
    print(f"[{cfg['name']}] lang nghe cong {node.p2p.port} | authority={bool(authw)} | {len(cfg['authorities'])} authority")

    # nap genesis chuan neu chuoi dang rong
    if node.chain.height()==0:
        gb=Block.from_d(json.load(open(rel(cfg["genesis"]))))
        ok,m,_=node.chain.add_block(gb)
        print(f"[{cfg['name']}] nap genesis.json: {'OK' if ok else 'LOI '+m} | supply={node.chain.audit_supply()/COIN:,.0f}")

    peers=[p for p in cfg.get("peers",[]) if "<" not in p]   # bo placeholder chua sua
    def reconnector():
        while True:
            for p in peers:
                try: host,port=p.rsplit(":",1); node.connect_peer(host,int(port))
                except Exception: pass
            time.sleep(5)
    threading.Thread(target=reconnector,daemon=True).start()
    time.sleep(1.0)
    if authw: node.start_mining(block_time=cfg.get("block_time",0.5))

    # trang thai dinh ky + explorer
    def monitor():
        while True:
            time.sleep(3)
            try:
                bgc_explorer.render(node.chain, rel("explorer.html"))
                ok = node.chain.audit_supply()==MAX_SUPPLY
                print(f"[{cfg['name']}] height={node.chain.height()} peers={len(node.p2p.peers)} "
                      f"supply={node.chain.audit_supply()/COIN:,.0f} {'OK' if ok else 'SUPPLY-LOI'} tip={node.chain.tip()[:12]}..")
            except Exception as e: print("monitor loi:",e)
    threading.Thread(target=monitor,daemon=True).start()

    print(f"[{cfg['name']}] San sang. Lenh: bal | send <dia_chi> <so_BGC> [memo] | peers | quit")
    try:
        for line in sys.stdin:
            parts=line.strip().split()
            if not parts: continue
            c=parts[0]
            if c=="quit": break
            elif c=="bal":
                if authw: print(f"  so du {node.name}: {node.chain.balance(authw.address)/COIN:,.4f} BGC "
                                 f"(mo khoa: {node.chain.balance(authw.address,True)/COIN:,.4f})")
                else: print("  node quan sat khong co vi")
            elif c=="peers": print(f"  {len(node.p2p.peers)} peer | height {node.chain.height()}")
            elif c=="send" and authw and len(parts)>=3:
                to=parts[1]; amt=float(parts[2]); memo=" ".join(parts[3:])
                try:
                    tx=authw.send(node.chain, to, amt, memo=memo); ok,m=node.submit_tx(tx)
                    print(f"  gui {amt} BGC -> {to[:16]}.. : {'da phat len mang' if ok else m}")
                except Exception as e: print("  loi gui:",e)
            else: print("  lenh: bal | send <dia_chi> <so_BGC> [memo] | peers | quit")
    except KeyboardInterrupt: pass
    node.close(); print(f"[{cfg['name']}] da dung.")
    return 0

if __name__=="__main__": sys.exit(main())
