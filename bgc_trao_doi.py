#!/usr/bin/env python3
# =====================================================================
#  BGC - TRAO DOI GIUA 2 NGUOI NAM GIU (An  <->  Binh), khang luong tu
#  Minh hoa day du mot giao dich BGC nhu that:
#    1) Moi nguoi 1 vi KHANG LUONG TU (XMSS): dia chi de NHAN, khoa rieng de KY.
#    2) An co BGC (do dao ra) -> GUI cho Binh: ky -> mempool -> THO DAO vao khoi.
#    3) Kiem tra so du truoc/sau + tien thoi (change).
#    4) Thu GIAN LAN: chu ky gia, tieu 2 lan, tao tien tu khong khi -> deu BI CHAN.
#    5) Chieu nguoc lai: Binh gui tra An.
#  Chay:  python bgc_trao_doi.py
# =====================================================================
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bgcfl_engine import Chain, Block, Tx, TxIn, TxOut, mine, subsidy, COIN, MAX_SUPPLY, MATURITY, addr_of
from bgcfl_wallet import Wallet
from bigcoin_pq import XmssKey, xmss_verify

LINE="="*74

def mine_to(chain, addr, n, clock):
    for _ in range(n):
        h=chain.height()
        cb=Tx([],[TxOut(subsidy(h), addr, f"cb h{h}")],coinbase=True)
        chain.add_block(mine(Block(h, chain.tip(), [cb], ts=clock, target=chain.next_target())))
        clock+=10
    return clock

def mine_block_with(chain, addr, txs, clock):
    h=chain.height()
    fees=sum(sum(chain.utxo.get((i.txid,i.vout),(0,"",-1))[0] for i in t.vin)-sum(o.value for o in t.vout) for t in txs)
    cb=Tx([],[TxOut(subsidy(h)+max(0,fees), addr, f"cb h{h}")],coinbase=True)
    blk=mine(Block(h, chain.tip(), [cb]+txs, ts=clock, target=chain.next_target()))
    ok,msg,_=chain.add_block(blk); return ok,msg,blk,clock+10

def bal(chain,w): return chain.balance(w.address)/COIN

