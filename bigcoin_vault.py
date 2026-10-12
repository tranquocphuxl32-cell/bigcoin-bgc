#!/usr/bin/env python3
# =====================================================================
#  BIGCOIN-VAULT - KHOA 11tr FOUNDER ON-CHAIN de CONG DONG TIN (minh bach, khong hua suong)
#  Dung engine bigcoin_pq.py (khang luong tu) cung thu muc. Giu 21tr co dinh.
#  --------------------------------------------------------------------
#  VAN DE NIEM TIN: founder giu 11tr (52%) -> cong dong so anh "ban thao". Giau ten
#  KHONG giai quyet duoc (quyen kiem soat nam cong khai tren chuoi). Giai phap DUNG:
#  KHOA 11tr bang TIMELOCK DONG THUAN -> node TU CHOI moi giao dich tieu coin khoa
#  truoc chieu cao mo khoa. Ai cung DOC duoc 'lock_until' tren chuoi -> TU KIEM:
#  "founder KHONG THE ban truoc moc X". Day la cam ket bang CODE, bat bien, verify duoc.
#  (Cung co the chia vesting nhieu dot. Demo: khoa toan bo 11tr toi 1 moc.)
# =====================================================================
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bigcoin_pq as bp
from bigcoin_pq import XmssKey, H, addr_of, xmss_verify, COIN, MAX_SUPPLY, GEN_AI, GEN_FOUNDER

# ---- TxOut co them lock_until (chieu cao khoi toi khi moi tieu duoc) ----
class TxOut:
    def __init__(s,value,address,memo="",lock_until=0): s.value=value; s.address=address; s.memo=memo; s.lock=lock_until
    def ser(s): return f"{s.value}|{s.address}|{s.memo}|L{s.lock}"
TxIn=bp.TxIn; Tx=bp.Tx; Block=bp.Block

class NodeVault:
    def __init__(s,auth_root): s.chain=[]; s.utxo={}; s.auth=auth_root   # utxo: (txid,vout)->(value,addr,lock)
    def height(s): return len(s.chain)
    def check_tx(s,tx,is_genesis=False):
        for o in tx.vout:
            if o.value<0 or o.value>MAX_SUPPLY: return False,"gia tri ngoai khoang"
        out=sum(o.value for o in tx.vout)
        if is_genesis: return (out==MAX_SUPPLY,"genesis phai = 21tr")
        if tx.coinbase: return (out==0,"coinbase khong tao coin")
        insum=0; seen=set()
        for i in tx.vin:
            k=(i.txid,i.vout)
            if k in seen: return False,"input trung"
            if k not in s.utxo: return False,"input khong ton tai/da tieu"
            val,owner,lock=s.utxo[k]
            if lock>s.height(): return False,f"COIN DANG KHOA toi khoi {lock} (hien {s.height()})"  # <- timelock
            if addr_of(i.owner)!=owner: return False,"owner khong khop"
            if not xmss_verify(i.owner, tx.sighash(), i.sig): return False,"chu ky sai"
            insum+=val; seen.add(k)
        if out>insum: return False,"tao coin tu khong khi (out>in)"
        return True,"ok"
    def apply_block(s,blk):
        if blk.auth!=s.auth: return False,"khong phai authority"
        if not xmss_verify(blk.auth, blk.sighash(), blk.sig): return False,"chu ky khoi sai"
        if s.chain and blk.prev!=s.chain[-1].hash(): return False,"prev khong noi tiep"
        is_gen=(s.height()==0)
        for ti,tx in enumerate(blk.txs):
            ok,m=s.check_tx(tx,is_genesis=(is_gen and ti==0))
            if not ok: return False,f"tx loi: {m}"
        for tx in blk.txs:
            for i in tx.vin: s.utxo.pop((i.txid,i.vout),None)
            for vo,o in enumerate(tx.vout):
                if o.value>0: s.utxo[(tx.txid(),vo)]=(o.value,o.address,getattr(o,"lock",0))
        s.chain.append(blk); return True,"ok"
    def audit_supply(s): return sum(v for v,_,_ in s.utxo.values())
    def balance(s,a,spendable_only=False):
        h=s.height()
        return sum(v for v,o,lk in s.utxo.values() if o==a and (not spendable_only or lk<=h))
    def locked(s,a):
        h=s.height(); return sum(v for v,o,lk in s.utxo.values() if o==a and lk>h)

def mk_block(node,txs,auth):
    b=Block(node.height(), node.chain[-1].hash() if node.chain else "0"*64, txs, auth.root)
    b.sig=auth.sign(b.sighash()); return b
def spend(node,key,to,amount,memo="",lock=0):
    me=addr_of(key.root); picks=[]; got=0; h=node.height()
    for (t,v),(val,owner,lk) in node.utxo.items():
        if owner==me and lk<=h: picks.append((t,v,val)); got+=val   # chi tieu coin DA MO KHOA
        if got>=amount: break
    if got<amount: raise RuntimeError("khong du BGC da mo khoa")
    vin=[TxIn(t,v,key.root) for t,v,_ in picks]
    vout=[TxOut(amount,to,memo,lock)]
    if got-amount>0: vout.append(TxOut(got-amount,me))
    tx=Tx(vin,vout); sig=key.sign(tx.sighash())
    for i in tx.vin: i.sig=sig
    return tx

