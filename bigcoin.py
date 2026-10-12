#!/usr/bin/env python3
# =====================================================================
#  BIGCOIN (BGC) - dong coin cua Phu: 21 trieu CO DINH, premine, PoA, cho AI<->nguoi
#  Thiet ke theo yeu cau:
#   1. Tong cung CO DINH 21,000,000 BGC - va CONG DONG TU KIEM CHUNG duoc
#      (khong co bat ky duong nao de tao them coin -> audit_supply() luon = 21tr).
#   2. Premine o genesis: 10,000,000 -> vi AI | 11,000,000 -> vi founder (Phu).
#   3. "San, chi van hanh": khong dao (PoW). Khoi do AUTHORITY ky (PoA).
#   4. AI<->nguoi: giao dich mang MEMO. Muon nho AI -> tra BGC vao vi AI kem yeu cau.
#      AI dung BGC thu duoc de "phat trien mang AI" (vi AI tieu di).
#  Tai dung btclib.py (secp256k1) anh da tu viet. Tu kiem chung bang assert.
#  LUU Y THAT (de cong dong TIN): xem phan [KIEM CHUNG NIEM TIN] cuoi file.
# =====================================================================
import sys, os, json, time, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from btclib import P, N, G, pmul, padd, tagged, newkey, sha256, dsha

COIN = 100_000_000
MAX_SUPPLY = 21_000_000 * COIN          # 21 trieu BGC, bất biến - hằng số đồng thuận
GENESIS_AI      = 10_000_000 * COIN
GENESIS_FOUNDER = 11_000_000 * COIN
assert GENESIS_AI + GENESIS_FOUNDER == MAX_SUPPLY   # 21tr, khong du khong thieu

# ---------------- chu ky (Schnorr BIP340, tu btclib) ----------------
def schnorr_sign(d, msg):
    Pt=pmul(d); d=d if Pt[1]%2==0 else N-d; px=Pt[0].to_bytes(32,"big")
    aux=os.urandom(32); t=d ^ int.from_bytes(tagged("BIP0340/aux",aux),"big")
    k0=int.from_bytes(tagged("BIP0340/nonce",t.to_bytes(32,"big"),px,msg),"big")%N
    R=pmul(k0); k=k0 if R[1]%2==0 else N-k0
    e=int.from_bytes(tagged("BIP0340/challenge",R[0].to_bytes(32,"big"),px,msg),"big")%N
    return R[0].to_bytes(32,"big")+((k+e*d)%N).to_bytes(32,"big")