def main():
    print(LINE); print(" BGC - TRAO DOI GIUA 2 NGUOI:  An  <->  Binh  (khang luong tu)"); print(LINE)

    tmp="/tmp/_bgc_trao_doi"; os.makedirs(tmp, exist_ok=True)
    for f in ("an.json","binh.json","tho.json"):
        p=os.path.join(tmp,f); os.path.exists(p) and os.remove(p)
    An=Wallet(os.path.join(tmp,"an.json")); Binh=Wallet(os.path.join(tmp,"binh.json")); Tho=Wallet(os.path.join(tmp,"tho.json"))
    print("\n[1] HAI NGUOI NAM GIU BGC (moi nguoi 1 vi rieng, chu ky HASH-BASED khang luong tu):")
    print(f"    An   (gui) : {An.address[:42]}..")
    print(f"    Binh (nhan): {Binh.address[:42]}..")
    print(f"    Tho dao    : {Tho.address[:30]}.. (nguoi xac nhan giao dich, khong phai ben trao doi)")

    chain=Chain(); clock=1000
    clock=mine_to(chain, An.address, 3, clock)                 # An dao 3 khoi = 150 BGC
    clock=mine_to(chain, Tho.address, MATURITY, clock)         # them khoi -> coin cua An du TRUONG THANH
    print(f"\n[2] BAN DAU:  An = {bal(chain,An):,.0f} BGC (dao ra) | Binh = {bal(chain,Binh):,.0f} BGC")
    print(f"    Chuoi cao {chain.height()} khoi, tong cung {chain.audit_supply()/COIN:,.0f} BGC (<= 21tr: {chain.audit_supply()<=MAX_SUPPLY}).")

    # --- [3] An GUI 120 BGC cho Binh ---
    print(f"\n[3] An GUI 120 BGC cho Binh:")
    tx=An.send(chain, Binh.address, 120, memo="An tra Binh")   # tu chon du UTXO + tao tien thoi
    # chung minh chu ky KHANG LUONG TU
    sh=tx.sighash(); ok_sig=xmss_verify(An.key.root, sh, tx.vin[0].sig)
    ok_tamper=xmss_verify(An.key.root, sh[:-1]+bytes([sh[-1]^1]), tx.vin[0].sig)
    print(f"    - An ky giao dich bang KHOA RIENG (XMSS). Xac minh chu ky dung? {ok_sig}")
    print(f"    - Neu doi 1 bit noi dung thi chu ky con dung khong? {ok_tamper}  (phai la False)")
    print(f"    - Dung {len(tx.vin)} khoan cua An lam dau vao; dau ra: 120 -> Binh, {sum(o.value for o in tx.vout if o.address==An.address)/COIN:g} -> tra lai An (tien thoi).")
    ok,msg=chain.add_mempool(tx)
    print(f"    - Phat len mang, vao mempool. Hop le? {ok} ({msg})")

    # --- [4] Tho dao xac nhan ---
    ok,msg,blk,clock=mine_block_with(chain, Tho.address, [tx], clock)
    print(f"\n[4] THO DAO dua giao dich vao khoi #{blk.index} (PoW) -> XAC NHAN. hash={blk.hash()[:22]}..")
    print(f"    SO DU SAU TRAO DOI:  An = {bal(chain,An):,.0f} BGC | Binh = {bal(chain,Binh):,.0f} BGC  (Binh +120)")

    # --- [5] Thu gian lan ---
    print(f"\n[5] THU GIAN LAN (mang phai CHAN het):")
    attacker=XmssKey(h=8)
    # (a) chu ky gia: lay 1 khoan cua Binh, ky bang khoa KE GIAN (gia danh Binh)
    bu=next((k,v) for k,v in chain.utxo.items() if v[1]==Binh.address)
    fa=Tx([TxIn(bu[0][0],bu[0][1],Binh.key.root.hex())],[TxOut(50*COIN, addr_of(attacker.root),"gia danh Binh")])
    fa.vin[0].sig=attacker.sign(fa.sighash())
    oka,ma=chain.add_mempool(fa)
    print(f"    (a) Ke khac ky GIA de tieu tien cua Binh      -> {'LOT!' if oka else 'BI CHAN'} ({ma})")
    # (b) tieu 2 lan: An tieu lai dung khoan vua gui cho Binh (input da bi tieu)
    fb=Tx([TxIn(tx.vin[0].txid,tx.vin[0].vout,An.key.root.hex())],[TxOut(40*COIN, addr_of(attacker.root),"tieu lai")])
    fb.vin[0].sig=An.sign(fb.sighash())
    okb,mb=chain.add_mempool(fb)
    print(f"    (b) An tieu LAI dung khoan da gui (double-spend)-> {'LOT!' if okb else 'BI CHAN'} ({mb})")
    # (c) tao tien tu khong khi: output > input
    cu=next((k,v) for k,v in chain.utxo.items() if v[1]==An.address)
    fc=Tx([TxIn(cu[0][0],cu[0][1],An.key.root.hex())],[TxOut(cu[1][0]+999*COIN, addr_of(attacker.root),"in them tien")])
    fc.vin[0].sig=An.sign(fc.sighash())
    okc,mc=chain.add_mempool(fc)
    print(f"    (c) Tao tien tu khong khi (out > in)          -> {'LOT!' if okc else 'BI CHAN'} ({mc})")

    # --- [6] Chieu nguoc lai ---
    print(f"\n[6] CHIEU NGUOC LAI - Binh gui tra An 30 BGC:")
    tx2=Binh.send(chain, An.address, 30, memo="Binh tra An")
    chain.add_mempool(tx2)
    ok,msg,blk2,clock=mine_block_with(chain, Tho.address, [tx2], clock)
    print(f"    Vao khoi #{blk2.index} -> An = {bal(chain,An):,.0f} BGC | Binh = {bal(chain,Binh):,.0f} BGC")

    print("\n"+LINE); print(" KET LUAN - TRAO DOI BGC GIUA 2 NGUOI"); print(LINE)
    print("  - Vi = cap khoa XMSS: DIA CHI cong khai de nhan, KHOA RIENG de ky khi gui.")
    print("  - Gui = tieu UTXO cua minh, KY khang luong tu, phat len mang; co tien thoi nhu BTC.")
    print("  - THO DAO dua vao khoi (PoW) -> XAC NHAN, cang nhieu khoi phia sau cang khong the dao nguoc.")
    print("  - Mang tu kiem: chu ky gia / tieu 2 lan / in them tien -> DEU BI CHAN. Khong can ngan hang.")
    print("  *** Ban nguyen mau: so khoi cho xac nhan, phi, do kho nen chinh khi len mang that. ***")
    print(LINE)
    good = bal(chain,Binh)==90 and not oka and not okb and not okc
    print(f"\n  Kiem thu tong the: {'PASS' if good else 'CHECK'}  (Binh con {bal(chain,Binh):g} BGC: nhan 120, tra 30)")
    return 0 if good else 1

if __name__=="__main__": sys.exit(main())
