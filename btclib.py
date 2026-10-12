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
import hashlib, hmac, struct, json, subprocess, os, time

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