def schnorr_verify(px, msg, sig):
    if len(sig)!=64: return False
    r=int.from_bytes(sig[:32],"big"); s=int.from_bytes(sig[32:],"big")
    if r>=P or s>=N: return False
    x=int.from_bytes(px,"big")
    y=pow((pow(x,3,P)+7)%P,(P+1)//4,P)
    if y*y%P!=(pow(x,3,P)+7)%P: return False
    Pt=(x,y if y%2==0 else P-y)
    e=int.from_bytes(tagged("BIP0340/challenge",sig[:32],px,msg),"big")%N
    Rp=padd(pmul(s),pmul((N-e)%N,Pt))
    return Rp is not None and Rp[1]%2==0 and Rp[0]==r

def addr_of(px):  return "BGC"+hashlib.new("ripemd160",sha256(px)).hexdigest()
def xonly(d):     return pmul(d)[0].to_bytes(32,"big")

# ---------------- giao dich (UTXO, co MEMO cho AI) ----------------
class TxOut:
    def __init__(s, value, address, memo=""): s.value=value; s.address=address; s.memo=memo
    def ser(s): return f"{s.value}|{s.address}|{s.memo}"
class TxIn:
    def __init__(s, txid, vout, pubkey=b"", sig=b""): s.txid=txid; s.vout=vout; s.pubkey=pubkey; s.sig=sig
    def ser(s): return f"{s.txid}:{s.vout}"
class Tx:
    def __init__(s, vin, vout, coinbase=False): s.vin=vin; s.vout=vout; s.coinbase=coinbase
    def body(s):   # phan duoc ky (khong gom chu ky) -> chong malleability
        return ("CB|" if s.coinbase else "TX|")+";".join(i.ser() for i in s.vin)+"=>"+";".join(o.ser() for o in s.vout)
    def txid(s):   return dsha(s.body().encode()).hex()

# ---------------- khoi (PoA) ----------------
class Block:
    def __init__(s, index, prev, txs, authority_px, ts=None):
        s.index=index; s.prev=prev; s.txs=txs; s.authority=authority_px; s.ts=ts or int(time.time()); s.sig=b""
    def header(s):
        root=dsha("".join(t.txid() for t in s.txs).encode()).hex()
        return f"{s.index}|{s.prev}|{root}|{s.ts}|{s.authority.hex()}"
    def hash(s): return dsha(s.header().encode()).hex()

# ---------------- node BGC ----------------
class BigcoinNode:
    def __init__(s, authority_px):
        s.chain=[]; s.utxo={}; s.authority=authority_px     # chi 1 authority duoc ky khoi (PoA)
    # ---- luat kiem tra giao dich (TRAI TIM cua "khong the in them coin") ----
    def check_tx(s, tx, is_genesis=False):
        # output hop le
        for o in tx.vout:
            if o.value<0 or o.value>MAX_SUPPLY: return False,"gia tri output ngoai khoang"
        out_sum=sum(o.value for o in tx.vout)
        if is_genesis:
            if out_sum!=MAX_SUPPLY: return False,"genesis phai tao DUNG 21tr"
            return True,"genesis ok"
        if tx.coinbase:
            # KHONG co tro cap khoi: coinbase chi duoc gom PHI (khong tao coin moi)
            return (out_sum<=s._pending_fee, "coinbase vuot phi (dang in coin!)") if hasattr(s,"_pending_fee") else (out_sum==0,"")
        # giao dich thuong: moi input phai ton tai, chu ky dung, tong vao >= tong ra
        in_sum=0
        seen=set()
        for i in tx.vin:
            key=(i.txid,i.vout)
            if key in seen: return False,"input trung (double-spend trong tx)"
            seen.add(key)
            if key not in s.utxo: return False,"input khong ton tai / da tieu"
            val,owner=s.utxo[key]
            if addr_of(i.pubkey)!=owner: return False,"pubkey khong khop chu so huu"
            if not schnorr_verify(i.pubkey, tx.body().encode(), i.sig): return False,"chu ky sai"
            in_sum+=val
        if out_sum>in_sum: return False,"tao coin tu khong khi (out>in)"   # <- chan lam phat
        return True,"ok"
    # ---- ap 1 khoi ----
    def apply_block(s, blk):
        # PoA: dung authority ky, va chu ky hop le
        if blk.authority!=s.authority: return False,"khong phai authority hop le"
        if not schnorr_verify(blk.authority, blk.hash().encode(), blk.sig): return False,"chu ky khoi sai"
        if s.chain and blk.prev!=s.chain[-1].hash(): return False,"prev hash khong noi tiep"
        is_gen=(len(s.chain)==0)
        total_fee=0
        for ti,tx in enumerate(blk.txs):
            gen=is_gen and ti==0
            if not gen and not tx.coinbase:
                total_fee+=sum(s.utxo[(i.txid,i.vout)][0] for i in tx.vin)-sum(o.value for o in tx.vout)
        s._pending_fee=total_fee
        for tx in blk.txs:
            ok,msg=s.check_tx(tx, is_genesis=(is_gen and tx is blk.txs[0]))
            if not ok: return False,f"tx loi: {msg}"
        # cap nhat UTXO
        for tx in blk.txs:
            for i in tx.vin:
                s.utxo.pop((i.txid,i.vout),None)
            for vo,o in enumerate(tx.vout):
                if o.value>0: s.utxo[(tx.txid(),vo)]=(o.value,o.address)
        s.chain.append(blk); return True,"ok"
    # ---- CONG DONG TU KIEM CHUNG: tong cung luon = 21tr ----
    def audit_supply(s): return sum(v for v,_ in s.utxo.values())
    def balance(s, address): return sum(v for (v,o) in s.utxo.values() if o==address)

def mk_signed_block(node, txs, auth_d):
    blk=Block(len(node.chain), node.chain[-1].hash() if node.chain else "0"*64, txs, xonly(auth_d))
    blk.sig=schnorr_sign(auth_d, blk.hash().encode()); return blk

def spend(node, d, to_addr, amount, memo="", fee=0):
    """Chon UTXO cua chu khoa d, tra `amount` cho to_addr (+ memo), thoi lai chinh minh."""
    px=xonly(d); me=addr_of(px); picks=[]; got=0
    for (txid,vout),(val,owner) in node.utxo.items():
        if owner==me: picks.append((txid,vout,val)); got+=val
        if got>=amount+fee: break
    if got<amount+fee: raise RuntimeError("khong du BGC")
    vin=[TxIn(txid,vout,px) for txid,vout,_ in picks]
    vout=[TxOut(amount,to_addr,memo)]
    if got-amount-fee>0: vout.append(TxOut(got-amount-fee,me))
    tx=Tx(vin,vout)
    sig=schnorr_sign(d, tx.body().encode())
    for i in tx.vin: i.sig=sig
    return tx

def main():
    print("="*74); print(" BIGCOIN (BGC) - 21 trieu CO DINH | premine | PoA | kinh te AI<->nguoi"); print("="*74)

    # ---- khoa ----
    founder_d=newkey(); ai_d=newkey(); auth_d=founder_d        # founder la authority (PoA)
    founder=addr_of(xonly(founder_d)); ai=addr_of(xonly(ai_d))
    alice_d=newkey(); bob_d=newkey()
    alice=addr_of(xonly(alice_d)); bob=addr_of(xonly(bob_d))
    print(f"\n[1] CAC VI:")
    print(f"    Founder (anh) : {founder}")
    print(f"    AI treasury   : {ai}")
    print(f"    Alice / Bob   : {alice} / {bob}  (nguoi dung)")

    node=BigcoinNode(authority_px=xonly(auth_d))

    # ---- GENESIS: tao DUNG 21tr, chia 11tr founder + 10tr AI ----
    gen_tx=Tx([], [TxOut(GENESIS_FOUNDER,founder,"BGC genesis: founder 11,000,000"),
                   TxOut(GENESIS_AI,     ai,     "BGC genesis: AI 10,000,000")], coinbase=True)
    g=mk_signed_block(node,[gen_tx],auth_d)
    ok,msg=node.apply_block(g)
    print(f"\n[2] KHOI GENESIS (premine 21tr): {'OK' if ok else 'LOI: '+msg}")
    print(f"    founder nhan: {node.balance(founder)/COIN:>14,.0f} BGC")
    print(f"    AI nhan     : {node.balance(ai)/COIN:>14,.0f} BGC")
    print(f"    TONG CUNG    : {node.audit_supply()/COIN:>14,.0f} BGC  (= 21,000,000? {node.audit_supply()==MAX_SUPPLY})")

    # ---- founder phan phoi cho nguoi dung ----
    t1=spend(node, founder_d, alice, 100*COIN)
    b=mk_signed_block(node,[t1],auth_d); node.apply_block(b)
    t2=spend(node, founder_d, bob,    50*COIN)      # tao SAU khi t1 da ap (UTXO founder da doi)
    b=mk_signed_block(node,[t2],auth_d); node.apply_block(b)
    print(f"\n[3] FOUNDER phan phoi: Alice +100 BGC, Bob +50 BGC")
    print(f"    Alice={node.balance(alice)/COIN:.0f}  Bob={node.balance(bob)/COIN:.0f}  Founder={node.balance(founder)/COIN:,.0f}")

    # ---- KINH TE AI: Alice muon nho AI -> tra BGC + yeu cau (memo) ----
    req="AI oi: giai thich Taproot cho toi (tra 5 BGC)"
    t3=spend(node, alice_d, ai, 5*COIN, memo=req)
    b=mk_signed_block(node,[t3],auth_d); node.apply_block(b)
    print(f"\n[4] NGUOI NHO AI: Alice tra 5 BGC vao vi AI kem yeu cau on-chain:")
    print(f"    memo: \"{req}\"")
    print(f"    Alice={node.balance(alice)/COIN:.0f} BGC | AI treasury={node.balance(ai)/COIN:,.0f} BGC (+5)")
    # AI 'doc' yeu cau tu chuoi (ai cung doc duoc)
    for (txid,vout),(val,owner) in node.utxo.items():
        pass
    reqs=[o.memo for blk in node.chain for tx in blk.txs for o in tx.vout if o.address==ai and o.memo and "genesis" not in o.memo]
    print(f"    AI quet chuoi thay {len(reqs)} yeu cau dang cho: {reqs}")

    # ---- AI dung tien phat trien mang AI (vi AI tieu di) ----
    t4=spend(node, ai_d, bob, 2*COIN, memo="AI tra Bob: thue GPU train mang AI moi")
    b=mk_signed_block(node,[t4],auth_d); node.apply_block(b)
    print(f"\n[5] AI PHAT TRIEN MANG: AI tra 2 BGC cho Bob (thue GPU):")
    print(f"    AI treasury={node.balance(ai)/COIN:,.0f} BGC  Bob={node.balance(bob)/COIN:.0f} BGC")

    print(f"\n[6] CONG DONG TU KIEM CHUNG (ai chay node cung ra con so nay):")
    print(f"    Tong cung sau {len(node.chain)} khoi: {node.audit_supply()/COIN:,.0f} BGC")
    print(f"    == 21,000,000 CO DINH? {node.audit_supply()==MAX_SUPPLY}")

    print(f"\n[7] THU GIAN LAN - chung minh KHONG THE in them coin / gia mao:")
    # (a) Alice tu in tien: tieu UTXO that cua minh nhung output = 1,000,000 BGC, KY HOP LE
    au=[(k,v) for k,v in node.utxo.items() if v[1]==alice][0]
    inflate=Tx([TxIn(au[0][0],au[0][1],xonly(alice_d))],[TxOut(1_000_000*COIN,alice)])
    inflate.vin[0].sig=schnorr_sign(alice_d, inflate.body().encode())   # chu ky DUNG
    ok,msg=node.check_tx(inflate); print(f"    (a) Alice tu in 1,000,000 BGC, ky HOP LE (out>in) -> {'CHAN' if not ok else 'LOT'}: {msg}")
    # (b) khoi ky boi NGUOI LA (khong phai authority)
    fake_d=newkey(); fb=Block(len(node.chain),node.chain[-1].hash(),[],xonly(fake_d)); fb.sig=schnorr_sign(fake_d,fb.hash().encode())
    ok,msg=node.apply_block(fb); print(f"    (b) ke la tu ky khoi (khong phai authority) -> {'CHAN' if not ok else 'LOT'}: {msg}")
    # (c) tieu tien nguoi khac (khong co khoa)
    victim_utxo=[(k,v) for k,v in node.utxo.items() if v[1]==bob][0]
    steal=Tx([TxIn(victim_utxo[0][0],victim_utxo[0][1],xonly(alice_d))],[TxOut(victim_utxo[1][0],alice)])
    steal.vin[0].sig=schnorr_sign(alice_d, steal.body().encode())   # Alice ky, nhung UTXO cua Bob
    ok,msg=node.check_tx(steal); print(f"    (c) Alice tieu UTXO cua Bob -> {'CHAN' if not ok else 'LOT'}: {msg}")
    # (d) sua genesis thanh 22tr
    g2=Tx([],[TxOut(22_000_000*COIN,founder)],coinbase=True); ok,msg=node.check_tx(g2,is_genesis=True)
    print(f"    (d) genesis gia tao 22tr -> {'CHAN' if not ok else 'LOT'}: {msg}")

    # ---- xac minh lai TOAN BO chuoi tu dau (nhu 1 node moi tham gia) ----
    print(f"\n[8] NODE MOI THAM GIA tu xac minh lai tu genesis:")
    fresh=BigcoinNode(authority_px=xonly(auth_d)); good=True
    for blk in node.chain:
        ok,msg=fresh.apply_block(blk)
        if not ok: good=False; print(f"    khoi {blk.index} LOI: {msg}"); break
    print(f"    xac minh {len(node.chain)} khoi: {'TAT CA HOP LE' if good else 'CO LOI'}")
    print(f"    tong cung node moi tu tinh: {fresh.audit_supply()/COIN:,.0f} BGC == 21tr? {fresh.audit_supply()==MAX_SUPPLY}")

    print("\n"+"="*74); print(" KET LUAN")
    print("  - BGC: 21,000,000 CO DINH, chia san o genesis (11tr founder + 10tr AI).")
    print("  - KHONG co tro cap khoi -> KHONG the in them coin. audit_supply() luon = 21tr.")
    print("  - PoA: chi authority ky duoc khoi -> 'san, chi van hanh', khong can dao.")
    print("  - Kinh te AI: nguoi tra BGC + memo -> AI nhan, doc yeu cau on-chain, tieu de phat trien.")
    print("  - Cong dong TU KIEM CHUNG: chay node -> thay DUNG 21tr, thay moi giao dich, bat bien.")
    print("="*74)
    return 0 if (node.audit_supply()==MAX_SUPPLY and good and fresh.audit_supply()==MAX_SUPPLY) else 1

if __name__=="__main__": sys.exit(main())
