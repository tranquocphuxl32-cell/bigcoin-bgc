#!/usr/bin/env python3
# =====================================================================
#  BGC MINER - MOT FILE DUY NHAT (tu chua tat ca). Gui file nay cho may khac:
#  chay la DAO ra BGC, BGC hien trong vi, va CHUYEN QUA LAI duoc.
#  Mac dinh tieng Duc + chon ngon ngu. Tu tao genesis ben trong (khong can file phu).
#  Chay:   python BGC_Miner_1file.py                 (mo trinh duyet, dao solo)
#          python BGC_Miner_1file.py --peers IP:9333 (tham gia mang, chuyen qua lai)
#  (Dong goi .exe:  pyinstaller --onefile --name BGC-Miner BGC_Miner_1file.py)
# =====================================================================
import hashlib, hmac, struct, json, subprocess, os, time, sys, socket, threading, argparse, functools, webbrowser, io, base64, math, re, secrets
from decimal import Decimal, InvalidOperation
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
try:
    import qrcode, qrcode.image.svg
    HAS_QR=True
except Exception:
    HAS_QR=False
print=functools.partial(print, flush=True)


# ================= btclib =================
#!/usr/bin/env python3
# =====================================================================
#  btclib.py - a small self-written library shared by the demos
#   - secp256k1, ECDSA (RFC6979), Schnorr (BIP340)
#   - SegWit transaction serialization, varint
#   - SIGHASH BIP143 (SegWit v0) and BIP341 (Taproot)
#   - Taproot: TapLeaf / TapBranch / TapTweak, control block
#   - bitcoin-cli calls (regtest)
#  In BGC it is used only for secp256k1 ECDH in the encrypted transport (bgc_secure).
# =====================================================================

BIN="/home/claude/bitcoin/build/bin"
def make_cli(datadir):
    def cli(*a, wallet=None):
        cmd=[f"{BIN}/bitcoin-cli","-regtest",f"-datadir={datadir}"]+([f"-rpcwallet={wallet}"] if wallet else [])+[("true" if x is True else "false" if x is False else str(x)) for x in a]
        out=subprocess.run(cmd,capture_output=True,text=True)
        if out.returncode: raise RuntimeError(out.stderr.strip() or out.stdout.strip())
        try: return json.loads(out.stdout)
        except Exception: return out.stdout.strip()
    return cli
def start_node(datadir, extra=()):
    subprocess.run(["pkill","bitcoind"],capture_output=True); time.sleep(1)
    subprocess.run(["rm","-rf",datadir]); os.makedirs(datadir)
    subprocess.run([f"{BIN}/bitcoind","-regtest",f"-datadir={datadir}","-fallbackfee=0.0001","-txindex","-daemon",*extra],capture_output=True)
    cli=make_cli(datadir)
    for _ in range(30):
        try: cli("getblockcount"); return cli
        except Exception: time.sleep(1)
    raise RuntimeError("node khong len")

# ---------- hash ----------
def sha256(b): return hashlib.sha256(b).digest()
def dsha(b): return sha256(sha256(b))
def tagged(tag,*ms):
    th=sha256(tag.encode()); return sha256(th+th+b"".join(ms))

# ---------- secp256k1 ----------
P=2**256-2**32-977
N=0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
G=(0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8)
def inv(a,m): return pow(a,m-2,m)
def padd(A,B):
    if A is None: return B
    if B is None: return A
    (x1,y1),(x2,y2)=A,B
    if x1==x2 and (y1+y2)%P==0: return None
    m=(3*x1*x1)*inv(2*y1,P)%P if A==B else (y2-y1)*inv(x2-x1,P)%P
    x3=(m*m-x1-x2)%P; return (x3,(m*(x1-x3)-y1)%P)
def pmul(k,Pt=G):
    R=None
    while k:
        if k&1: R=padd(R,Pt)
        Pt=padd(Pt,Pt); k>>=1
    return R
def newkey():
    while True:
        d=int.from_bytes(os.urandom(32),"big")
        if 1<=d<N: return d
def pub_compressed(d):
    x,y=pmul(d); return (b"\x03" if y&1 else b"\x02")+x.to_bytes(32,"big")