def main():
    print("="*78); print(" BIGCOIN-VAULT - khoa 11tr founder on-chain de cong dong TU KIEM (minh bach)"); print("="*78)
    founder=XmssKey(h=6); ai=XmssKey(h=5); alice=XmssKey(h=4); auth=founder
    F,AI,AL=addr_of(founder.root),addr_of(ai.root),addr_of(alice.root)
    node=NodeVault(auth.root)

    UNLOCK=10   # demo: khoa toi khoi 10 (that: dat ~2,100,000 ~ vai nam, hoac vesting nhieu dot)
    print(f"\n[1] GENESIS: 11tr founder KHOA toi khoi {UNLOCK} | 10tr AI thanh khoan (van hanh):")
    gen=Tx([],[TxOut(GEN_FOUNDER,F,"founder 11tr - KHOA (vesting)",lock_until=UNLOCK),
               TxOut(GEN_AI,AI,"AI treasury 10tr - thanh khoan")],coinbase=True)
    ok,m=node.apply_block(mk_block(node,[gen],auth))
    print(f"    genesis: {'OK' if ok else m}  | tong={node.audit_supply()/COIN:,.0f} (=21tr? {node.audit_supply()==MAX_SUPPLY})")
    print(f"    founder: khoa {node.locked(F)/COIN:,.0f} | tieu duoc {node.balance(F,True)/COIN:,.0f}")
    print(f"    AI     : tieu duoc {node.balance(AI,True)/COIN:,.0f}")
    print(f"    => CONG DONG DOC tren chuoi: 11tr cua founder co 'lock_until={UNLOCK}'. Bat bien.")

    print(f"\n[2] AI van hanh binh thuong (10tr thanh khoan): AI -> Alice 100 BGC")
    node.apply_block(mk_block(node,[spend(node,ai,AL,100*COIN,"AI cap von")],auth))
    print(f"    Alice={node.balance(AL)/COIN:.0f}  AI tieu duoc={node.balance(AI,True)/COIN:,.0f}")

    print(f"\n[3] FOUNDER THU BAN THAO 11tr SOM (khoi {node.height()} < {UNLOCK}):")
    try:
        bad=spend(node,founder,AL,1_000_000*COIN,"founder ban thao")
        ok,m=node.check_tx(bad); print(f"    tieu 1,000,000 BGC khoa -> {'CHAN' if not ok else 'LOT'}: {m}")
    except RuntimeError as e:
        print(f"    vi khong cho chon duoc coin khoa -> CHAN ngay o tao giao dich: {e}")
    # thu ep bang tay: build tx tieu truc tiep UTXO khoa
    lk_utxo=[(k,v) for k,v in node.utxo.items() if v[1]==F and v[2]>node.height()][0]
    force=Tx([TxIn(lk_utxo[0][0],lk_utxo[0][1],founder.root)],[TxOut(lk_utxo[1][0],AL,"ep ban")])
    force.vin[0].sig=founder.sign(force.sighash())
    ok,m=node.check_tx(force); print(f"    ep tieu thang UTXO khoa -> {'CHAN' if not ok else 'LOT'}: {m}")
    print(f"    => Du la FOUNDER, du co KHOA, van KHONG ban duoc truoc khoi {UNLOCK}. Code ep buoc.")

    print(f"\n[4] CHO TOI MOC MO KHOA (dao {UNLOCK-node.height()} khoi rong):")
    while node.height()<UNLOCK: node.apply_block(mk_block(node,[],auth))
    print(f"    chieu cao hien tai = {node.height()} (>= {UNLOCK}) -> 11tr da mo khoa")
    print(f"    founder tieu duoc bay gio: {node.balance(F,True)/COIN:,.0f} BGC")
    ok,m=node.check_tx(spend(node,founder,AL,500*COIN,"founder phan phoi SAU mo khoa"))
    print(f"    founder phan phoi 500 BGC (sau mo khoa) -> {'OK' if ok else 'CHAN: '+m}")

    print(f"\n[5] CONG DONG TU KIEM (node moi doc cam ket tu genesis):")
    g0=node.chain[0].txs[0]
    for vo,o in enumerate(g0.vout):
        print(f"    genesis out[{vo}]: {o.value/COIN:,.0f} BGC -> {o.address[:18]}.. lock_until={o.lock}")
    print(f"    tong cung: {node.audit_supply()/COIN:,.0f} BGC (=21tr? {node.audit_supply()==MAX_SUPPLY})")
    print("    => Bat ky ai chay node deu THAY 11tr bi khoa toi moc do. Khong can tin loi founder.")

    print("\n"+"="*78); print(" KET LUAN & LUU Y CHO ANH")
    print("  - Giau TEN khong tao niem tin (quyen kiem soat nam cong khai tren chuoi).")
    print("    KHOA COIN bang code moi tao niem tin: ai cung verify founder khong ban duoc som.")
    print("  - 11tr founder khoa toi moc mo khoa (nen dat vai nam / chia vesting nhieu dot).")
    print("  - 10tr AI thanh khoan de VAN HANH (tra robot/dich vu) - cung nen vesting 1 phan.")
    print("  - 21tr VAN co dinh; timelock chi quyet dinh KHI NAO tieu, khong tao/huy coin.")
    print("  *** LUU Y ***")
    print("  1. Nen khoa CA mot phan 10tr AI (vesting) de tranh 'quy AI' xa hang loat lam sap gia.")
    print("  2. Timelock bat bien = con dao 2 luoi: khoa roi KHONG rut som duoc ke ca khi can.")
    print("     Chon moc/vesting ky truoc khi phat hanh genesis (genesis khong sua duoc).")
    print("  3. Ket hop: khoa coin (file nay) + but danh (hop phap) + whitepaper trung thuc =")
    print("     cach ra mat dang tin, thay cho 'giau + chuyen AI tu tao' (khong ben, de bi lo).")
    print("="*78)
    return 0 if node.audit_supply()==MAX_SUPPLY else 1

if __name__=="__main__": sys.exit(main())