def pub_xonly(d): return pmul(d)[0].to_bytes(32,"big")
def lift_x(xb):
    x=int.from_bytes(xb,"big"); y=pow((pow(x,3,P)+7)%P,(P+1)//4,P)
    return (x, y if y%2==0 else P-y)

# ---------- ECDSA ----------
def _k6979(z,d):
    x=d.to_bytes(32,"big"); h1=z.to_bytes(32,"big"); V=b"\x01"*32; K=b"\x00"*32
    K=hmac.new(K,V+b"\x00"+x+h1,hashlib.sha256).digest(); V=hmac.new(K,V,hashlib.sha256).digest()
    K=hmac.new(K,V+b"\x01"+x+h1,hashlib.sha256).digest(); V=hmac.new(K,V,hashlib.sha256).digest()
    while True:
        V=hmac.new(K,V,hashlib.sha256).digest(); k=int.from_bytes(V,"big")
        if 1<=k<N: return k
        K=hmac.new(K,V+b"\x00",hashlib.sha256).digest(); V=hmac.new(K,V,hashlib.sha256).digest()
def ecdsa_sign_der(d,z,hashtype=1):
    k=_k6979(z,d); r=pmul(k)[0]%N; s=inv(k,N)*(z+r*d)%N
    if s>N//2: s=N-s
    def enc(n):
        b=n.to_bytes((n.bit_length()+7)//8,"big")
        if b[0]&0x80: b=b"\x00"+b
        return b"\x02"+bytes([len(b)])+b
    body=enc(r)+enc(s); return b"\x30"+bytes([len(body)])+body+bytes([hashtype])

# ---------- Schnorr BIP340 ----------
def schnorr_sign(d0,msg,aux=None):
    aux=aux or os.urandom(32)
    Pt=pmul(d0); d=d0 if Pt[1]%2==0 else N-d0; px=Pt[0].to_bytes(32,"big")
    t=d ^ int.from_bytes(tagged("BIP0340/aux",aux),"big")
    k0=int.from_bytes(tagged("BIP0340/nonce",t.to_bytes(32,"big"),px,msg),"big")%N
    R=pmul(k0); k=k0 if R[1]%2==0 else N-k0
    e=int.from_bytes(tagged("BIP0340/challenge",R[0].to_bytes(32,"big"),px,msg),"big")%N
    return R[0].to_bytes(32,"big")+((k+e*d)%N).to_bytes(32,"big")

# ---------- serialize ----------
def varint(n):
    if n<0xfd: return bytes([n])
    if n<=0xffff: return b"\xfd"+struct.pack("<H",n)
    return b"\xfe"+struct.pack("<I",n)
def push(b): return (bytes([len(b)]) if len(b)<0x4c else b"\x4c"+bytes([len(b)]))+b
def scriptnum(n):
    if n==0: return b"\x00"           # OP_0
    if 1<=n<=16: return bytes([0x50+n])
    b=n.to_bytes((n.bit_length()+7)//8,"little")
    if b[-1]&0x80: b+=b"\x00"
    return push(b)
def outpoint(txid,vout): return bytes.fromhex(txid)[::-1]+struct.pack("<I",vout)
def ser_out(value,spk): return struct.pack("<Q",value)+varint(len(spk))+spk
def ser_tx(version, vins, vouts, locktime, witnesses=None):
    """vins: list of (txid,vout,scriptSig,sequence); vouts: list of (value,spk); witnesses: list of list of bytes"""
    b=struct.pack("<I",version)
    if witnesses: b+=b"\x00\x01"
    b+=varint(len(vins))
    for txid,vout,ss,seq in vins: b+=outpoint(txid,vout)+varint(len(ss))+ss+struct.pack("<I",seq)
    b+=varint(len(vouts))
    for v,spk in vouts: b+=ser_out(v,spk)
    if witnesses:
        for w in witnesses: b+=varint(len(w))+b"".join(varint(len(x))+x for x in w)
    return b+struct.pack("<I",locktime)

# ---------- SIGHASH BIP143 (SegWit v0, P2WSH/P2WPKH) ----------
def sighash_bip143(version,vins,vouts,locktime,idx,script_code,amount,hashtype=1):
    hp=dsha(b"".join(outpoint(t,v) for t,v,_,_ in vins))
    hs=dsha(b"".join(struct.pack("<I",s) for _,_,_,s in vins))
    ho=dsha(b"".join(ser_out(v,s) for v,s in vouts))
    t,v,_,seq=vins[idx]
    pre=(struct.pack("<I",version)+hp+hs+outpoint(t,v)+varint(len(script_code))+script_code
         +struct.pack("<Q",amount)+struct.pack("<I",seq)+ho+struct.pack("<I",locktime)+struct.pack("<I",hashtype))
    return int.from_bytes(dsha(pre),"big")

# ---------- SIGHASH BIP341 (Taproot, SIGHASH_DEFAULT) ----------
def sighash_bip341(version,vins,vouts,locktime,idx,prev_amounts,prev_spks,leaf_hash=None):
    sp=sha256(b"".join(outpoint(t,v) for t,v,_,_ in vins))
    sa=sha256(b"".join(struct.pack("<Q",a) for a in prev_amounts))
    ss=sha256(b"".join(varint(len(s))+s for s in prev_spks))
    sq=sha256(b"".join(struct.pack("<I",s) for _,_,_,s in vins))
    so=sha256(b"".join(ser_out(v,s) for v,s in vouts))
    ext=1 if leaf_hash else 0
    msg=(b"\x00"+struct.pack("<I",version)+struct.pack("<I",locktime)+sp+sa+ss+sq+so
         +bytes([ext*2])+struct.pack("<I",idx))
    if leaf_hash: msg+=leaf_hash+b"\x00"+b"\xff\xff\xff\xff"
    return tagged("TapSighash",b"\x00",msg)

# ---------- Taproot tree ----------
def tapleaf(script,ver=0xc0): return tagged("TapLeaf",bytes([ver]),varint(len(script)),script)
def tapbranch(a,b): return tagged("TapBranch",*(sorted([a,b])))
def taptweak(px,root=b""): return int.from_bytes(tagged("TapTweak",px,root),"big")
def tweak_pubkey(d_internal, root=b""):
    Pt=pmul(d_internal); px=Pt[0].to_bytes(32,"big")
    d=d_internal if Pt[1]%2==0 else N-d_internal
    t=taptweak(px,root); Q=pmul((d+t)%N)
    return Q, (d+t)%N, px      # Q (output key point), tweaked private, internal x
def p2tr_spk(Q): return b"\x51\x20"+Q[0].to_bytes(32,"big")
def p2wsh_spk(script): return b"\x00\x20"+sha256(script)

# ================= bigcoin_pq =================
#!/usr/bin/env python3
# =====================================================================
#  BIGCOIN-PQ (BGC post-quantum) - uses ONLY SHA-256, NO secp256k1 -> SELF-CONTAINED
#  --------------------------------------------------------------------
#  The quantum threat: Shor's algorithm breaks ECDSA/Schnorr (it recovers the private
#  key from the public key on secp256k1). This module replaces signatures with a
#  HASH-BASED scheme:
#    - WOTS+ : a Winternitz ONE-TIME signature (only SHA-256 hash chains)
#    - XMSS  : a Merkle tree of many WOTS keys -> one address can sign 2^h times
#  Security rests SOLELY on the one-wayness of SHA-256. A quantum computer (Grover)
#  only halves the security (256-bit -> 128-bit), which is still safe. Shor is useless
#  against a hash function. This follows NIST SP 800-208 (XMSS).
# =====================================================================

def H(b): return hashlib.sha256(b).digest()

# ---------------- WOTS+ (one-time signature, SHA-256 only) ----------------
W=16; LEN1=64; LEN2=3; LEN=LEN1+LEN2     # 256-bit msg / 4 bits = 64 base-16 digits + 3 checksum digits

def chain(x, start, steps):
    """Hash `x` `steps` times in a row, starting at absolute position `start`."""
    for i in range(start, start+steps):
        x = H(x + bytes([i]))
    return x

def wots_keygen(seed):
    sk=[H(seed+b"sk"+i.to_bytes(2,"big")) for i in range(LEN)]   # LEN secrets derived from the seed
    pk=[chain(sk[i],0,W-1) for i in range(LEN)]                  # top of each chain = public key
    return sk, pk
def wots_pk_hash(pk): return H(b"".join(pk))

def msg_digits(mh):
    d=[]
    for b in mh: d.append(b>>4); d.append(b&0xf)     # 64 digits
    csum=sum(W-1-x for x in d)
    for _ in range(LEN2): d.append(csum&0xf); csum>>=4
    return d                                          # LEN digits

def wots_sign(sk, mh):
    d=msg_digits(mh); return [chain(sk[i],0,d[i]) for i in range(LEN)]
def wots_pk_from_sig(sig, mh):
    d=msg_digits(mh); return [chain(sig[i],d[i],W-1-d[i]) for i in range(LEN)]

# ---------------- Merkle tree (XMSS) ----------------
def merkle(leaves):
    levels=[leaves]; cur=leaves
    while len(cur)>1:
        cur=[H(cur[i]+cur[i+1]) for i in range(0,len(cur),2)]; levels.append(cur)
    return levels
def auth_path(levels, idx):
    p=[];
    for lvl in levels[:-1]: p.append(lvl[idx^1]); idx//=2
    return p
def root_from(leaf, idx, path):
    h=leaf
    for sib in path:
        h=H(sib+h) if idx&1 else H(h+sib); idx//=2
    return h

MAX_XMSS_H=20                               # tallest tree a verifier accepts (2^20 signatures)

class XmssKey:
    """A post-quantum address = the Merkle root over 2^h WOTS one-time keys."""
    def __init__(s, master=None, h=4):
        if not 1<=h<=MAX_XMSS_H: raise ValueError(f"h must be 1..{MAX_XMSS_H}")
        s.master=master or os.urandom(32); s.h=h; L=1<<h; s.next=0
        s.leaves=[]
        for k in range(L):
            _,pk=wots_keygen(H(s.master+k.to_bytes(4,"big"))); s.leaves.append(wots_pk_hash(pk))
        s.levels=merkle(s.leaves); s.root=s.levels[-1][0]
    def sign(s, mh):
        if s.next>=(1<<s.h): raise RuntimeError("out of one-time signatures (need a new address / larger h)")
        k=s.next; s.next+=1
        return s.sign_at(k, mh)
    def sign_at(s, k, mh):
        """Sign with leaf k. The caller guarantees k is never used twice (see bgcfl_wallet)."""
        if not 0<=k<(1<<s.h): raise RuntimeError("out of one-time signatures (need a new address / larger h)")
        sk,_=wots_keygen(H(s.master+k.to_bytes(4,"big")))
        return {"i":k,"w":[x.hex() for x in wots_sign(sk,mh)],"p":[x.hex() for x in auth_path(s.levels,k)]}

def _hex32(x):
    """Strict lowercase 64-hex -> 32 bytes, or None (no spaces/uppercase: one encoding per value)."""
    if type(x) is not str or len(x)!=64: return None
    try: b=bytes.fromhex(x)
    except ValueError: return None
    return b if b.hex()==x else None

def xmss_verify(root, mh, sig):
    """True only for a well-formed, valid signature. Never raises on hostile input."""
    if type(root) is not bytes or len(root)!=32 or type(mh) is not bytes or len(mh)!=32: return False
    if type(sig) is not dict: return False
    i=sig.get("i"); w=sig.get("w"); p=sig.get("p")
    if type(i) is not int or type(w) is not list or type(p) is not list: return False
    if len(w)!=LEN or not 1<=len(p)<=MAX_XMSS_H or not 0<=i<(1<<len(p)): return False
    wb=[_hex32(x) for x in w]; pb=[_hex32(x) for x in p]
    if None in wb or None in pb: return False
    leaf=wots_pk_hash(wots_pk_from_sig(wb, mh))
    return root_from(leaf, i, pb)==root

# ---------------- BGC economics (unchanged); signatures = XMSS ----------------
COIN=100_000_000; MAX_SUPPLY=21_000_000*COIN
GEN_AI=10_000_000*COIN; GEN_FOUNDER=11_000_000*COIN
def addr_of(root): return "BGCQ"+root.hex()        # Q = quantum-resistant

class TxOut:
    def __init__(s,value,address,memo=""): s.value=value; s.address=address; s.memo=memo
    def ser(s): return f"{s.value}|{s.address}|{s.memo}"
class TxIn:
    def __init__(s,txid,vout,owner_root=b"",sig=None): s.txid=txid; s.vout=vout; s.owner=owner_root; s.sig=sig
    def ser(s): return f"{s.txid}:{s.vout}"
class Tx:
    def __init__(s,vin,vout,coinbase=False): s.vin=vin; s.vout=vout; s.coinbase=coinbase
    def body(s): return ("CB|" if s.coinbase else "TX|")+";".join(i.ser() for i in s.vin)+"=>"+";".join(o.ser() for o in s.vout)
    def txid(s): return H(s.body().encode()).hex()
    def sighash(s): return H(b"BGCQ-sig"+s.body().encode())

class Block:
    def __init__(s,index,prev,txs,auth_root): s.index=index; s.prev=prev; s.txs=txs; s.auth=auth_root; s.ts=int(time.time()); s.sig=None
    def header(s): return f"{s.index}|{s.prev}|{H(''.join(t.txid() for t in s.txs).encode()).hex()}|{s.ts}|{s.auth.hex()}"
    def hash(s): return H(s.header().encode()).hex()
    def sighash(s): return H(b"BGCQ-blk"+s.header().encode())

class NodePQ:
    def __init__(s, auth_root): s.chain=[]; s.utxo={}; s.auth=auth_root
    def check_tx(s,tx,is_genesis=False):
        for o in tx.vout:
            if o.value<0 or o.value>MAX_SUPPLY: return False,"value out of range"
        out=sum(o.value for o in tx.vout)
        if is_genesis: return (out==MAX_SUPPLY,"genesis must equal 21M")
        if tx.coinbase: return (out==0,"coinbase may not create coins")
        insum=0; seen=set()
        for i in tx.vin:
            k=(i.txid,i.vout)
            if k in seen: return False,"duplicate input"
            seen.add(k)
            if k not in s.utxo: return False,"input missing/already spent"
            val,owner=s.utxo[k]
            if addr_of(i.owner)!=owner: return False,"owner mismatch"
            if not xmss_verify(i.owner, tx.sighash(), i.sig): return False,"bad XMSS signature"
            insum+=val
        if out>insum: return False,"coins created from nothing (out>in)"
        return True,"ok"
    def apply_block(s,blk):
        if blk.auth!=s.auth: return False,"not an authority"
        if not xmss_verify(blk.auth, blk.sighash(), blk.sig): return False,"bad block signature (XMSS)"
        if s.chain and blk.prev!=s.chain[-1].hash(): return False,"prev does not link"
        is_gen=(len(s.chain)==0)
        for ti,tx in enumerate(blk.txs):
            ok,m=s.check_tx(tx,is_genesis=(is_gen and ti==0))
            if not ok: return False,f"tx error: {m}"
        for tx in blk.txs:
            for i in tx.vin: s.utxo.pop((i.txid,i.vout),None)
            for vo,o in enumerate(tx.vout):
                if o.value>0: s.utxo[(tx.txid(),vo)]=(o.value,o.address)
        s.chain.append(blk); return True,"ok"
    def audit_supply(s): return sum(v for v,_ in s.utxo.values())
    def balance(s,a): return sum(v for v,o in s.utxo.values() if o==a)

def mk_block(node,txs,auth_key):
    b=Block(len(node.chain), node.chain[-1].hash() if node.chain else "0"*64, txs, auth_key.root)
    b.sig=auth_key.sign(b.sighash()); return b
def spend(node,key,to_addr,amount,memo="",fee=0):
    me=addr_of(key.root); picks=[]; got=0
    for (txid,vout),(val,owner) in node.utxo.items():
        if owner==me: picks.append((txid,vout)); got+=val
        if got>=amount+fee: break
    if got<amount+fee: raise RuntimeError("insufficient BGC")
    vin=[TxIn(t,v,key.root) for t,v in picks]
    vout=[TxOut(amount,to_addr,memo)]
    if got-amount-fee>0: vout.append(TxOut(got-amount-fee,me))
    tx=Tx(vin,vout); sig=key.sign(tx.sighash())
    for i in tx.vin: i.sig=sig   # (demo: one shared signature; in production each input gets its own one-time sig)
    return tx

def main():
    print("="*76); print(" BIGCOIN-PQ (BGC post-quantum) - hash-based XMSS signatures, SHA-256 only, SELF-CONTAINED"); print("="*76)

    print("\n[1] POST-QUANTUM KEYS (XMSS, h=4 -> each address signs 16 times):")
    t0=time.time()
    founder=XmssKey(h=6); ai=XmssKey(h=4); alice=XmssKey(h=4); bob=XmssKey(h=4)
    auth=founder
    print(f"    created 4 XMSS wallets in {time.time()-t0:.1f}s")
    print(f"    Founder: {addr_of(founder.root)[:28]}..  (h=6 -> signs 64 blocks)")
    print(f"    AI     : {addr_of(ai.root)[:28]}..")
    print(f"    ADDRESS = MERKLE ROOT (a single 32-byte hash). No 'EC public key' is ever exposed.")

    node=NodePQ(auth.root)
    gen=Tx([],[TxOut(GEN_FOUNDER,addr_of(founder.root),"genesis founder 11M"),
               TxOut(GEN_AI,addr_of(ai.root),"genesis AI 10M")],coinbase=True)
    g=mk_block(node,[gen],auth); ok,m=node.apply_block(g)
    print(f"\n[2] GENESIS 21M (premine): {'OK' if ok else m}")
    print(f"    founder={node.balance(addr_of(founder.root))/COIN:,.0f}  AI={node.balance(addr_of(ai.root))/COIN:,.0f}  TOTAL={node.audit_supply()/COIN:,.0f} (=21M? {node.audit_supply()==MAX_SUPPLY})")

    t1=spend(node,founder,addr_of(alice.root),100*COIN); node.apply_block(mk_block(node,[t1],auth))
    t2=spend(node,founder,addr_of(bob.root),50*COIN);     node.apply_block(mk_block(node,[t2],auth))
    print(f"\n[3] Distribution: Alice={node.balance(addr_of(alice.root))/COIN:.0f} Bob={node.balance(addr_of(bob.root))/COIN:.0f}  (signed with XMSS, verified OK)")

    req="Hey AI, explain hash-based signatures (pay 5 BGC)"
    t3=spend(node,alice,addr_of(ai.root),5*COIN,memo=req); node.apply_block(mk_block(node,[t3],auth))
    print(f"\n[4] A human hires the AI (post-quantum tx): Alice->AI 5 BGC + on-chain memo")
    print(f"    AI treasury={node.balance(addr_of(ai.root))/COIN:,.0f} BGC")

    print(f"\n[5] ANYONE CAN AUDIT: total supply after {len(node.chain)} blocks = {node.audit_supply()/COIN:,.0f} BGC (=21M? {node.audit_supply()==MAX_SUPPLY})")

    print("\n[6] WHY QUANTUM-RESISTANT - why Shor is useless:")
    print("    - Address = Merkle root (a hash). Recovering a private key means INVERTING SHA-256.")
    print("    - Shor breaks discrete log (ECDSA) but CANNOT invert a hash function.")
    print("    - Grover only speeds up preimage search x2 (256-bit -> 128-bit) -> still out of reach.")
    # illustration: a 'quantum attack' = trying to invert one leaf hash -> needs ~2^128 (infeasible)
    target=founder.leaves[0]
    print(f"    example: one leaf = {target.hex()[:24]}.. ; finding a preimage needs ~2^128 hashes -> hopeless.")

    print("\n[7] FRAUD RESISTANCE (like normal BGC, but with PQ signatures):")
    # (a) mint coins: out>in, with a valid XMSS signature
    au=[(k,v) for k,v in node.utxo.items() if v[1]==addr_of(alice.root)][0]
    inflate=Tx([TxIn(au[0][0],au[0][1],alice.root)],[TxOut(1_000_000*COIN,addr_of(alice.root))])
    inflate.vin[0].sig=alice.sign(inflate.sighash())
    ok,m=node.check_tx(inflate); print(f"    (a) mint 1,000,000 BGC (valid PQ sig, out>in) -> {'REJECTED' if not ok else 'PASSED'}: {m}")
    # (b) forge a signature: flip one byte of the WOTS sig
    bobkey2=XmssKey(h=4)
    tx=spend(node,bob,addr_of(alice.root),1*COIN)
    tx.vin[0].sig["w"][0]="00"*32                      # corrupt one signature element
    ok,m=node.check_tx(tx); print(f"    (b) tamper with XMSS signature -> {'REJECTED' if not ok else 'PASSED'}: {m}")
    # (c) sign with a key other than the owner's
    tx2=Tx([TxIn(au[0][0],au[0][1],bob.root)],[TxOut(au[1][0],addr_of(bob.root))])
    tx2.vin[0].sig=bob.sign(tx2.sighash())             # Bob signs Alice's UTXO
    ok,m=node.check_tx(tx2); print(f"    (c) Bob signs Alice's UTXO -> {'REJECTED' if not ok else 'PASSED'}: {m}")

    print("\n[8] IMPORTANT WARNING (one-time): each XMSS leaf signs only ONCE.")
    print("    Signing two different messages with the SAME leaf leaks chain material -> forgeable.")
    print("    So the wallet MUST advance the leaf index on every sign (stateful). The file tracks 'next'.")
    print(f"    Founder has signed {founder.next}/{1<<founder.h} times; when exhausted, use a new address (or larger h / stateless SPHINCS+).")

    print("\n[9] A FRESH NODE re-verifies from genesis (PQ signatures):")
    fresh=NodePQ(auth.root); good=True
    for blk in node.chain:
        ok,m=fresh.apply_block(blk)
        if not ok: good=False; print("   error:",m); break
    print(f"    {len(node.chain)} blocks: {'ALL VALID' if good else 'ERROR'}; total={fresh.audit_supply()/COIN:,.0f} (=21M? {fresh.audit_supply()==MAX_SUPPLY})")

    print("\n"+"="*76); print(" CONCLUSION")
    print("  - BGC-PQ: same as BGC (21M cap, 11M/10M, PoA, AI memo) but with HASH-BASED signatures.")
    print("  - Address = Merkle root; signature = WOTS+ one-time + Merkle path (XMSS, NIST standard).")
    print("  - Security rests only on SHA-256 one-wayness -> SHOR (quantum) USELESS; Grover only x2.")
    print("  - Trade-off: larger signatures (KBs) and ONE LEAF PER SIGN (stateful, must count the index).")
    print("  - File uses ONLY hashlib -> SELF-CONTAINED, no secp256k1/btclib needed.")
    print("  - For unlimited stateless signing in practice: use SPHINCS+ (also hash-based, NIST).")
    print("="*76)
    return 0 if (node.audit_supply()==MAX_SUPPLY and good) else 1

# ================= bgc_secure =================
#!/usr/bin/env python3
# =====================================================================
#  BGC SECURE - a BIP324-style ENCRYPTED P2P channel: ECDH (secp256k1) + HKDF-SHA256 +
#  ChaCha20-Poly1305. An eavesdropper cannot read or alter messages. Forward secrecy
#  (ephemeral session key per connection). Wraps a plain socket -> sends/receives encrypted frames.
#  NOTE: this encrypts the LINK with classical ECDH; if broken by a quantum computer it only
#  exposes network METADATA, NOT the coins (coin signatures are hash-based PQ). It can later be
#  upgraded to a post-quantum KEM (ML-KEM). AEAD cipher: self-written ChaCha20-Poly1305 (RFC8439).
# =====================================================================

# ---- ChaCha20 (RFC8439) ----
def _rotl(v,b): return ((v<<b)&0xffffffff)|(v>>(32-b))
def _qr(s,a,b,c,d):
    s[a]=(s[a]+s[b])&0xffffffff; s[d]=_rotl(s[d]^s[a],16)
    s[c]=(s[c]+s[d])&0xffffffff; s[b]=_rotl(s[b]^s[c],12)
    s[a]=(s[a]+s[b])&0xffffffff; s[d]=_rotl(s[d]^s[a],8)
    s[c]=(s[c]+s[d])&0xffffffff; s[b]=_rotl(s[b]^s[c],7)
def _block(key,nonce,cnt):
    st=[0x61707865,0x3320646e,0x79622d32,0x6b206574]+list(struct.unpack("<8I",key))+[cnt]+list(struct.unpack("<3I",nonce))
    w=st[:]
    for _ in range(10):
        _qr(w,0,4,8,12);_qr(w,1,5,9,13);_qr(w,2,6,10,14);_qr(w,3,7,11,15)
        _qr(w,0,5,10,15);_qr(w,1,6,11,12);_qr(w,2,7,8,13);_qr(w,3,4,9,14)
    return struct.pack("<16I",*[(w[i]+st[i])&0xffffffff for i in range(16)])
def _xor(key,nonce,data,start=1):
    out=bytearray()
    for i in range((len(data)+63)//64):
        chunk=data[64*i:64*i+64]; ks=_block(key,nonce,start+i)[:len(chunk)]
        out+=(int.from_bytes(chunk,"little")^int.from_bytes(ks,"little")).to_bytes(len(chunk),"little")
    return bytes(out)
def _poly(key,msg):
    r=int.from_bytes(key[:16],"little")&0x0ffffffc0ffffffc0ffffffc0fffffff; sx=int.from_bytes(key[16:],"little")
    p=(1<<130)-5; acc=0
    for i in range(0,len(msg),16):
        acc=(acc+int.from_bytes(msg[i:i+16]+b"\x01","little"))*r%p
    return ((acc+sx)&((1<<128)-1)).to_bytes(16,"little")
def _pad(x): return b"" if len(x)%16==0 else b"\x00"*(16-len(x)%16)
def aead_enc(key,nonce,aad,pt):
    ct=_xor(key,nonce,pt); otk=_block(key,nonce,0)[:32]
    mac=aad+_pad(aad)+ct+_pad(ct)+struct.pack("<QQ",len(aad),len(pt))
    return ct+_poly(otk,mac)
def aead_dec(key,nonce,aad,ct):
    if len(ct)<16: return None
    body,tag=ct[:-16],ct[-16:]; otk=_block(key,nonce,0)[:32]
    mac=aad+_pad(aad)+body+_pad(body)+struct.pack("<QQ",len(aad),len(body))
    if not hmac.compare_digest(_poly(otk,mac),tag): return None
    return _xor(key,nonce,body)
def _hkdf(salt,ikm,info,L=64):
    prk=hmac.new(salt,ikm,hashlib.sha256).digest(); out=b""; t=b""; i=1
    while len(out)<L: t=hmac.new(prk,t+info+bytes([i]),hashlib.sha256).digest(); out+=t; i+=1
    return out[:L]

MAX_FRAME=16*1024*1024        # largest encrypted message accepted (blocks are <= 2 MB)
HANDSHAKE_TIMEOUT=10          # seconds to complete the key exchange
IDLE_TIMEOUT=120              # drop a peer that sends nothing for this long

def _recvn(sock,n):
    b=bytearray(n); view=memoryview(b); got=0
    while got<n:
        r=sock.recv_into(view[got:], n-got)
        if not r: raise ConnectionError("dong")
        got+=r
    return bytes(b)

class SecureSocket:
    """Boc socket: bat tay ECDH epheral -> 2 khoa huong (gui/nhan). Khung: [4 byte len][ct+tag]."""
    def __init__(s, sock, initiator):
        s.sock=sock; s.sn=0; s.rn=0; s._slock=threading.Lock()
        sock.settimeout(HANDSHAKE_TIMEOUT)
        d=newkey(); Pt=pmul(d)
        mypub=(b"\x02" if Pt[1]%2==0 else b"\x03")+Pt[0].to_bytes(32,"big")
        sock.sendall(mypub)
        theirs=_recvn(sock,33)
        x=int.from_bytes(theirs[1:],"big")
        if theirs[0] not in (2,3) or x>=P: raise ConnectionError("bad handshake key")
        y=pow((pow(x,3,P)+7)%P,(P+1)//4,P)
        if (y*y-(pow(x,3,P)+7))%P!=0: raise ConnectionError("handshake key is not on secp256k1")
        if y%2!=(0 if theirs[0]==2 else 1): y=P-y
        shared=pmul(d,(x,y))[0].to_bytes(32,"big")
        sock.settimeout(IDLE_TIMEOUT)
        # khoa doi xung: sap xep pub theo thu tu co dinh de 2 ben ra cung khoa
        a,b=(mypub,theirs) if initiator else (theirs,mypub)
        k=_hkdf(b"BGC-v2-transport", shared, a+b, 64)
        # initiator gui bang k[:32], nhan bang k[32:]; responder nguoc lai
        s.ks, s.kr = (k[:32],k[32:]) if initiator else (k[32:],k[:32])
    def _nonce(s,n): return b"\x00"*4+n.to_bytes(8,"little")
    def send(s, data:bytes):
        if len(data)>MAX_FRAME: raise ValueError("message too large")
        with s._slock:                                  # 1 luong 1 luc: tranh dua nonce + ghi xen ke
            ct=aead_enc(s.ks, s._nonce(s.sn), b"", data); s.sn+=1
            s.sock.sendall(struct.pack("<I",len(ct))+ct)
    def recv(s)->bytes:
        ln=struct.unpack("<I",_recvn(s.sock,4))[0]
        if ln<16 or ln>MAX_FRAME+16: raise ConnectionError("frame size out of range")
        pt=aead_dec(s.kr, s._nonce(s.rn), b"", _recvn(s.sock,ln)); s.rn+=1
        if pt is None: raise ConnectionError("MAC sai - ban tin bi sua")
        return pt
    def close(s):
        try: s.sock.close()
        except OSError: pass

def self_test():
    import threading
    srv=socket.socket(); srv.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); srv.bind(("127.0.0.1",0)); srv.listen(1)
    port=srv.getsockname()[1]; box={}
    def server():
        c,_=srv.accept(); sec=SecureSocket(c, initiator=False)
        box["got"]=sec.recv(); sec.send(b"chao lai tu B (da ma hoa)")
    threading.Thread(target=server,daemon=True).start()
    c=socket.create_connection(("127.0.0.1",port)); sec=SecureSocket(c, initiator=True)
    sec.send("xin chao tu A (BGC P2P ma hoa)".encode())
    import time; time.sleep(0.2); reply=sec.recv()
    srv.close()
    return box.get("got"), reply

# ================= bgcfl_engine =================
#!/usr/bin/env python3
# =====================================================================
#  BGC-FL ENGINE v2 - consensus for the fair-launch BGC chain (Bitcoin-style).
#   - NO PREMINE: the genesis block pays 0; every coin is mined (permissionless PoW).
#   - subsidy(h)=50>>(h//210000) -> 21,000,000 cap, the same schedule as Bitcoin.
#   - DIFFICULTY: LWMA, re-computed EVERY block from the last 60 solve times
#     (reacts in minutes, not weeks, so an early miner cannot instamine for days).
#   - TIMESTAMPS: must be > median of the last 11 blocks and < now + 2h.
#   - COINBASE: matures after 100 blocks and commits to its height (unique txids).
#   - Fork-choice = MOST CHAINWORK; reorgs disconnect/reconnect blocks with undo data,
#     so adding a block costs O(block), not O(chain).
#   - Spends are signed with HASH-BASED post-quantum XMSS signatures (bigcoin_pq).
#   - Canonical JSON serialization; the block hash commits to every signature.
#  REGTEST params (tiny difficulty, short maturity) exist for tests and demos only.
# =====================================================================

def dsha(b): return hashlib.sha256(hashlib.sha256(b).digest()).digest()
def canon(obj): return json.dumps(obj, separators=(",",":"), ensure_ascii=True, sort_keys=True)

COIN=100_000_000
INITIAL=50*COIN
MAX_MONEY=21_000_000*COIN
GENESIS_PREV="00"*32
GENESIS_MSG="BGC: dong tien hau luong tu, sinh ra cho ky nguyen AI va robot."
GENESIS_TS=1760000000

MAX_BLOCK_BYTES=2_000_000      # serialized size limit of one block
MAX_BLOCK_TXS=5_000
MAX_TX_BYTES=500_000
MAX_TX_IN=64
MAX_TX_OUT=64
MAX_MEMO_BYTES=256
MAX_FUTURE_DRIFT=2*60*60       # a block may be at most 2h ahead of our clock (Bitcoin: same)
MTP_SPAN=11                    # median-time-past window (Bitcoin: same)
MAX_MEMPOOL_TXS=5_000
MAX_ORPHANS=200

ADDR_RE=re.compile(r"BGCQ[0-9a-f]{64}\Z")
HEX64_RE=re.compile(r"[0-9a-f]{64}\Z")

class Params:
    """Network parameters. MAIN is the real network; REGTEST is for tests/demos."""
    def __init__(s, name, magic, halving, interval, maturity, pow_limit, window):
        s.name=name; s.magic=magic; s.halving=halving; s.interval=interval
        s.maturity=maturity; s.pow_limit=pow_limit; s.window=window
    def subsidy(s, height):
        e=height//s.halving
        return (INITIAL>>e) if e<64 else 0
    def max_supply(s):
        t=0; e=0
        while e<64 and (INITIAL>>e)>0:
            t+=(INITIAL>>e)*s.halving; e+=1
        return t

MAIN   =Params("main",   "BGC2-main",    halving=210_000, interval=600, maturity=100, pow_limit=(1<<230)-1, window=60)
REGTEST=Params("regtest","BGC2-regtest", halving=150,     interval=10,  maturity=5,   pow_limit=(1<<252)-1, window=12)

# Main-network values, kept as module constants for the UI and older callers.
HALVING=MAIN.halving
BLOCK_INTERVAL=MAIN.interval
MATURITY=MAIN.maturity
POW_LIMIT=MAIN.pow_limit
GENESIS_TARGET=POW_LIMIT
MAX_SUPPLY=MAIN.max_supply()

def subsidy(height, p=MAIN): return p.subsidy(height)
def work_of(target): return (1<<256)//(target+1)   # chainwork of one block given its difficulty

# ---------------- strict validation helpers ----------------
class Invalid(Exception):
    """Malformed data or a consensus-rule violation."""

def _need(cond, msg):
    if not cond: raise Invalid(msg)
def _int(x, lo, hi, what):
    _need(type(x) is int and lo<=x<=hi, f"bad {what}"); return x
def _hex64(x, what):
    _need(type(x) is str and HEX64_RE.match(x) is not None, f"bad {what}"); return x
def _memo(x):
    _need(type(x) is str, "bad memo")
    try: n=len(x.encode("utf-8"))
    except UnicodeEncodeError: raise Invalid("bad memo")
    _need(n<=MAX_MEMO_BYTES, f"memo longer than {MAX_MEMO_BYTES} bytes"); return x
def valid_address(a): return type(a) is str and ADDR_RE.match(a) is not None

# ---------------- transactions & blocks ----------------
class TxOut:
    __slots__=("value","address","memo")
    def __init__(s,value,address,memo=""): s.value=value; s.address=address; s.memo=memo
    def to_d(s): return {"v":s.value,"a":s.address,"m":s.memo}
    @staticmethod
    def from_d(d):
        _need(type(d) is dict, "bad output")
        a=d.get("a"); _need(valid_address(a), "bad address")
        return TxOut(_int(d.get("v"),0,MAX_MONEY,"value"), a, _memo(d.get("m","")))

class TxIn:
    __slots__=("txid","vout","owner","sig")
    def __init__(s,txid,vout,owner="",sig=None): s.txid=txid; s.vout=vout; s.owner=owner; s.sig=sig
    def to_d(s): return {"t":s.txid,"o":s.vout,"ow":s.owner,"s":s.sig}
    @staticmethod
    def from_d(d):
        _need(type(d) is dict, "bad input")
        sig=d.get("s")
        _need(type(sig) is dict and set(sig)=={"i","w","p"}, "bad signature")
        return TxIn(_hex64(d.get("t"),"input txid"), _int(d.get("o"),0,MAX_TX_OUT-1,"input index"),
                    _hex64(d.get("ow"),"owner"), sig)

class Tx:
    __slots__=("vin","vout","coinbase","height")
    def __init__(s,vin,vout,coinbase=False,height=None):
        s.vin=vin; s.vout=vout; s.coinbase=coinbase; s.height=height
    def body(s):
        """What the txid and the signatures cover: everything except the signatures."""
        return canon(["BGC2-tx", "cb" if s.coinbase else "tx", s.height if s.coinbase else 0,
                      [[i.txid,i.vout] for i in s.vin],
                      [[o.value,o.address,o.memo] for o in s.vout]])
    def txid(s): return H(s.body().encode()).hex()
    def sighash(s, magic=MAIN.magic): return H(magic.encode()+b"|sighash|"+s.body().encode())
    def to_d(s):
        d={"i":[i.to_d() for i in s.vin],"o":[o.to_d() for o in s.vout],"cb":s.coinbase}
        if s.coinbase: d["h"]=s.height
        return d
    def wtxid(s): return H(canon(s.to_d()).encode()).hex()   # covers signatures too
    def size(s): return len(canon(s.to_d()))
    @staticmethod
    def from_d(d):
        _need(type(d) is dict, "bad tx")
        cb=d.get("cb",False); vin=d.get("i"); vout=d.get("o")
        _need(type(cb) is bool and type(vin) is list and type(vout) is list, "bad tx")
        _need(len(vin)<=MAX_TX_IN and 1<=len(vout)<=MAX_TX_OUT, "too many inputs/outputs")
        h=None
        if cb:
            _need(not vin, "coinbase has inputs"); h=_int(d.get("h"),0,1<<40,"coinbase height")
        else:
            _need(len(vin)>=1, "tx has no inputs")
        return Tx([TxIn.from_d(x) for x in vin],[TxOut.from_d(x) for x in vout],cb,h)

class Block:
    __slots__=("index","prev","txs","ts","nonce","target")
    def __init__(s,index,prev,txs,ts=None,nonce=0,target=POW_LIMIT):
        s.index=index; s.prev=prev; s.txs=txs; s.ts=int(time.time()) if ts is None else ts
        s.nonce=nonce; s.target=target
    def root(s): return H(b"".join(bytes.fromhex(t.wtxid()) for t in s.txs)).hex()
    def header_prefix(s): return f'["BGC2-hdr",{s.index},"{s.prev}","{s.root()}",{s.ts},"{s.target:064x}",'
    def header(s): return s.header_prefix()+f"{s.nonce}]"
    def hash(s): return dsha(s.header().encode()).hex()
    def pow_ok(s): return int.from_bytes(dsha(s.header().encode()),"big")<=s.target
    def to_d(s): return {"i":s.index,"p":s.prev,"tx":[t.to_d() for t in s.txs],"ts":s.ts,"n":s.nonce,"tg":s.target}
    def size(s): return len(canon(s.to_d()))
    @staticmethod
    def from_d(d):
        _need(type(d) is dict, "bad block")
        txs=d.get("tx")
        _need(type(txs) is list and 1<=len(txs)<=MAX_BLOCK_TXS, "bad block transactions")
        return Block(_int(d.get("i"),0,1<<40,"block height"), _hex64(d.get("p"),"prev hash"),
                     [Tx.from_d(x) for x in txs], _int(d.get("ts"),0,1<<40,"timestamp"),
                     _int(d.get("n"),0,1<<64,"nonce"), _int(d.get("tg"),1,(1<<256)-1,"target"))

def mine(block, max_tries=None):
    """Search nonces until the PoW meets the target. Returns the block, or None after max_tries."""
    base=hashlib.sha256(block.header_prefix().encode()); tgt=block.target
    n=block.nonce; end=None if max_tries is None else n+max_tries
    while end is None or n<end:
        h=base.copy(); h.update(b"%d]"%n)
        if int.from_bytes(hashlib.sha256(h.digest()).digest(),"big")<=tgt:
            block.nonce=n; return block
        n+=1
    block.nonce=n; return None

def make_genesis(p=MAIN):
    """Block 0, identical on every machine. Pays 0 BGC to an address nobody controls -> no premine.
    Like Bitcoin's genesis it is hard-coded (accepted by hash), not mined."""
    burn=addr_of(H(GENESIS_MSG.encode()))
    cb=Tx([],[TxOut(0, burn, GENESIS_MSG)],coinbase=True,height=0)
    return Block(0, GENESIS_PREV, [cb], ts=GENESIS_TS, nonce=0, target=p.pow_limit)

# ---------------- chain state ----------------
class _Entry:
    __slots__=("blk","hash","height","work","parent","invalid")
    def __init__(s,blk,hh,height,work,parent):
        s.blk=blk; s.hash=hh; s.height=height; s.work=work; s.parent=parent; s.invalid=False

class Chain:
    """Block tree + active chain + UTXO set + mempool. Every public method is thread-safe."""
    def __init__(s, datadir=None, params=MAIN):
        s.p=params; s.datadir=datadir; s.lock=threading.RLock()
        s.index={}; s.children={}; s.bad=set(); s.orphans={}
        s.active=[]; s.pos={}; s.utxo={}; s.undo={}           # utxo: (txid,vout)->(value,addr,cb_height|-1)
        s.mempool={}; s.mp_fee={}; s.mp_spent={}
        s._load_off=0
        g=make_genesis(params); gh=g.hash()
        e=_Entry(g, gh, 0, work_of(g.target), None)
        s.index[gh]=e; s.genesis_hash=gh
        ok,msg=s._connect(e)
        assert ok, msg

    # ----- read-only views -----
    def height(s):
        with s.lock: return len(s.active)                    # = height of the NEXT block
    def tip(s):
        with s.lock: return s.active[-1]
    @property
    def blocks(s):
        with s.lock: return [s.index[h].blk for h in s.active]
    def get_block(s, hh):
        with s.lock:
            e=s.index.get(hh); return e.blk if e else None
    def chainwork(s):
        with s.lock: return s.index[s.active[-1]].work
    def tip_info(s):
        with s.lock:
            e=s.index[s.active[-1]]; return e.height, e.work, e.hash
    def next_target(s):
        with s.lock: return s._target_after(s.index[s.active[-1]])
    def audit_supply(s):
        with s.lock: return sum(v for v,_,_ in s.utxo.values())
    def balance(s, a):
        with s.lock: return sum(v for v,o,_ in s.utxo.values() if o==a)
    def balances(s):
        with s.lock:
            out={}
            for v,a,_ in s.utxo.values(): out[a]=out.get(a,0)+v
            return out
    def spendable(s, addr):
        """[((txid,vout),value)] of addr: mature and not already spent by a pending tx."""
        with s.lock:
            h=len(s.active); out=[]
            for k,(val,owner,cbh) in s.utxo.items():
                if owner!=addr or k in s.mp_spent: continue
                if cbh>=0 and h-cbh<s.p.maturity: continue
                out.append((k,val))
            return out

    # ----- difficulty & time rules -----
    def _target_after(s, e):
        """LWMA difficulty for the child of entry e (zawy LWMA-1, integer math)."""
        p=s.p; n=min(p.window, e.height)
        if n<1: return p.pow_limit
        es=[]; x=e
        for _ in range(n+1): es.append(x); x=x.parent
        es.reverse()
        T=p.interval; prev_ts=es[0].blk.ts; weighted=0; sum_t=0
        for j in range(1,n+1):
            ts=es[j].blk.ts
            this_ts=ts if ts>prev_ts else prev_ts+1
            weighted+=min(6*T, this_ts-prev_ts)*j; prev_ts=this_ts
            sum_t+=es[j].blk.target
        k=n*(n+1)*T//2
        return max(1, min((sum_t//n)*weighted//k, p.pow_limit))
    def _mtp(s, e):
        ts=[]; x=e
        while x is not None and len(ts)<MTP_SPAN: ts.append(x.blk.ts); x=x.parent
        ts.sort(); return ts[len(ts)//2]

    # ----- validation -----
    def _check_tx_basic(s, tx):
        _need(type(tx.vout) is list and 1<=len(tx.vout)<=MAX_TX_OUT, "bad outputs")
        tot=0
        for o in tx.vout:
            _need(type(o.value) is int and 0<=o.value<=MAX_MONEY, "value out of range")
            _need(valid_address(o.address), "bad address"); _memo(o.memo)
            tot+=o.value
        _need(tot<=MAX_MONEY, "value out of range")
        if tx.coinbase:
            _need(not tx.vin, "coinbase has inputs")
            _need(type(tx.height) is int and tx.height>=0, "bad coinbase height")
        else:
            _need(type(tx.vin) is list and 1<=len(tx.vin)<=MAX_TX_IN, "bad inputs")
            seen=set()
            for i in tx.vin:
                _hex64(i.txid,"input txid"); _int(i.vout,0,MAX_TX_OUT-1,"input index"); _hex64(i.owner,"owner")
                k=(i.txid,i.vout); _need(k not in seen, "duplicate input"); seen.add(k)
        _need(tx.size()<=MAX_TX_BYTES, "tx too large")

    def _check_inputs(s, tx, height):
        """Inputs exist, are mature, belong to the signer and carry a valid XMSS signature. Returns the fee."""
        insum=0; sh=tx.sighash(s.p.magic)
        for i in tx.vin:
            k=(i.txid,i.vout)
            _need(k in s.utxo, "input missing/already spent")
            val,owner,cbh=s.utxo[k]
            _need(not (cbh>=0 and height-cbh<s.p.maturity), f"immature coinbase (needs {s.p.maturity} blocks)")
            _need(addr_of(bytes.fromhex(i.owner))==owner, "owner mismatch")
            _need(xmss_verify(bytes.fromhex(i.owner), sh, i.sig), "bad signature")
            insum+=val
        out=sum(o.value for o in tx.vout)
        _need(out<=insum, "coins created from nothing (out>in)")
        return insum-out

    def _check_basic(s, blk):
        """Context-free block checks (no chain state needed)."""
        _need(type(blk.txs) is list and 1<=len(blk.txs)<=MAX_BLOCK_TXS, "bad block transactions")
        _need(type(blk.target) is int and 1<=blk.target<=s.p.pow_limit, "target above the PoW limit")
        _need(type(blk.ts) is int and type(blk.index) is int and blk.index>=1, "bad block header")
        _hex64(blk.prev,"prev hash")
        _need(blk.pow_ok(), "bad PoW")
        _need(blk.txs[0].coinbase, "first tx must be the coinbase")
        _need(not any(t.coinbase for t in blk.txs[1:]), "more than one coinbase")
        seen=set()
        for tx in blk.txs:
            s._check_tx_basic(tx)
            t=tx.txid(); _need(t not in seen, "duplicate transaction"); seen.add(t)
        _need(blk.size()<=MAX_BLOCK_BYTES, "block too large")

    # ----- connect / disconnect (with undo data) -----
    def _connect(s, e):
        blk=e.blk; height=e.height; undo=[]
        try:
            fees=0
            for tx in blk.txs[1:]:
                fees+=s._check_inputs(tx, height)
                for i in tx.vin:
                    k=(i.txid,i.vout); undo.append((k, s.utxo.pop(k)))
                s._add_outputs(tx, -1, undo)          # later txs in this block may spend these
            cb=blk.txs[0]
            _need(cb.height==height, "coinbase height mismatch")
            allowed=s.p.subsidy(height)+fees; out=sum(o.value for o in cb.vout)
            _need(out<=allowed, f"coinbase {out}>{allowed} (inflation)")
            s._add_outputs(cb, height, undo)
        except Invalid as ex:
            s._rollback(undo); return False, str(ex)
        s.undo[e.hash]=undo; s.active.append(e.hash); s.pos[e.hash]=height
        return True, "ok"
    def _add_outputs(s, tx, cbh, undo):
        t=tx.txid()
        for vo,o in enumerate(tx.vout):
            if o.value>0:
                k=(t,vo); _need(k not in s.utxo, "duplicate txid")
                s.utxo[k]=(o.value,o.address,cbh); undo.append((k,None))
    def _rollback(s, undo):
        for k,prev in reversed(undo):
            if prev is None: s.utxo.pop(k,None)
            else: s.utxo[k]=prev
    def _disconnect_tip(s):
        hh=s.active.pop(); del s.pos[hh]
        s._rollback(s.undo.pop(hh)); return s.index[hh]

    def _mark_invalid(s, e):
        stack=[e.hash]
        while stack:
            hh=stack.pop(); x=s.index.get(hh)
            if x is None or x.invalid: continue
            x.invalid=True; s.bad.add(hh); stack.extend(s.children.get(hh,[]))

    def _activate(s, e):
        """Make e the active tip (it has more work). On an invalid block, keep the best valid chain."""
        path=[]; x=e
        while x.hash not in s.pos: path.append(x); x=x.parent
        fork=x; path.reverse()
        old_work=s.index[s.active[-1]].work
        old=[]                                        # disconnected, tip first
        while s.active[-1]!=fork.hash: old.append(s._disconnect_tip())
        for i,x in enumerate(path):
            ok,msg=s._connect(x)
            if ok: continue
            s._mark_invalid(x)
            new_work=path[i-1].work if i>0 else fork.work
            if new_work<=old_work:                    # go back to the old chain
                for _ in range(i): s._disconnect_tip()
                for y in reversed(old): s._connect(y)
                old=[]
            s._refresh_mempool(old)
            return False, msg
        s._refresh_mempool(old)
        return True, "ok"

    # ----- adding blocks -----
    def add_block(s, blk, persist=True):
        """Validate and store a block. Returns (ok, message, reorged).
        A message starting with 'orphan' means the parent is unknown: ask peers for more blocks."""
        with s.lock:
            try:
                hh=blk.hash()
                if hh in s.index: return False,"already have it",False
                if hh in s.bad: return False,"known invalid block",False
                s._check_basic(blk)
            except Invalid as ex: return False,str(ex),False
            except Exception: return False,"malformed block",False
            parent=s.index.get(blk.prev)
            if parent is None:
                if hh not in s.orphans:
                    if len(s.orphans)>=MAX_ORPHANS: s.orphans.pop(next(iter(s.orphans)))
                    s.orphans[hh]=blk
                return False,"orphan: parent unknown",False
            old_tip=s.active[-1]
            res=s._accept(hh, blk, parent, persist)
            if res[0]: s._process_orphans(hh, persist)
            return res[0], res[1], old_tip not in s.pos

    def _accept(s, hh, blk, parent, persist):
        if parent.invalid: s.bad.add(hh); return False,"parent is invalid"
        try:
            _need(blk.index==parent.height+1, "wrong height")
            _need(blk.target==s._target_after(parent), "wrong difficulty")
            _need(blk.ts>s._mtp(parent), "timestamp too old (<= median of the last 11 blocks)")
        except Invalid as ex:
            s.bad.add(hh); return False,str(ex)
        if blk.ts>time.time()+MAX_FUTURE_DRIFT:
            return False,"timestamp too far in the future"   # not marked bad: may become valid later
        e=_Entry(blk, hh, parent.height+1, parent.work+work_of(blk.target), parent)
        s.index[hh]=e; s.children.setdefault(parent.hash,[]).append(hh)
        if persist and s.datadir: s._save(blk)
        if e.work<=s.index[s.active[-1]].work: return True,"stored (side branch)"
        return s._activate(e)

    def _process_orphans(s, parent_hash, persist):
        queue=[parent_hash]
        while queue:
            ph=queue.pop()
            for oh,ob in [(h,b) for h,b in s.orphans.items() if b.prev==ph]:
                del s.orphans[oh]
                if oh in s.index: continue
                ok,_=s._accept(oh, ob, s.index[ph], persist)
                if ok: queue.append(oh)

    # ----- mempool -----
    def add_mempool(s, tx):
        with s.lock:
            try:
                _need(not tx.coinbase, "coinbase not allowed in the mempool")
                s._check_tx_basic(tx)
                t=tx.txid()
                if t in s.mempool: return False,"already in mempool"
                _need(len(s.mempool)<MAX_MEMPOOL_TXS, "mempool full")
                for i in tx.vin:
                    _need((i.txid,i.vout) not in s.mp_spent, "conflicts with a pending transaction (double-spend)")
                fee=s._check_inputs(tx, len(s.active))
            except Invalid as ex: return False,str(ex)
            except Exception: return False,"malformed transaction"
            s.mempool[t]=tx; s.mp_fee[t]=fee
            for i in tx.vin: s.mp_spent[(i.txid,i.vout)]=t
            return True,"ok"
    def _mp_remove(s, t):
        tx=s.mempool.pop(t); s.mp_fee.pop(t,None)
        for i in tx.vin: s.mp_spent.pop((i.txid,i.vout),None)
    def _refresh_mempool(s, old):
        if not old:                                   # plain extension: drop confirmed/conflicting txs
            for t,tx in list(s.mempool.items()):
                if any((i.txid,i.vout) not in s.utxo for i in tx.vin): s._mp_remove(t)
            return
        cands=[tx for e in reversed(old) for tx in e.blk.txs[1:]]+list(s.mempool.values())
        s.mempool={}; s.mp_fee={}; s.mp_spent={}
        for tx in cands:
            if len(s.mempool)>=MAX_MEMPOOL_TXS: break
            s.add_mempool(tx)

    # ----- mining -----
    def block_template(s, addr, memo=""):
        """A ready-to-mine block on the current tip paying subsidy+fees to addr."""
        with s.lock:
            parent=s.index[s.active[-1]]; height=parent.height+1
            ts=max(int(time.time()), s._mtp(parent)+1)
            txs=[]; fees=0; size=2_000
            for t,tx in s.mempool.items():
                sz=tx.size()
                if size+sz>MAX_BLOCK_BYTES or len(txs)+1>=MAX_BLOCK_TXS: continue
                txs.append(tx); fees+=s.mp_fee[t]; size+=sz
            cb=Tx([],[TxOut(s.p.subsidy(height)+fees, addr, memo)],coinbase=True,height=height)
            return Block(height, parent.hash, [cb]+txs, ts=ts, target=s._target_after(parent))

    def make_block(s, addr, txs=(), ts=None, parent=None, memo="", extra_reward=0):
        """Mine a block on `parent` (default: the tip) that follows the header rules.
        For tests, demos and simulations; fees are not added (pass extra_reward)."""
        with s.lock:
            e=s.index[parent or s.active[-1]]; height=e.height+1
            ts=e.blk.ts+s.p.interval if ts is None else ts
            target=s._target_after(e)
        cb=Tx([],[TxOut(s.p.subsidy(height)+extra_reward, addr, memo or f"cb h{height}")],coinbase=True,height=height)
        return mine(Block(height, e.hash, [cb]+list(txs), ts=ts, target=target))

    # ----- sync helpers -----
    def locator(s):
        """Hashes from the tip back to genesis, dense at first then exponentially sparse."""
        with s.lock:
            loc=[]; i=len(s.active)-1; step=1
            while i>0:
                loc.append(s.active[i])
                if len(loc)>=10: step*=2
                i-=step
            loc.append(s.active[0]); return loc
    def blocks_after(s, loc, max_count=500, max_bytes=4_000_000):
        """Active-chain blocks (as dicts) after the first locator hash we know."""
        with s.lock:
            start=1
            for hh in loc:
                if type(hh) is str and hh in s.pos: start=s.pos[hh]+1; break
            out=[]; size=0
            for hh in s.active[start:start+max_count]:
                d=s.index[hh].blk.to_d(); sz=len(canon(d))
                if out and size+sz>max_bytes: break
                out.append(d); size+=sz
            return out

    # ----- persistence (append-only; only blocks with valid headers are written) -----
    def _path(s): return os.path.join(s.datadir, f"blocks-{s.p.name}.jsonl")
    def _save(s, blk):
        os.makedirs(s.datadir, exist_ok=True)
        with open(s._path(),"a",encoding="utf-8",newline="\n") as f: f.write(canon(blk.to_d())+"\n")
    def load(s):
        """Read blocks appended to the data file since the last call (full re-validation)."""
        if not s.datadir or not os.path.exists(s._path()): return 0
        with open(s._path(),"rb") as f:
            f.seek(s._load_off); data=f.read()
        end=data.rfind(b"\n")
        if end<0: return 0
        s._load_off+=end+1; n=0
        for line in data[:end].split(b"\n"):
            if not line.strip(): continue
            try: blk=Block.from_d(json.loads(line))
            except Exception: continue                # torn or corrupt line (e.g. power loss)
            ok,_,_=s.add_block(blk, persist=False)
            if ok: n+=1
        return n

# ================= bgcfl_wallet =================
#!/usr/bin/env python3
# =====================================================================
#  BGC-FL WALLET - a POST-QUANTUM wallet for the fair-launch chain (bgcfl_engine).
#  - Signatures are HASH-BASED (XMSS) -> a quantum computer cannot forge them.
#  - XMSS is a "one-time, stateful" scheme: a leaf must NEVER sign twice. The wallet
#    reserves the leaf (writes next+1 to disk) BEFORE signing, so a crash or restart
#    can only skip a leaf, never reuse one.
#  - NEVER restore an old copy of the wallet file and keep using it: the old 'next'
#    would reuse leaves. After restoring a backup, move the coins to a NEW wallet.
#  - Fully compatible with bgcfl_engine (COIN, Tx/TxIn/TxOut, coinbase maturity).
#  Standalone: python bgcfl_wallet.py <wallet_file.json>   (create / show the address)
# =====================================================================

LOW_SIGNATURES=100      # warn the user when fewer signatures than this are left

def parse_amount(x):
    """'1.5' / 1.5 -> 150000000 base units. Exact decimal math (no float rounding)."""
    try: d=Decimal(str(x).strip())
    except InvalidOperation: raise ValueError("invalid amount")
    if not d.is_finite() or d<=0: raise ValueError("amount must be > 0")
    units=d*COIN
    if units!=units.to_integral_value(): raise ValueError("at most 8 decimal places")
    units=int(units)
    if units>MAX_MONEY: raise ValueError("amount too large")
    return units

class Wallet:
    """A durable wallet: stores the master seed + the leaf index 'next'. h=12 -> 4096 signatures/wallet."""
    def __init__(s, path, h=12):
        s.path=path
        if os.path.exists(path):
            with open(path) as f: d=json.load(f)
            s.key=XmssKey(master=bytes.fromhex(d["master"]), h=d["h"]); s.key.next=d["next"]
        else:
            s.key=XmssKey(h=h); s._flush()
    def _flush(s):
        tmp=s.path+".tmp"
        with open(tmp,"w") as f:
            json.dump({"master":s.key.master.hex(),"h":s.key.h,"next":s.key.next}, f)
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp, s.path)                 # atomic replace (survives power loss)
        try: os.chmod(s.path, 0o600)            # owner-only on Linux/macOS (no-op on Windows)
        except OSError: pass
    @property
    def address(s): return addr_of(s.key.root)
    def remaining(s): return (1<<s.key.h)-s.key.next   # signatures left
    def sign(s, sighash):
        k=s.key.next
        if k>=(1<<s.key.h):
            raise RuntimeError("wallet has no signatures left: create a new wallet and move the coins")
        s.key.next=k+1; s._flush()              # reserve the leaf on disk FIRST
        return s.key.sign_at(k, sighash)
    def spendable(s, chain):
        """My UTXOs that are mature and not already used by one of my pending transactions."""
        return chain.spendable(s.address)
    def balance(s, chain):
        return chain.balance(s.address)/COIN
    def balance_spendable(s, chain):
        return sum(val for _,val in s.spendable(chain))/COIN
    def send(s, chain, to_addr, amount_bgc, memo="", fee_bgc=0):
        if not valid_address(to_addr): raise ValueError("invalid address (expected BGCQ + 64 hex characters)")
        if len(memo.encode("utf-8"))>MAX_MEMO_BYTES: raise ValueError(f"memo longer than {MAX_MEMO_BYTES} bytes")
        amt=parse_amount(amount_bgc); fee=parse_amount(fee_bgc) if fee_bgc else 0
        me=s.address; picks=[]; got=0
        for k,val in sorted(s.spendable(chain), key=lambda kv:-kv[1]):   # largest first -> fewer inputs
            picks.append(k); got+=val
            if got>=amt+fee or len(picks)>=64: break
        if got<amt+fee:
            raise RuntimeError(f"not enough mature BGC (need {(amt+fee)/COIN:g}, have {got/COIN:g})")
        vin=[TxIn(t,v,s.key.root.hex()) for t,v in picks]
        vout=[TxOut(amt, to_addr, memo)]
        if got-amt-fee>0: vout.append(TxOut(got-amt-fee, me, "change"))
        tx=Tx(vin, vout)
        sig=s.sign(tx.sighash(chain.p.magic))  # one signature covers every input (same key, same message)
        for i in tx.vin: i.sig=sig
        return tx

def main():
    path=sys.argv[1] if len(sys.argv)>1 else "my_bgc_wallet.json"
    w=Wallet(path)
    print(f"Wallet: {path}")
    print(f"Address (receive BGC): {w.address}")
    print(f"Signatures left      : {w.remaining():,} (XMSS h={w.key.h})")
    print("Give this address to others to receive BGC. KEEP the wallet file safe - losing it loses the coins.")
    print("Never keep using an OLD copy of this file (it would reuse one-time keys).")
    return 0

# ================= bgcfl_genesis =================
#!/usr/bin/env python3
# =====================================================================
#  BGC-FL GENESIS - shows the CANONICAL block 0 (shared by EVERY machine).
#  Like Bitcoin: everyone must start from the SAME genesis block to be on the same
#  network. The block is hard-coded in bgcfl_engine.make_genesis(), so no file needs to
#  be shared. The genesis coinbase pays 0 BGC to an address whose key nobody knows
#  -> NO premine, nobody gets a head start.
#  Usage: python bgcfl_genesis.py [--regtest] [out.json]   -> prints (and optionally saves) block 0
# =====================================================================

def build(params=MAIN):
    return make_genesis(params)

# ================= run_miner =================
#!/usr/bin/env python3
# =====================================================================
#  RUN_MINER - mine BGC easily, Bitcoin-style (anyone can mine).
#
#  Like Bitcoin:
#    - Fair launch, NO premine: every coin is mined (PoW).
#    - Permissionless: no approval needed, just plug in a machine and mine.
#    - Halving + per-block difficulty adjustment + coinbase maturity + fork-choice by chainwork.
#  Unlike Bitcoin (stronger):
#    - HASH-BASED signatures (XMSS) -> QUANTUM-RESISTANT.
#    - P2P MA HOA dau-cuoi (ECDH + ChaCha20-Poly1305).
#
#  Dung (de nhat):
#    python run_miner.py                         # tao vi, dao solo, cong 9333
#    python run_miner.py --peers IP:9333         # tham gia mang qua 1 seed
#    python run_miner.py --name An --port 9333 --peers a.b.c.d:9333,e.f.g.h:9333
#    python run_miner.py --regtest               # mang THU NGHIEM rieng (do kho rat thap)
#
#  Khi chay: genesis co san trong code, noi seed, TU DAO vao vi cua ban, in trang thai.
#  Lenh go vao: bal | addr | send <dia_chi> <so_BGC> [memo] | peers | stop | mine | quit
# =====================================================================

HERE=os.path.dirname(os.path.abspath(__file__))
MSG="BGC: dong tien hau luong tu, sinh ra cho ky nguyen AI va robot."
PROTO=2               # phien ban giao thuc P2P
MAX_PEERS=32          # so ket noi toi da
TIP_EVERY=15          # giay giua 2 lan bao dinh chuoi
MINE_BATCH=20_000     # so nonce moi dot (roi kiem tra khoi moi)
TEMPLATE_AGE=30       # giay: lam moi khoi mau (giao dich moi + timestamp)

def load_genesis(chain, gpath=None):
    """Genesis nay nam san trong code (giong nhau tren moi may) - chi in ra de kiem tra."""
    print(f"[genesis] khoi 0 ({chain.p.name}): hash={chain.genesis_hash[:16]}..")

# ---------- mang P2P ma hoa ----------
class Peer:
    def __init__(s,sec,addr): s.sec=sec; s.addr=addr; s.lock=threading.Lock(); s.ready=False; s.work=0; s.asked=0.0
    def send(s,msg):
        try:
            data=json.dumps(msg,separators=(",",":")).encode()
            with s.lock: s.sec.send(data)
            return True
        except Exception:
            s.sec.close(); return False

class MinerNode:
    def __init__(s, name, wallet, datadir, port, params=MAIN, bind="0.0.0.0"):
        s.name=name; s.w=wallet; s.addr=wallet.address
        s.chain=Chain(datadir=datadir, params=params); s.chain.load()
        s.peers=[]; s.out=set(); s.lock=threading.Lock()
        s.stop=False; s.mining=False; s._miner=None; s.hashrate=0.0
        s.events=[]                          # nhat ky su kien (cho giao dien app doc)
        s.srv=socket.socket(); s.srv.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        s.srv.bind((bind,port)); s.port=s.srv.getsockname()[1]; s.srv.listen(16)
        threading.Thread(target=s._accept,daemon=True).start()
        threading.Thread(target=s._ticker,daemon=True).start()
    # --- ket noi ---
    def _accept(s):
        while not s.stop:
            try: c,_=s.srv.accept()
            except OSError: break
            threading.Thread(target=s._serve,args=(c,False,None),daemon=True).start()
    def connect(s,host,port):
        tgt=(host,int(port))
        with s.lock:
            if tgt in s.out or len(s.peers)>=MAX_PEERS: return
            s.out.add(tgt)
        try:
            c=socket.create_connection(tgt,timeout=4)
            threading.Thread(target=s._serve,args=(c,True,tgt),daemon=True).start()
        except OSError:
            with s.lock: s.out.discard(tgt)
    def _serve(s,sock,initiator,tgt):
        p=None
        try:
            sec=SecureSocket(sock,initiator=initiator)
            p=Peer(sec, tgt)
            with s.lock:
                if len(s.peers)>=MAX_PEERS: return
                s.peers.append(p)
            h,work,tip=s.chain.tip_info()
            p.send({"t":"version","v":PROTO,"net":s.chain.p.magic,"g":s.chain.genesis_hash,"h":h,"w":hex(work),"tip":tip})
            while not s.stop:
                msg=json.loads(sec.recv())
                if type(msg) is not dict or not s._on(p,msg): break   # du lieu xau -> ngat ket noi
        except Exception: pass
        finally:
            try: sock.close()
            except OSError: pass
            with s.lock:
                if p in s.peers: s.peers.remove(p)
                if tgt: s.out.discard(tgt)
    def _ticker(s):
        while not s.stop:
            time.sleep(TIP_EVERY); s._bcast(s._tip_msg())
    def _tip_msg(s):
        h,work,tip=s.chain.tip_info(); return {"t":"tip","h":h,"w":hex(work),"tip":tip}
    def _bcast(s,msg,skip=None):
        with s.lock: ps=[p for p in s.peers if p.ready and p is not skip]
        for p in ps: p.send(msg)
    def _log(s, kind, **kw):                 # su kien co cau truc (app tu dich ngon ngu)
        ev={"t":time.time(),"kind":kind}; ev.update(kw)
        with s.lock: s.events=(s.events+[ev])[-200:]
    # --- dong bo ---
    def _ask(s,p,soon=False):
        """Xin khoi tiep theo bang 'locator' (danh sach hash cua minh), co gioi han tan suat."""
        if time.time()-p.asked<(2 if soon else 10): return
        p.asked=time.time(); p.send({"t":"getblocks","loc":s.chain.locator()})
    def _note_tip(s,p,msg):
        try: p.work=int(msg.get("w"),16)
        except (TypeError,ValueError): return False
        if p.work>s.chain.chainwork(): s._ask(p)
        return True
    def _add(s,bd,p):
        """True: khoi moi duoc nhan | False: vo hai (trung/mo coi/tuong lai) | None: khoi SAI luat."""
        try: blk=Block.from_d(bd)
        except Exception: return None
        ok,m,_=s.chain.add_block(blk)
        if ok: return True
        if m.startswith("orphan"): s._ask(p,soon=True); return False
        if m=="already have it" or "future" in m: return False
        return None
    def _on(s,p,msg):
        t=msg.get("t")
        if t=="version":
            if msg.get("net")!=s.chain.p.magic or msg.get("g")!=s.chain.genesis_hash: return False  # mang khac
            p.ready=True
            with s.chain.lock: txs=[tx.to_d() for tx in list(s.chain.mempool.values())[:500]]
            if txs: p.send({"t":"txs","x":txs})
            return s._note_tip(p,msg)
        if not p.ready: return False
        if t=="tip": return s._note_tip(p,msg)
        if t=="getblocks":
            loc=msg.get("loc")
            if type(loc) is not list: return False
            p.send({"t":"blocks","b":s.chain.blocks_after(loc[:64])})
        elif t=="blocks":
            bl=msg.get("b")
            if type(bl) is not list: return False
            p.asked=0.0; progressed=False
            for bd in bl:
                r=s._add(bd,p)
                if r is None: return False
                progressed|=r
            if progressed:
                s._bcast(s._tip_msg(),skip=p)
                if p.work>s.chain.chainwork(): s._ask(p,soon=True)
        elif t=="block":
            r=s._add(msg.get("b"),p)
            if r is None: return False
            if r: s._bcast(msg,skip=p)
        elif t in ("tx","txs"):
            items=[msg.get("x")] if t=="tx" else msg.get("x")
            if type(items) is not list: return False
            for x in items[:500]:
                try: tx=Tx.from_d(x)
                except Exception: return False
                ok,_=s.chain.add_mempool(tx)
                if ok: s._bcast({"t":"tx","x":x},skip=p)
        return True
    def submit_tx(s, tx):
        ok,m=s.chain.add_mempool(tx)
        if ok: s._bcast({"t":"tx","x":tx.to_d()})
        return ok,m
    # --- dao (PoW) ---
    def start_mining(s):
        s.mining=True
        if s._miner is None or not s._miner.is_alive():
            s._miner=threading.Thread(target=s._mine,daemon=True); s._miner.start()
    def stop_mining(s, wait=False):
        """Dung dao. wait=True: cho luong dao ket thuc han (khoi vua tim duoc van duoc phat)."""
        s.mining=False
        if wait and s._miner is not None: s._miner.join(10)
    def _mine(s):
        memo=f"BGC {s.name}"[:64]
        while s.mining and not s.stop:
            blk=s.chain.block_template(s.addr, memo); t0=time.time(); tries=0; found=None
            while s.mining and not s.stop and s.chain.tip()==blk.prev and time.time()-t0<TEMPLATE_AGE:
                found=mine(blk, MINE_BATCH); tries+=MINE_BATCH
                if found: break
            dt=time.time()-t0
            if dt>0.5: s.hashrate=tries/dt
            if not found: continue
            ok,_,_=s.chain.add_block(found)
            if ok and s.chain.tip()==found.hash():
                s._bcast({"t":"block","b":found.to_d()})
                reward=found.txs[0].vout[0].value/COIN
                s._log("mined", h=found.index, reward=reward, tip=found.hash()[:12])
                print(f"  ⛏  DAO DUOC khoi #{found.index}  (+{reward:g} BGC)  tip={found.hash()[:12]}..")
    def close(s):
        s.stop=True; s.mining=False
        try: s.srv.close()
        except OSError: pass
        with s.lock: ps=list(s.peers)
        for p in ps: p.sec.close()

def banner(name, port, addr, net):
    print("="*72)
    print(f" ⬡  {MSG}")
    print("="*72)
    print(" DAO BGC - fair-launch, khang luong tu, P2P ma hoa (giong BTC, manh hon)")
    print(f"   mang    : {net}")
    print(f"   tho dao : {name}   |   cong : {port}")
    print(f"   vi cua ban (nhan BGC): {addr}")
    print("="*72)

def parse_peers(text):
    return [p.strip() for p in text.split(",") if p.strip() and "<" not in p]

def start_reconnector(node, peers, every=10):
    def loop():
        while not node.stop:
            for p in peers:
                try: host,port=p.rsplit(":",1); node.connect(host,int(port))
                except Exception: pass
            time.sleep(every)
    threading.Thread(target=loop,daemon=True).start()

# ================= bgc_app =================
#!/usr/bin/env python3
# =====================================================================
#  BGC-APP - a "one-click" GUI to mine BGC (runs in the browser).
#  - Runs a MinerNode in the background and opens a control page in the browser.
#  - DEFAULT LANGUAGE GERMAN; with a language picker (Deutsch / English / Tieng Viet).
#  - Shows: status, balance, address, start/stop mining, send BGC, add seed, event log, history.
#  Usage: python bgc_app.py                          (opens http://localhost:7000)
#         python bgc_app.py --peers IP:9333          (join a network)
#         python bgc_app.py --web-port 7000 --port 9333 --name An
# =====================================================================
try:
    import qrcode, qrcode.image.svg               # tao ma QR cho dia chi (tuy chon)
    HAS_QR=True
except Exception:
    HAS_QR=False

# Khi dong goi thanh .exe (PyInstaller one-file): dat vi/du lieu/genesis CANH BEN
# file .exe (de nguoi dung tim/sao luu vi), khong phai trong thu muc giai nen tam.
if getattr(sys, "frozen", False):
    HERE=os.path.dirname(sys.executable)
else:
    HERE=os.path.dirname(os.path.abspath(__file__))
NODE=None; PEERS_CFG=[]
# Secret for this run: only the page we serve knows it, so other websites open in the same
# browser cannot call /api/send (CSRF). The Host check below blocks DNS-rebinding.
TOKEN=secrets.token_urlsafe(32); WEB_PORT=7000

# ---------------------------------------------------------------- trang HTML
PAGE=r"""<!doctype html><html lang="de" data-theme="dark"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Cpolygon points='32,3 57,17.5 57,46.5 32,61 7,46.5 7,17.5' fill='%235aa0ff'/%3E%3Cpolygon points='32,12 49,22 49,42 32,52 15,42 15,22' fill='%23141a24'/%3E%3Ctext x='32' y='43' font-family='Arial,sans-serif' font-weight='bold' font-size='30' fill='%235aa0ff' text-anchor='middle'%3EB%3C/text%3E%3Ccircle cx='49' cy='18' r='5' fill='%2349d17a'/%3E%3C/svg%3E">
<title>BGC Miner</title><style>
:root{--bg:#0b0e14;--card:#141a24;--line:#263040;--mut:#8aa0b4;--ok:#49d17a;--ac:#5aa0ff;--txt:#dfe8f0;--warn:#ffb454}
@media(prefers-color-scheme:light){:root:not([data-theme=dark]){--bg:#f3f6fa;--card:#fff;--line:#d7dee8;--mut:#5a6b7b;--ok:#128a43;--ac:#1763d6;--txt:#1b2430}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:15px/1.55 system-ui,Segoe UI,Roboto,sans-serif;padding:16px;max-width:860px;margin:0 auto}
.top{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
.msg{font-size:17px;font-weight:600;color:var(--ac);margin:4px 0}
select,input,button{font:inherit;color:var(--txt);background:var(--card);border:1px solid var(--line);border-radius:9px;padding:8px 10px}
button{cursor:pointer;background:var(--ac);color:#fff;border:0;font-weight:600}
button.sec{background:var(--card);color:var(--txt);border:1px solid var(--line)}
button:disabled{opacity:.5;cursor:default}
.sub{color:var(--mut);font-size:13px;margin:2px 0 14px}
.k{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}
.cell{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;min-width:135px;flex:1}
.cell .n{font-size:21px;font-weight:700} .cell .l{color:var(--mut);font-size:12px}
.bar{height:7px;background:var(--line);border-radius:6px;overflow:hidden;margin-top:6px}.bar>i{display:block;height:100%;background:var(--ok);width:0}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin:12px 0}
.card h3{margin:0 0 10px;font-size:14px}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.row input{flex:1;min-width:120px}
code{background:rgba(120,140,170,.18);padding:2px 6px;border-radius:5px;font-size:12px;word-break:break-all}
.addr{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:var(--mut);margin-right:6px}
.dot.on{background:var(--ok)} .pill{font-size:12px;color:var(--mut)}
#log{max-height:200px;overflow:auto;font-size:13px}
#log div{padding:3px 0;border-bottom:1px solid var(--line)}
#hist{max-height:260px;overflow:auto;font-size:13px}
#hist .it{display:flex;justify-content:space-between;gap:10px;padding:7px 0;border-bottom:1px solid var(--line)}
#hist .l2{color:var(--mut);font-size:12px}
#hist .amt{font-weight:700;white-space:nowrap}
#hist .pos{color:var(--ok)} #hist .neg{color:var(--warn)}
.note{color:var(--warn);font-size:12px;margin-top:8px}
.toast{position:fixed;bottom:16px;left:50%;transform:translateX(-50%);background:var(--card);border:1px solid var(--line);padding:10px 16px;border-radius:10px;opacity:0;transition:.3s;pointer-events:none}
.toast.show{opacity:1}
</style></head><body>
<div class="top">
  <div><p class="msg" id="tagline">⬡</p><p class="sub" id="subtitle"></p></div>
  <div><label class="pill" id="lang_l"></label>
    <select id="lang"><option value="de">Deutsch</option><option value="en">English</option><option value="vi">Tiếng Việt</option></select>
  </div>
</div>

<div class="k">
  <div class="cell"><div class="n" id="s_h">0</div><div class="l" id="l_h"></div></div>
  <div class="cell"><div class="n" id="s_peers">0</div><div class="l" id="l_peers"></div></div>
  <div class="cell"><div class="n" id="s_bal">0</div><div class="l" id="l_bal"></div></div>
  <div class="cell"><div class="n" id="s_reward">0</div><div class="l" id="l_reward"></div></div>
  <div class="cell"><div class="n" id="s_supply">0</div><div class="l" id="l_supply"></div><div class="bar"><i id="s_bar"></i></div></div>
</div>

<div class="card">
  <h3 id="h_mine"></h3>
  <div class="row">
    <span><span class="dot" id="mdot"></span><span class="pill" id="mstat"></span></span>
    <button id="btn_mine"></button>
  </div>
  <div class="note" id="mnote"></div>
</div>

<div class="card">
  <h3 id="h_wallet"></h3>
  <div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap">
    <div style="background:#fff;padding:8px;border-radius:10px;line-height:0" id="qrbox">
      <img id="qr" width="132" height="132" alt="QR">
    </div>
    <div style="flex:1;min-width:200px">
      <p class="sub" id="recv_l" style="margin:0 0 6px"></p>
      <div class="addr"><code id="addr"></code><button class="sec" id="btn_copy"></button></div>
      <p class="sub" id="wallet_hint"></p>
    </div>
  </div>
</div>

<div class="card">
  <h3 id="h_send"></h3>
  <div class="row">
    <input id="to" placeholder="BGCQ...">
    <input id="amt" type="number" step="0.0001" style="max-width:130px" placeholder="0.00">
    <input id="memo" placeholder="" style="max-width:150px">
    <button id="btn_send"></button>
  </div>
  <p class="sub" id="send_hint"></p>
</div>

<div class="card">
  <h3 id="h_net"></h3>
  <div class="row">
    <input id="peer" placeholder="IP:9333">
    <button class="sec" id="btn_connect"></button>
  </div>
  <p class="sub" id="net_hint"></p>
</div>

<div class="card"><h3 id="h_hist"></h3><div id="hist"></div></div>
<div class="card"><h3 id="h_log"></h3><div id="log"></div></div>
<p class="sub" id="footer"></p>
<div class="toast" id="toast"></div>

<script>
const T={
 de:{tag:"BGC: Die post-quanten Währung, geboren für das Zeitalter von KI und Robotern.",
  subtitle:"Fair-Launch · quantensichere Signaturen (XMSS) · verschlüsseltes P2P · wie Bitcoin, nur stärker",
  lang:"Sprache", l_h:"Höhe (Blöcke)", l_peers:"Verbundene Knoten", l_bal:"Dein Guthaben (BGC)",
  l_reward:"Aktuelle Belohnung", l_supply:"Ausgegeben / Max",
  h_mine:"Schürfen (Mining)", mine_on:"Mining läuft", mine_off:"Mining gestoppt",
  btn_start:"Mining starten", btn_stop:"Mining stoppen",
  mnote:"Frisch geschürfte Coins brauchen einige Blöcke bis sie ausgegeben werden können (Coinbase-Reife).",
  h_wallet:"Deine Brieftasche", recv_l:"Diese Adresse scannen, um dir BGC zu senden:", copy:"Adresse kopieren", copied:"Adresse kopiert",
  wallet_hint:"Gib diese Adresse weiter, um BGC zu empfangen. Bewahre die Wallet-Datei sicher auf — Verlust = Coins verloren.",
  h_send:"BGC senden", btn_send:"Senden", memo:"Notiz",
  send_hint:"Signiert quantensicher (XMSS) und über das Netz verbreitet. Nur ausgereifte Coins sind verfügbar.",
  spendable:"verfügbar", remaining:"Signaturen übrig",
  h_net:"Dem Netzwerk beitreten", btn_connect:"Verbinden",
  net_hint:"Gib die Adresse eines Seed-Knotens ein (IP:Port), um dem Netzwerk beizutreten. Alle Knoten müssen dieselbe genesis-Datei verwenden.",
  h_log:"Ereignisse", h_hist:"Verlauf (Transaktionen)", hist_mined:"Geschürft", hist_sent:"Gesendet an", hist_received:"Erhalten von", hist_empty:"Noch keine Transaktionen", footer:"Prototyp zum Lernen/Demo — vor echtem Einsatz Parameter anpassen und Sicherheitsaudit durchführen.",
  ev_mined:"Block #{h} geschürft (+{r} BGC)", ev_start:"Mining gestartet", ev_stop:"Mining gestoppt",
  ev_send:"{a} BGC gesendet an {to}…", ev_recv:"Guthaben aktualisiert", err:"Fehler"},
 en:{tag:"BGC: The post-quantum currency, born for the age of AI and robots.",
  subtitle:"Fair launch · quantum-safe signatures (XMSS) · encrypted P2P · like Bitcoin, but stronger",
  lang:"Language", l_h:"Height (blocks)", l_peers:"Connected peers", l_bal:"Your balance (BGC)",
  l_reward:"Current reward", l_supply:"Issued / Max",
  h_mine:"Mining", mine_on:"Mining running", mine_off:"Mining stopped",
  btn_start:"Start mining", btn_stop:"Stop mining",
  mnote:"Freshly mined coins need a few blocks before they can be spent (coinbase maturity).",
  h_wallet:"Your wallet", recv_l:"Scan this address to send yourself BGC:", copy:"Copy address", copied:"Address copied",
  wallet_hint:"Share this address to receive BGC. Keep the wallet file safe — losing it means losing your coins.",
  h_send:"Send BGC", btn_send:"Send", memo:"Memo",
  send_hint:"Signed quantum-safe (XMSS) and broadcast to the network. Only matured coins are spendable.",
  spendable:"spendable", remaining:"signatures left",
  h_net:"Join the network", btn_connect:"Connect",
  net_hint:"Enter a seed node address (IP:port) to join the network. All nodes must use the same genesis file.",
  h_log:"Events", h_hist:"History (transactions)", hist_mined:"Mined", hist_sent:"Sent to", hist_received:"Received from", hist_empty:"No transactions yet", footer:"Learning/demo prototype — tune parameters and get a security audit before real use.",
  ev_mined:"Mined block #{h} (+{r} BGC)", ev_start:"Mining started", ev_stop:"Mining stopped",
  ev_send:"Sent {a} BGC to {to}…", ev_recv:"Balance updated", err:"Error"},
 vi:{tag:"BGC: đồng tiền hậu lượng tử, sinh ra cho kỷ nguyên AI và robot.",
  subtitle:"Fair-launch · chữ ký kháng lượng tử (XMSS) · P2P mã hóa · giống Bitcoin, mạnh hơn",
  lang:"Ngôn ngữ", l_h:"Chiều cao (số khối)", l_peers:"Số máy kết nối", l_bal:"Số dư của bạn (BGC)",
  l_reward:"Phần thưởng hiện tại", l_supply:"Đã phát hành / Tối đa",
  h_mine:"Đào (Mining)", mine_on:"Đang đào", mine_off:"Đã dừng đào",
  btn_start:"Bắt đầu đào", btn_stop:"Dừng đào",
  mnote:"Coin vừa đào cần chờ vài khối mới tiêu được (coinbase maturity).",
  h_wallet:"Ví của bạn", recv_l:"Quét địa chỉ này để gửi BGC cho bạn:", copy:"Chép địa chỉ", copied:"Đã chép địa chỉ",
  wallet_hint:"Đưa địa chỉ này để nhận BGC. Giữ kỹ file ví — mất là mất coin.",
  h_send:"Gửi BGC", btn_send:"Gửi", memo:"Ghi chú",
  send_hint:"Ký kháng lượng tử (XMSS) rồi phát lên mạng. Chỉ coin đã trưởng thành mới tiêu được.",
  spendable:"tiêu được", remaining:"chữ ký còn lại",
  h_net:"Tham gia mạng", btn_connect:"Kết nối",
  net_hint:"Nhập địa chỉ seed node (IP:cổng) để tham gia mạng. Mọi máy phải dùng cùng file genesis.",
  h_log:"Nhật ký", h_hist:"Lịch sử giao dịch", hist_mined:"Đào được", hist_sent:"Đã gửi tới", hist_received:"Đã nhận từ", hist_empty:"Chưa có giao dịch", footer:"Bản nguyên mẫu học/demo — chỉnh tham số và kiểm toán an ninh trước khi dùng thật.",
  ev_mined:"Đào được khối #{h} (+{r} BGC)", ev_start:"Bắt đầu đào", ev_stop:"Dừng đào",
  ev_send:"Đã gửi {a} BGC tới {to}…", ev_recv:"Cập nhật số dư", err:"Lỗi"}
};
let L="de", ST={};
function fmt(s,o){return s.replace(/\{(\w+)\}/g,(_,k)=>o[k]!=null?o[k]:"")}
function tr(){const t=T[L];
 document.documentElement.lang=L;
 document.getElementById("tagline").textContent="⬡ "+t.tag;
 document.getElementById("subtitle").textContent=t.subtitle;
 document.getElementById("lang_l").textContent=t.lang+": ";
 for(const[id,k] of [["l_h","l_h"],["l_peers","l_peers"],["l_bal","l_bal"],["l_reward","l_reward"],["l_supply","l_supply"],
   ["h_mine","h_mine"],["h_wallet","h_wallet"],["h_send","h_send"],["h_net","h_net"],["h_log","h_log"],
   ["mnote","mnote"],["wallet_hint","wallet_hint"],["send_hint","send_hint"],["net_hint","net_hint"],["footer","footer"],
   ["btn_copy","copy"],["recv_l","recv_l"],["h_hist","h_hist"]]) document.getElementById(id).textContent=t[k];
 document.getElementById("memo").placeholder=t.memo;
 document.getElementById("btn_send").textContent=t.btn_send;
 document.getElementById("btn_connect").textContent=t.btn_connect;
 render();
}
function toast(m){const e=document.getElementById("toast");e.textContent=m;e.classList.add("show");setTimeout(()=>e.classList.remove("show"),1600)}
function evtext(e){const t=T[L];
 if(e.kind==="mined")return fmt(t.ev_mined,{h:e.h,r:e.reward});
 if(e.kind==="start")return t.ev_start; if(e.kind==="stop")return t.ev_stop;
 if(e.kind==="send")return fmt(t.ev_send,{a:e.amount,to:(e.to||"").slice(0,14)});
 return e.kind;}
function render(){const t=T[L],d=ST;if(!d.address)return;
 document.getElementById("s_h").textContent=d.height;
 document.getElementById("s_peers").textContent=d.peers;
 document.getElementById("s_bal").textContent=(+d.balance).toLocaleString(undefined,{maximumFractionDigits:4});
 document.getElementById("s_reward").textContent=(+d.reward);
 document.getElementById("s_supply").textContent=Math.round(d.supply).toLocaleString()+" / "+Math.round(d.maxsupply).toLocaleString();
 document.getElementById("s_bar").style.width=(100*d.supply/d.maxsupply)+"%";
 document.getElementById("addr").textContent=d.address;
 document.getElementById("mdot").className="dot"+(d.mining?" on":"");
 document.getElementById("mstat").textContent=(d.mining?t.mine_on:t.mine_off)+" · "+(+d.spendable).toLocaleString(undefined,{maximumFractionDigits:4})+" "+t.spendable+" · "+d.remaining+" "+t.remaining;
 const b=document.getElementById("btn_mine");b.textContent=d.mining?t.btn_stop:t.btn_start;b.dataset.on=d.mining?"1":"0";
 const log=document.getElementById("log");log.innerHTML="";
 (d.events||[]).slice().reverse().forEach(e=>{const row=document.createElement("div");
   const ts=new Date(e.t*1000).toLocaleTimeString();row.textContent=ts+"  "+evtext(e);log.appendChild(row)});
}
function el(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e}
function renderHist(items){const t=T[L],box=document.getElementById("hist");box.textContent="";
 if(!items||!items.length){box.appendChild(el("div","l2",t.hist_empty));return}
 items.forEach(it=>{const row=el("div","it");
   let label,sign,cls;
   if(it.kind==="mined"){label=t.hist_mined;sign="+";cls="pos"}
   else if(it.kind==="received"){label=t.hist_received+" "+String(it.party||"").slice(0,16)+"…";sign="+";cls="pos"}
   else{label=t.hist_sent+" "+String(it.party||"").slice(0,16)+"…";sign="−";cls="neg"}
   const memo=it.memo?(" · "+it.memo):"";
   const left=el("div");left.appendChild(el("div",null,label));left.appendChild(el("div","l2","#"+it.h+memo));
   row.appendChild(left);
   row.appendChild(el("div","amt "+cls,sign+(+it.amount).toLocaleString(undefined,{maximumFractionDigits:4})+" BGC"));
   box.appendChild(row)});
}
const TOKEN="__BGC_TOKEN__";
const H={"X-BGC-Token":TOKEN};
async function pollHist(){try{const r=await fetch("/api/history",{headers:H});renderHist(await r.json())}catch(e){}}
async function poll(){try{const r=await fetch("/api/status",{headers:H});ST=await r.json();render()}catch(e){}}
async function post(u,b){const r=await fetch(u,{method:"POST",headers:Object.assign({"Content-Type":"application/json"},H),body:JSON.stringify(b||{})});return r.json()}
document.getElementById("lang").onchange=e=>{L=e.target.value;localStorage&&localStorage.setItem("bgc_lang",L);tr()};
document.getElementById("btn_mine").onclick=async e=>{const on=e.target.dataset.on==="1";await post("/api/mine",{on:!on});poll()};
document.getElementById("btn_copy").onclick=()=>{navigator.clipboard&&navigator.clipboard.writeText(ST.address);toast(T[L].copied)};
document.getElementById("btn_send").onclick=async()=>{const to=document.getElementById("to").value.trim(),amt=document.getElementById("amt").value,memo=document.getElementById("memo").value;
 if(!to||!amt)return;const r=await post("/api/send",{to,amount:amt,memo});toast(r.ok?T[L].btn_send+" ✓":(T[L].err+": "+r.msg));if(r.ok){document.getElementById("to").value="";document.getElementById("amt").value=""}poll()};
document.getElementById("btn_connect").onclick=async()=>{const p=document.getElementById("peer").value.trim();if(!p)return;await post("/api/connect",{peer:p});try{localStorage&&localStorage.setItem("bgc_peer",p)}catch(e){}toast("OK");poll()};
try{const s=localStorage&&localStorage.getItem("bgc_lang");if(s){L=s;document.getElementById("lang").value=s}}catch(e){}
try{const p=localStorage&&localStorage.getItem("bgc_peer");if(p)document.getElementById("peer").value=p}catch(e){}
// QR dia chi: hien neu server co; an ca o neu khong co (204/loi)
const _qr=document.getElementById("qr");
_qr.onerror=()=>{document.getElementById("qrbox").style.display="none"};
_qr.src="/api/qr?k="+encodeURIComponent(TOKEN)+"&"+Date.now();
tr();poll();pollHist();setInterval(poll,2000);setInterval(pollHist,5000);
</script></body></html>"""

# ---------------------------------------------------------------- API
def status():
    n=NODE; ch=n.chain; w=n.w; h=ch.height(); p=ch.p
    return {"height":h,"peers":len(n.peers),"supply":ch.audit_supply()/COIN,"maxsupply":p.max_supply()/COIN,
            "reward":p.subsidy(h)/COIN,"balance":w.balance(ch),"spendable":w.balance_spendable(ch),
            "address":n.addr,"remaining":w.remaining(),"mining":n.mining,"chainwork":str(ch.chainwork()),
            "name":n.name,"port":n.port,"maturity":p.maturity,"net":p.name,"hashrate":round(n.hashrate),
            "events":n.events[-60:]}

_HIST={"tip":None,"items":[]}
def history(limit=30):
    """Lich su giao dich cua vi (cache theo dinh chuoi, chi quet lai khi co khoi moi)."""
    tip=NODE.chain.tip()
    if _HIST["tip"]!=tip:
        _HIST["items"]=_scan_history(limit); _HIST["tip"]=tip
    return _HIST["items"]

def _scan_history(limit):
    """Lich su giao dich cua vi: da dao / da nhan / da gui (quet toan chuoi)."""
    ch=NODE.chain; me=NODE.addr
    outmap={}                                   # (txid,vout) -> (value,addr)
    for blk in ch.blocks:
        for tx in blk.txs:
            tid=tx.txid()
            for vo,o in enumerate(tx.vout): outmap[(tid,vo)]=(o.value,o.address)
    items=[]
    for blk in ch.blocks:
        for tx in blk.txs:
            out_me=sum(o.value for o in tx.vout if o.address==me)
            memo=next((o.memo for o in tx.vout if o.memo), "")
            if tx.coinbase:
                if out_me>0:
                    items.append({"kind":"mined","amount":out_me/COIN,"h":blk.index,"memo":""})
                continue
            in_me=sum(outmap.get((i.txid,i.vout),(0,""))[0] for i in tx.vin if outmap.get((i.txid,i.vout),(0,""))[1]==me)
            if in_me>0:                          # minh la NGUOI GUI
                to=next((o.address for o in tx.vout if o.address!=me), me)
                sent=sum(o.value for o in tx.vout if o.address!=me)
                items.append({"kind":"sent","amount":sent/COIN,"party":to,"h":blk.index,"memo":memo})
            elif out_me>0:                       # minh la NGUOI NHAN
                frm=outmap.get((tx.vin[0].txid,tx.vin[0].vout),(0,"?"))[1]
                items.append({"kind":"received","amount":out_me/COIN,"party":frm,"h":blk.index,"memo":memo})
    return items[-limit:][::-1]                  # moi nhat len dau

class Handler(BaseHTTPRequestHandler):
    def _send(s, code, body, ctype="application/json"):
        b=body if isinstance(body,bytes) else body.encode()
        s.send_response(code); s.send_header("Content-Type",ctype+"; charset=utf-8")
        s.send_header("Content-Length",str(len(b)))
        s.send_header("Cache-Control","no-store"); s.send_header("X-Frame-Options","DENY")
        s.send_header("Referrer-Policy","no-referrer")
        s.end_headers(); s.wfile.write(b)
    def _read_body(s):
        """Read the whole request body first: replying while it is unread makes Windows reset the connection."""
        try: n=int(s.headers.get("Content-Length",0))
        except ValueError: n=-1
        if not 0<=n<=65536: s.close_connection=True; return None
        return s.rfile.read(n)
    def _json(s):
        d=json.loads(s._body or b"{}")
        if type(d) is not dict: raise ValueError("bad request")
        return d
    def _host_ok(s):
        """Only answer requests addressed to this machine (blocks DNS-rebinding attacks)."""
        return s.headers.get("Host","") in {f"localhost:{WEB_PORT}", f"127.0.0.1:{WEB_PORT}", f"[::1]:{WEB_PORT}"}
    def _auth_ok(s):
        k=s.headers.get("X-BGC-Token","")
        if not k and "?" in s.path:
            from urllib.parse import parse_qs
            k=(parse_qs(s.path.split("?",1)[1]).get("k") or [""])[0]
        return hmac.compare_digest(k.encode(), TOKEN.encode())
    def do_GET(s):
        if not s._host_ok(): s._send(403,"{}"); return
        if s.path=="/" or s.path.startswith("/index"):
            s._send(200,PAGE.replace("__BGC_TOKEN__",TOKEN),"text/html"); return
        if not s.path.startswith("/api/"): s._send(404,"{}"); return
        if not s._auth_ok(): s._send(403,"{}"); return
        if s.path.startswith("/api/status"): s._send(200,json.dumps(status()))
        elif s.path.startswith("/api/history"): s._send(200,json.dumps(history()))
        elif s.path.startswith("/api/qr"):
            if not HAS_QR: s.send_response(204); s.end_headers(); return
            import io
            q=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
            q.add_data(NODE.addr); q.make(fit=True)
            buf=io.BytesIO(); q.make_image(image_factory=qrcode.image.svg.SvgPathImage).save(buf)
            s._send(200, buf.getvalue(), "image/svg+xml")
        else: s._send(404,"{}")
    def do_POST(s):
        s._body=s._read_body()
        if s._body is None: s._send(413,"{}"); return
        if not s._host_ok() or not s._auth_ok(): s._send(403,"{}"); return
        if not s.headers.get("Content-Type","").startswith("application/json"): s._send(415,"{}"); return
        try:
            if s.path=="/api/mine":
                on=s._json().get("on",True)
                if on and not NODE.mining: NODE.start_mining(); NODE._log("start")
                elif not on and NODE.mining: NODE.mining=False; NODE._log("stop")
                s._send(200,json.dumps({"ok":True}))
            elif s.path=="/api/send":
                d=s._json(); to=str(d.get("to","")).strip(); amount=str(d.get("amount","")).strip()
                tx=NODE.w.send(NODE.chain,to,amount,memo=str(d.get("memo","") or "send"))
                ok,m=NODE.submit_tx(tx)
                if ok: NODE._log("send",amount=amount,to=to)
                s._send(200,json.dumps({"ok":ok,"msg":m}))
            elif s.path=="/api/connect":
                d=s._json(); host,port=d["peer"].rsplit(":",1); NODE.connect(host,int(port))
                s._send(200,json.dumps({"ok":True}))
            else: s._send(404,"{}")
        except Exception as e:
            s._send(200,json.dumps({"ok":False,"msg":str(e)}))
    def log_message(s,*a): pass

def main():
    global NODE, PEERS_CFG, WEB_PORT
    ap=argparse.ArgumentParser(description="BGC Miner App (giao dien trinh duyet).")
    ap.add_argument("--web-port", type=int, default=7000)
    ap.add_argument("--port", type=int, default=9333)
    ap.add_argument("--name", default=(os.environ.get("COMPUTERNAME") or "tho")[:12])
    ap.add_argument("--peers", default="")
    ap.add_argument("--datadir", default=os.path.join(HERE,"bgcfl_data"))
    ap.add_argument("--wallet", default=os.path.join(HERE,"my_bgc_wallet.json"))
    ap.add_argument("--regtest", action="store_true", help="mang thu nghiem rieng (do kho thap, coin KHONG co gia tri)")
    ap.add_argument("--no-open", action="store_true")
    a=ap.parse_args()

    os.makedirs(a.datadir, exist_ok=True)
    print("[khoi dong] dang nap vi va kiem tra lai chuoi da luu...")
    w=Wallet(a.wallet)
    NODE=MinerNode(a.name, w, a.datadir, a.port, params=REGTEST if a.regtest else MAIN)
    load_genesis(NODE.chain)
    PEERS_CFG=parse_peers(a.peers)
    if PEERS_CFG: start_reconnector(NODE, PEERS_CFG)

    WEB_PORT=a.web_port
    srv=ThreadingHTTPServer(("127.0.0.1",a.web_port),Handler)
    url=f"http://localhost:{a.web_port}"
    print("="*68); print(" BGC Miner App dang chay.  Mo trinh duyet:", url); print("="*68)
    print(f"   mang: {NODE.chain.p.name} | vi: {NODE.addr}")
    print(f"   cong P2P: {NODE.port} | seed: {PEERS_CFG or '(dao solo)'}")
    if not a.no_open:
        try: threading.Timer(1.0, lambda: webbrowser.open(url)).start()
        except Exception: pass
    try: srv.serve_forever()
    except KeyboardInterrupt: pass
    NODE.close(); srv.shutdown()
    return 0

if __name__=="__main__": sys.exit(main())
