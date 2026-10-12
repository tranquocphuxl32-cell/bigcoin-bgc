#!/usr/bin/env python3
# =====================================================================
#  BGC MINER - MOT FILE DUY NHAT (tu chua tat ca). Gui file nay cho may khac:
#  chay la DAO ra BGC, BGC hien trong vi, va CHUYEN QUA LAI duoc.
#  Mac dinh tieng Duc + chon ngon ngu. Tu tao genesis ben trong (khong can file phu).
#  Chay:   python BGC_Miner_1file.py                 (mo trinh duyet, dao solo)
#          python BGC_Miner_1file.py --peers IP:9333 (tham gia mang, chuyen qua lai)
#  (Dong goi .exe:  pyinstaller --onefile --name BGC-Miner BGC_Miner_1file.py)
# =====================================================================
import hashlib, hmac, struct, json, subprocess, os, time, sys, socket, threading, argparse, functools, webbrowser, io, base64, math
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

class XmssKey:
    """A post-quantum address = the Merkle root over 2^h WOTS one-time keys."""
    def __init__(s, master=None, h=4):
        s.master=master or os.urandom(32); s.h=h; L=1<<h; s.next=0
        s.leaves=[]
        for k in range(L):
            _,pk=wots_keygen(H(s.master+k.to_bytes(4,"big"))); s.leaves.append(wots_pk_hash(pk))
        s.levels=merkle(s.leaves); s.root=s.levels[-1][0]
    def sign(s, mh):
        if s.next>=(1<<s.h): raise RuntimeError("out of one-time signatures (need a new address / larger h)")
        k=s.next; s.next+=1
        sk,_=wots_keygen(H(s.master+k.to_bytes(4,"big")))
        return {"i":k,"w":[x.hex() for x in wots_sign(sk,mh)],"p":[x.hex() for x in auth_path(s.levels,k)]}
def xmss_verify(root, mh, sig):
    pk=wots_pk_from_sig([bytes.fromhex(x) for x in sig["w"]], mh)
    leaf=wots_pk_hash(pk)
    return root_from(leaf, sig["i"], [bytes.fromhex(x) for x in sig["p"]])==root

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
        ks=_block(key,nonce,start+i)
        for j,b in enumerate(data[64*i:64*i+64]): out.append(b^ks[j])
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

def _recvn(sock,n):
    b=b""
    while len(b)<n:
        r=sock.recv(n-len(b))
        if not r: raise ConnectionError("dong")
        b+=r
    return b

class SecureSocket:
    """Boc socket: bat tay ECDH epheral -> 2 khoa huong (gui/nhan). Khung: [4 byte len][ct+tag]."""
    def __init__(s, sock, initiator):
        s.sock=sock; s.sn=0; s.rn=0; s._slock=threading.Lock()
        d=newkey(); Pt=pmul(d)
        mypub=(b"\x02" if Pt[1]%2==0 else b"\x03")+Pt[0].to_bytes(32,"big")
        sock.sendall(mypub)
        theirs=_recvn(sock,33)
        x=int.from_bytes(theirs[1:],"big"); y=pow((pow(x,3,P)+7)%P,(P+1)//4,P)
        if y%2!=(0 if theirs[0]==2 else 1): y=P-y
        shared=pmul(d,(x,y))[0].to_bytes(32,"big")
        # khoa doi xung: sap xep pub theo thu tu co dinh de 2 ben ra cung khoa
        a,b=(mypub,theirs) if initiator else (theirs,mypub)
        k=_hkdf(b"BGC-v2-transport", shared, a+b, 64)
        # initiator gui bang k[:32], nhan bang k[32:]; responder nguoc lai
        s.ks, s.kr = (k[:32],k[32:]) if initiator else (k[32:],k[:32])
    def _nonce(s,n): return b"\x00"*4+n.to_bytes(8,"little")
    def send(s, data:bytes):
        with s._slock:                                   # 1 luong 1 luc: tranh dua nonce + ghi xen ke
            ct=aead_enc(s.ks, s._nonce(s.sn), b"", data); s.sn+=1
            s.sock.sendall(struct.pack("<I",len(ct))+ct)
    def recv(s)->bytes:
        ln=struct.unpack("<I",_recvn(s.sock,4))[0]
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
#  BGC-FL (FAIR LAUNCH, Bitcoin-style, near production) - no premine, PoW,
#  halving, + DIFFICULTY RETARGET + COINBASE MATURITY + real chainwork.
#   - NO PREMINE: coins are emitted gradually via the coinbase (mining). Permissionless PoW.
#   - subsidy(h)=50>>(h//HALVING), halving -> total ~21M (scaled down for the demo).
#   - RETARGET: every RETARGET blocks, difficulty adjusts to real time (like Bitcoin's 2016 blocks).
#   - COINBASE MATURITY: freshly mined coins wait MATURITY blocks before they can be spent (reorg theft protection).
#   - Fork-choice = MOST CHAINWORK (sum of 2^256/(target+1)); reorg.
#   - Spends are signed with HASH-BASED post-quantum signatures (bigcoin_pq). Memo field for AI/robots.
# =====================================================================

def dsha(b): return hashlib.sha256(hashlib.sha256(b).digest()).digest()

COIN=100_000_000
INITIAL=50*COIN
HALVING=10
GENESIS_TARGET=(1<<248)-1      # initial difficulty (easy, for the demo); smaller number = harder
RETARGET=8                     # adjust difficulty every 8 blocks (Bitcoin: 2016)
BLOCK_INTERVAL=10              # target seconds/block (demo); Bitcoin: 600
MATURITY=5                     # coinbase waits 5 blocks before it can be spent (Bitcoin: 100)
GENESIS_PREV="00"*32

def subsidy(height):
    h=height//HALVING
    return (INITIAL>>h) if h<64 else 0
def max_supply():
    t=0; h=0
    while True:
        s=subsidy(h*HALVING)
        if s==0: break
        t+=s*HALVING; h+=1
    return t
MAX_SUPPLY=max_supply()
def work_of(target): return (1<<256)//(target+1)   # chainwork of one block given its difficulty

class TxOut:
    __slots__=("value","address","memo")
    def __init__(s,value,address,memo=""): s.value=value; s.address=address; s.memo=memo
    def ser(s): return f"{s.value}|{s.address}|{s.memo}"
    def to_d(s): return {"v":s.value,"a":s.address,"m":s.memo}
    @staticmethod
    def from_d(d): return TxOut(d["v"],d["a"],d.get("m",""))
class TxIn:
    __slots__=("txid","vout","owner","sig")
    def __init__(s,txid,vout,owner="",sig=None): s.txid=txid; s.vout=vout; s.owner=owner; s.sig=sig
    def ser(s): return f"{s.txid}:{s.vout}"
    def to_d(s): return {"t":s.txid,"o":s.vout,"ow":s.owner,"s":s.sig}
    @staticmethod
    def from_d(d): return TxIn(d["t"],d["o"],d.get("ow",""),d.get("s"))
class Tx:
    __slots__=("vin","vout","coinbase")
    def __init__(s,vin,vout,coinbase=False): s.vin=vin; s.vout=vout; s.coinbase=coinbase
    def body(s): return ("CB|" if s.coinbase else "TX|")+";".join(i.ser() for i in s.vin)+"=>"+";".join(o.ser() for o in s.vout)
    def txid(s): return H(s.body().encode()).hex()
    def sighash(s): return H(b"BGCFL-sig"+s.body().encode())
    def to_d(s): return {"i":[i.to_d() for i in s.vin],"o":[o.to_d() for o in s.vout],"cb":s.coinbase}
    @staticmethod
    def from_d(d): return Tx([TxIn.from_d(x) for x in d["i"]],[TxOut.from_d(x) for x in d["o"]],d.get("cb",False))
class Block:
    __slots__=("index","prev","txs","ts","nonce","target")
    def __init__(s,index,prev,txs,ts=None,nonce=0,target=GENESIS_TARGET):
        s.index=index; s.prev=prev; s.txs=txs; s.ts=ts or int(time.time()); s.nonce=nonce; s.target=target
    def root(s): return H("".join(t.txid() for t in s.txs).encode()).hex()
    def header(s): return f"{s.index}|{s.prev}|{s.root()}|{s.ts}|{s.target}|{s.nonce}"
    def hash(s): return dsha(s.header().encode()).hex()
    def pow_ok(s): return int.from_bytes(dsha(s.header().encode()),"big")<=s.target
    def to_d(s): return {"i":s.index,"p":s.prev,"tx":[t.to_d() for t in s.txs],"ts":s.ts,"n":s.nonce,"tg":s.target}
    @staticmethod
    def from_d(d): return Block(d["i"],d["p"],[Tx.from_d(x) for x in d["tx"]],d["ts"],d["n"],d.get("tg",GENESIS_TARGET))

def retarget(prev_target, actual_timespan):
    """Adjust difficulty: faster than target -> smaller target (harder); slower -> larger. Clamp 4x."""
    expected=RETARGET*BLOCK_INTERVAL
    actual=max(expected//4, min(expected*4, actual_timespan))   # clamp against shocks
    nt=prev_target*actual//expected
    return max(1, min(nt, GENESIS_TARGET))                       # never easier than genesis

def expected_target(branch, height):
    """The CORRECT difficulty for the block at `height`, computed from the earlier blocks in `branch`."""
    if height==0: return GENESIS_TARGET
    prev=branch[height-1].target
    if height % RETARGET != 0: return prev
    first=branch[height-RETARGET]; last=branch[height-1]
    return retarget(prev, last.ts-first.ts)

def mine(block):
    while True:
        if block.pow_ok(): return block
        block.nonce+=1

class Chain:
    def __init__(s, datadir=None):
        s.store={}; s.active=[]; s.utxo={}; s.mempool={}; s.datadir=datadir   # utxo: k->(value,addr,cb_height|-1)
    def height(s): return len(s.active)
    def tip(s): return s.active[-1] if s.active else GENESIS_PREV
    @property
    def blocks(s): return [s.store[h] for h in s.active]
    def next_target(s):   # difficulty for the NEXT block (miners use this)
        return expected_target(s.blocks, s.height())

    def _check_tx(s, tx, utxo, height, fees_ctx=None):
        for o in tx.vout:
            if o.value<0 or o.value>MAX_SUPPLY: return False,"value out of range"
        out=sum(o.value for o in tx.vout)
        if tx.coinbase:
            allowed=subsidy(height)+(fees_ctx or 0)
            return (out<=allowed, f"coinbase {out}>{allowed} (inflation)" if out>allowed else "ok")
        insum=0; seen=set()
        for i in tx.vin:
            k=(i.txid,i.vout)
            if k in seen: return False,"duplicate input"
            if k not in utxo: return False,"input missing/already spent"
            val,owner,cbh=utxo[k]
            if cbh>=0 and height-cbh<MATURITY: return False,f"immature coinbase (needs {MATURITY} blocks)"
            if addr_of(bytes.fromhex(i.owner))!=owner: return False,"owner mismatch"
            if not xmss_verify(bytes.fromhex(i.owner), tx.sighash(), i.sig): return False,"bad signature"
            insum+=val; seen.add(k)
        if out>insum: return False,"coins created from nothing (out>in)"
        return True,"ok"

    def _replay(s, branch):
        utxo={}; work=0; supply=0
        for h_i,blk in enumerate(branch):
            if blk.index!=h_i: return False,None,0
            if h_i>0 and blk.prev!=branch[h_i-1].hash(): return False,None,0
            if blk.target!=expected_target(branch,h_i): return False,None,0   # difficulty obeys the retarget rule
            if not blk.pow_ok(): return False,None,0                           # PoW meets the difficulty
            if not blk.txs or not blk.txs[0].coinbase: return False,None,0
            fees=0
            for tx in blk.txs[1:]:
                if tx.coinbase: return False,None,0
                insum=sum(utxo.get((i.txid,i.vout),(0,"",-1))[0] for i in tx.vin)
                fees+=insum-sum(o.value for o in tx.vout)
            for ti,tx in enumerate(blk.txs):
                ok,_=s._check_tx(tx, utxo, h_i, fees_ctx=(fees if ti==0 else None))
                if not ok: return False,None,0
            cb_out=sum(o.value for o in blk.txs[0].vout); supply+=cb_out-fees
            if supply>MAX_SUPPLY: return False,None,0
            for ti,tx in enumerate(blk.txs):
                for i in tx.vin: utxo.pop((i.txid,i.vout),None)
                cbh=h_i if ti==0 else -1
                for vo,o in enumerate(tx.vout):
                    if o.value>0: utxo[(tx.txid(),vo)]=(o.value,o.address,cbh)
            work+=work_of(blk.target)
        return True,utxo,work

    def add_block(s, blk, persist=True):
        if not blk.pow_ok(): return False,"bad PoW",False
        hh=blk.hash()
        if hh in s.store: return False,"already have it",False
        s.store[hh]=blk
        if persist and s.datadir: s._save(blk)
        return True,"ok",s._reorg()
    def _reorg(s):
        prevset={b.prev for b in s.store.values()}
        tips=[h for h in s.store if h not in prevset]
        best=None; best_u=None; best_w=-1
        if s.active:
            ok0,u0,w0=s._replay(s.blocks)
            if ok0: best=s.blocks; best_u=u0; best_w=w0
        for t in tips:
            br=s._branch(t)
            if not br: continue
            ok,u,w=s._replay(br)
            if ok and w>best_w: best=br; best_u=u; best_w=w
        if best is None: return False
        na=[b.hash() for b in best]
        if na==s.active: return False
        reorged=(s.active!=na[:len(s.active)])
        old=set(s.active); s.active=na; s.utxo=best_u
        for h in old-set(na):
            for tx in s.store[h].txs:
                if not tx.coinbase: s.mempool.setdefault(tx.txid(),tx)
        for h in na:
            for tx in s.store[h].txs: s.mempool.pop(tx.txid(),None)
        return reorged
    def _branch(s, tip):
        chain=[]; h=tip
        while h!=GENESIS_PREV:
            if h not in s.store: return None
            b=s.store[h]; chain.append(b); h=b.prev
            if len(chain)>1_000_000: return None
        chain.reverse()
        return chain if chain and chain[0].index==0 else None
    def chainwork(s):
        return sum(work_of(b.target) for b in s.blocks)
    def add_mempool(s, tx):
        ok,m=s._check_tx(tx, s.utxo, s.height())
        if ok: s.mempool[tx.txid()]=tx
        return ok,m
    def audit_supply(s): return sum(v for v,_,_ in s.utxo.values())
    def balance(s,a): return sum(v for v,o,_ in s.utxo.values() if o==a)
    def _path(s): return os.path.join(s.datadir,"chainfl.jsonl")
    def _save(s,blk):
        os.makedirs(s.datadir,exist_ok=True); open(s._path(),"a").write(json.dumps(blk.to_d())+"\n")
    def load(s):
        if not s.datadir or not os.path.exists(s._path()): return 0
        n=0
        for line in open(s._path()):
            line=line.strip()
            if line: s.add_block(Block.from_d(json.loads(line)),persist=False); n+=1
        return n

# ================= bgcfl_wallet =================
#!/usr/bin/env python3
# =====================================================================
#  BGC-FL WALLET - a POST-QUANTUM wallet for the fair-launch chain (bgcfl_engine).
#  - Signatures are HASH-BASED (XMSS) -> a quantum computer cannot forge them.
#  - XMSS is a "one-time, stateful" scheme: the leaf index 'next' MUST be persisted to
#    disk BEFORE signing, otherwise a restart could reuse a leaf and leak the key.
#    This wallet does exactly that.
#  - Fully compatible with bgcfl_engine (COIN, Tx/TxIn/TxOut, coinbase maturity).
#  Standalone: python bgcfl_wallet.py <wallet_file.json>   (create / show the address)
# =====================================================================

class Wallet:
    """A durable wallet: stores the master seed + the leaf index 'next'. h=12 -> 4096 signatures/wallet."""
    def __init__(s, path, h=12):
        s.path=path
        if os.path.exists(path):
            d=json.load(open(path))
            s.key=XmssKey(master=bytes.fromhex(d["master"]), h=d["h"]); s.key.next=d["next"]
        else:
            s.key=XmssKey(h=h); s._flush()
    def _flush(s):
        tmp=s.path+".tmp"
        json.dump({"master":s.key.master.hex(),"h":s.key.h,"next":s.key.next}, open(tmp,"w"))
        os.replace(tmp, s.path)                 # atomic write (survives power loss)
    @property
    def address(s): return addr_of(s.key.root)
    def remaining(s): return (1<<s.key.h)-s.key.next   # signatures left
    def sign(s, sighash):
        s._flush_before()                       # persist 'next' before consuming the leaf
        sig=s.key.sign(sighash)                 # sign() advances next
        s._flush()                              # persist the new 'next' -> durable
        return sig
    def _flush_before(s):
        # make sure the state "about to use leaf s.key.next" is on disk before signing
        s._flush()
    def spendable(s, chain):
        """My UTXOs that are MATURE (coinbase has waited MATURITY blocks)."""
        me=s.address; h=chain.height(); outs=[]
        for (t,v),(val,owner,cbh) in chain.utxo.items():
            if owner!=me: continue
            if cbh>=0 and h-cbh<MATURITY: continue     # freshly mined coin not mature yet
            outs.append(((t,v),val))
        return outs
    def balance(s, chain):
        return sum(v for v,o,_ in chain.utxo.values() if o==s.address)/COIN
    def balance_spendable(s, chain):
        return sum(val for _,val in s.spendable(chain))/COIN
    def send(s, chain, to_addr, amount_bgc, memo=""):
        amt=int(round(amount_bgc*COIN)); me=s.address
        picks=[]; got=0
        for k,val in s.spendable(chain):
            picks.append(k); got+=val
            if got>=amt: break
        if got<amt:
            raise RuntimeError(f"not enough mature BGC (need {amount_bgc}, have {got/COIN})")
        vin=[TxIn(t,v,s.key.root.hex()) for t,v in picks]
        vout=[TxOut(amt, to_addr, memo)]
        if got-amt>0: vout.append(TxOut(got-amt, me, "change"))
        tx=Tx(vin, vout)
        sig=s.sign(tx.sighash())
        for i in tx.vin: i.sig=sig
        return tx

def main():
    path=sys.argv[1] if len(sys.argv)>1 else "my_bgc_wallet.json"
    w=Wallet(path)
    print(f"Wallet: {path}")
    print(f"Address (receive BGC): {w.address}")
    print(f"Signatures left      : {w.remaining():,} (XMSS h={w.key.h})")
    print("Give this address to others to receive BGC. KEEP the wallet file safe - losing it loses the coins.")
    return 0

# ================= bgcfl_genesis =================
#!/usr/bin/env python3
# =====================================================================
#  BGC-FL GENESIS - creates the CANONICAL block 0 (shared by EVERY machine).
#  Like Bitcoin: everyone must start from the SAME genesis block to be on the same
#  network. This block is "mined" once and saved to bgcfl_genesis.json; everyone uses
#  that exact file. The genesis coinbase goes to an UNSPENDABLE address (hashed from the
#  message) -> NO premine, nobody gets a head start.
#  Usage: python bgcfl_genesis.py   -> writes bgcfl_genesis.json
# =====================================================================

# Official message (like the text on Bitcoin's genesis block).
# NOTE: this exact string fixes the genesis hash — do not change it, or every machine's
# genesis block 0 would differ and the networks would not match.
MSG = "BGC: dong tien hau luong tu, sinh ra cho ky nguyen AI va robot."
# UNSPENDABLE address: nobody knows its private key -> the genesis coinbase is "burned".
BURN = "BGC-genesis-unspendable-" + H(MSG.encode()).hex()[:24]
# Fixed timestamp so the genesis block is IDENTICAL across machines.
GENESIS_TS = 1760000000

def build():
    cb = Tx([], [TxOut(subsidy(0), BURN, MSG)], coinbase=True)
    blk = Block(0, "00"*32, [cb], ts=GENESIS_TS, target=GENESIS_TARGET)
    return mine(blk)       # find a nonce that meets the difficulty (easy for genesis, so fast)

# ================= run_miner =================
#!/usr/bin/env python3
# =====================================================================
#  RUN_MINER - mine BGC easily, Bitcoin-style (anyone can mine).
#
#  Like Bitcoin:
#    - Fair launch, NO premine: every coin is mined (PoW).
#    - Permissionless: no approval needed, just plug in a machine and mine.
#    - Halving + difficulty retarget + coinbase maturity + fork-choice by chainwork.
#  Unlike Bitcoin (stronger):
#    - HASH-BASED signatures (XMSS) -> QUANTUM-RESISTANT.
#    - P2P MA HOA dau-cuoi (ECDH + ChaCha20-Poly1305).
#
#  Dung (de nhat):
#    python run_miner.py                         # tao vi, dao solo, cong 9333
#    python run_miner.py --peers IP:9333         # tham gia mang qua 1 seed
#    python run_miner.py --name An --port 9333 --peers a.b.c.d:9333,e.f.g.h:9333
#
#  Khi chay: tu nap genesis chuan, noi seed, TU DAO vao vi cua ban, in trang thai.
#  Lenh go vao: bal | addr | send <dia_chi> <so_BGC> [memo] | peers | stop | quit
# =====================================================================

HERE=os.path.dirname(os.path.abspath(__file__))
MSG="BGC: dong tien hau luong tu, sinh ra cho ky nguyen AI va robot."

# ---------- nap / tao genesis chuan (chung moi may) ----------
def load_genesis(chain, gpath):
    if not os.path.exists(gpath):
        json.dump(build().to_d(), open(gpath,"w"))
        print(f"[genesis] chua co -> tu tao {os.path.basename(gpath)}")
    gb=Block.from_d(json.load(open(gpath)))
    if chain.height()==0:
        ok,m,_=chain.add_block(gb)
        print(f"[genesis] nap khoi 0: {'OK' if ok else 'LOI '+m} hash={gb.hash()[:16]}..")

# ---------- mang P2P ma hoa ----------
class Peer:
    def __init__(s,sec): s.sec=sec; s.lock=threading.Lock()
    def send(s,msg):
        try:
            with s.lock: s.sec.send(json.dumps(msg).encode())
        except Exception: pass

class MinerNode:
    def __init__(s, name, wallet, datadir, port):
        s.name=name; s.w=wallet; s.addr=wallet.address
        s.chain=Chain(datadir=datadir); s.chain.load()
        s.peers=[]; s.out=set(); s.lock=threading.Lock()
        s.stop=False; s.mining=False
        s.events=[]                          # nhat ky su kien (cho giao dien app doc)
        s.srv=socket.socket(); s.srv.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        s.srv.bind(("0.0.0.0",port)); s.port=s.srv.getsockname()[1]; s.srv.listen(16)
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
            if tgt in s.out: return
            s.out.add(tgt)
        try:
            c=socket.create_connection(tgt,timeout=4)
            threading.Thread(target=s._serve,args=(c,True,tgt),daemon=True).start()
        except OSError:
            with s.lock: s.out.discard(tgt)
    def _serve(s,sock,initiator,tgt):
        try: sec=SecureSocket(sock,initiator=initiator)
        except Exception:
            if tgt:
                with s.lock: s.out.discard(tgt)
            return
        p=Peer(sec)
        with s.lock: s.peers.append(p)
        p.send({"t":"hello","h":s.chain.height()})
        try:
            while not s.stop: s._on(p, json.loads(sec.recv()))
        except Exception: pass
        with s.lock:
            if p in s.peers: s.peers.remove(p)
            if tgt: s.out.discard(tgt)
    def _ticker(s):
        while not s.stop:
            time.sleep(0.5); s._bcast({"t":"hello","h":s.chain.height()})
    def _bcast(s,msg):
        with s.lock: ps=list(s.peers)
        for p in ps: p.send(msg)
    def _log(s, kind, **kw):                 # su kien co cau truc (app tu dich ngon ngu)
        ev={"t":time.time(),"kind":kind}; ev.update(kw)
        s.events.append(ev); s.events=s.events[-200:]
    def _on(s,p,msg):
        t=msg.get("t")
        if t=="hello":
            if msg["h"]>s.chain.height(): p.send({"t":"getblocks"})
            elif msg["h"]<s.chain.height(): p.send({"t":"blocks","b":[b.to_d() for b in s.chain.blocks]})
        elif t=="getblocks": p.send({"t":"blocks","b":[b.to_d() for b in s.chain.blocks]})
        elif t=="blocks":
            for bd in msg["b"]: s.chain.add_block(Block.from_d(bd))
        elif t=="block":
            before=s.chain.height(); s.chain.add_block(Block.from_d(msg["b"]))
            if s.chain.height()>before: s._bcast(msg)
            if s.chain.height()<msg["b"]["i"]+1: p.send({"t":"getblocks"})
        elif t=="tx":
            try: s.chain.add_mempool(Tx.from_d(msg["x"]))
            except Exception: pass
    def submit_tx(s, tx):
        ok,m=s.chain.add_mempool(tx)
        if ok: s._bcast({"t":"tx","x":tx.to_d()})
        return ok,m
    # --- dao (PoW) ---
    def start_mining(s):
        s.mining=True; threading.Thread(target=s._mine,daemon=True).start()
    def _mine(s):
        while s.mining and not s.stop:
            h=s.chain.height(); prev=s.chain.tip(); tgt=s.chain.next_target()
            # lay giao dich tu mempool (don gian: tat ca hop le)
            extra=list(s.chain.mempool.values())[:50]
            fees=0
            for tx in extra:
                insum=sum(s.chain.utxo.get((i.txid,i.vout),(0,"",-1))[0] for i in tx.vin)
                fees+=insum-sum(o.value for o in tx.vout)
            fees=max(0,fees)
            cb=Tx([],[TxOut(subsidy(h)+fees, s.addr, f"BGC {s.name} h{h}")],coinbase=True)
            blk=Block(h, prev, [cb]+extra, ts=int(time.time()), target=tgt)
            found=False
            for _ in range(6000):                 # dao tung dot; bo neu co khoi moi toi
                if s.chain.tip()!=prev or s.stop or not s.mining: break
                if blk.pow_ok(): found=True; break
                blk.nonce+=1
            if found and s.chain.tip()==prev:
                ok,_,_=s.chain.add_block(blk)
                if ok:
                    s._bcast({"t":"block","b":blk.to_d()})
                    s._log("mined", h=h, reward=subsidy(h)/COIN, tip=blk.hash()[:12])
                    print(f"  ⛏  DAO DUOC khoi #{h}  (+{subsidy(h)/COIN:g} BGC)  tip={blk.hash()[:12]}..")
            else:
                time.sleep(0.01)
    def close(s):
        s.stop=True; s.mining=False
        try: s.srv.close()
        except OSError: pass

def banner(name, port, addr):
    print("="*72)
    print(f" ⬡  {MSG}")
    print("="*72)
    print(" DAO BGC - fair-launch, khang luong tu, P2P ma hoa (giong BTC, manh hon)")
    print(f"   tho dao : {name}   |   cong : {port}")
    print(f"   vi cua ban (nhan BGC): {addr}")
    print("="*72)

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
function renderHist(items){const t=T[L],box=document.getElementById("hist");box.innerHTML="";
 if(!items||!items.length){box.innerHTML='<div class="l2">'+t.hist_empty+'</div>';return}
 items.forEach(it=>{const row=document.createElement("div");row.className="it";
   let label,sign,cls;
   if(it.kind==="mined"){label=t.hist_mined;sign="+";cls="pos"}
   else if(it.kind==="received"){label=t.hist_received+" "+(it.party||"").slice(0,16)+"…";sign="+";cls="pos"}
   else{label=t.hist_sent+" "+(it.party||"").slice(0,16)+"…";sign="−";cls="neg"}
   const memo=it.memo?(" · "+it.memo):"";
   row.innerHTML='<div><div>'+label+'</div><div class="l2">#'+it.h+memo+'</div></div>'+
     '<div class="amt '+cls+'">'+sign+(+it.amount).toLocaleString(undefined,{maximumFractionDigits:4})+' BGC</div>';
   box.appendChild(row)});
}
async function pollHist(){try{const r=await fetch("/api/history");renderHist(await r.json())}catch(e){}}
async function poll(){try{const r=await fetch("/api/status");ST=await r.json();render()}catch(e){}}
async function post(u,b){const r=await fetch(u,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b||{})});return r.json()}
document.getElementById("lang").onchange=e=>{L=e.target.value;localStorage&&localStorage.setItem("bgc_lang",L);tr()};
document.getElementById("btn_mine").onclick=async e=>{const on=e.target.dataset.on==="1";await post("/api/mine",{on:!on});poll()};
document.getElementById("btn_copy").onclick=()=>{navigator.clipboard&&navigator.clipboard.writeText(ST.address);toast(T[L].copied)};
document.getElementById("btn_send").onclick=async()=>{const to=document.getElementById("to").value.trim(),amt=document.getElementById("amt").value,memo=document.getElementById("memo").value;
 if(!to||!amt)return;const r=await post("/api/send",{to,amount:+amt,memo});toast(r.ok?T[L].btn_send+" ✓":(T[L].err+": "+r.msg));if(r.ok){document.getElementById("to").value="";document.getElementById("amt").value=""}poll()};
document.getElementById("btn_connect").onclick=async()=>{const p=document.getElementById("peer").value.trim();if(!p)return;await post("/api/connect",{peer:p});try{localStorage&&localStorage.setItem("bgc_peer",p)}catch(e){}toast("OK");poll()};
try{const s=localStorage&&localStorage.getItem("bgc_lang");if(s){L=s;document.getElementById("lang").value=s}}catch(e){}
try{const p=localStorage&&localStorage.getItem("bgc_peer");if(p)document.getElementById("peer").value=p}catch(e){}
// QR dia chi: hien neu server co; an ca o neu khong co (204/loi)
const _qr=document.getElementById("qr");
_qr.onerror=()=>{document.getElementById("qrbox").style.display="none"};
_qr.src="/api/qr?"+Date.now();
tr();poll();pollHist();setInterval(poll,2000);setInterval(pollHist,5000);
</script></body></html>"""

# ---------------------------------------------------------------- API
def status():
    n=NODE; ch=n.chain; w=n.w; h=ch.height()
    return {"height":h,"peers":len(n.peers),"supply":ch.audit_supply()/COIN,"maxsupply":MAX_SUPPLY/COIN,
            "reward":subsidy(h)/COIN,"balance":w.balance(ch),"spendable":w.balance_spendable(ch),
            "address":n.addr,"remaining":w.remaining(),"mining":n.mining,"chainwork":ch.chainwork(),
            "name":n.name,"port":n.port,"maturity":MATURITY,"events":n.events[-60:]}

def history(limit=30):
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
        s.send_header("Content-Length",str(len(b))); s.end_headers(); s.wfile.write(b)
    def _json(s):
        n=int(s.headers.get("Content-Length",0));
        return json.loads(s.rfile.read(n) or b"{}")
    def do_GET(s):
        if s.path.startswith("/api/status"): s._send(200,json.dumps(status()))
        elif s.path.startswith("/api/history"): s._send(200,json.dumps(history()))
        elif s.path.startswith("/api/qr"):
            if not HAS_QR: s.send_response(204); s.end_headers(); return
            import io
            q=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
            q.add_data(NODE.addr); q.make(fit=True)
            buf=io.BytesIO(); q.make_image(image_factory=qrcode.image.svg.SvgPathImage).save(buf)
            s._send(200, buf.getvalue(), "image/svg+xml")
        elif s.path=="/" or s.path.startswith("/index"): s._send(200,PAGE,"text/html")
        else: s._send(404,"{}")
    def do_POST(s):
        try:
            if s.path=="/api/mine":
                on=s._json().get("on",True)
                if on and not NODE.mining: NODE.start_mining(); NODE._log("start")
                elif not on and NODE.mining: NODE.mining=False; NODE._log("stop")
                s._send(200,json.dumps({"ok":True}))
            elif s.path=="/api/send":
                d=s._json(); tx=NODE.w.send(NODE.chain,d["to"],float(d["amount"]),memo=d.get("memo","") or "send")
                ok,m=NODE.submit_tx(tx)
                if ok: NODE._log("send",amount=float(d["amount"]),to=d["to"])
                s._send(200,json.dumps({"ok":ok,"msg":m}))
            elif s.path=="/api/connect":
                d=s._json(); host,port=d["peer"].rsplit(":",1); NODE.connect(host,int(port))
                s._send(200,json.dumps({"ok":True}))
            else: s._send(404,"{}")
        except Exception as e:
            s._send(200,json.dumps({"ok":False,"msg":str(e)}))
    def log_message(s,*a): pass

def main():
    global NODE, PEERS_CFG
    ap=argparse.ArgumentParser(description="BGC Miner App (giao dien trinh duyet).")
    ap.add_argument("--web-port", type=int, default=7000)
    ap.add_argument("--port", type=int, default=9333)
    ap.add_argument("--name", default=(os.environ.get("COMPUTERNAME") or "tho")[:12])
    ap.add_argument("--peers", default="")
    ap.add_argument("--datadir", default=os.path.join(HERE,"bgcfl_data"))
    ap.add_argument("--wallet", default=os.path.join(HERE,"my_bgc_wallet.json"))
    ap.add_argument("--genesis", default=os.path.join(HERE,"bgcfl_genesis.json"))
    ap.add_argument("--no-open", action="store_true")
    a=ap.parse_args()

    os.makedirs(a.datadir, exist_ok=True)
    w=Wallet(a.wallet)
    NODE=MinerNode(a.name, w, a.datadir, a.port)
    load_genesis(NODE.chain, a.genesis)
    PEERS_CFG=[p.strip() for p in a.peers.split(",") if p.strip() and "<" not in p]
    def reconnector():
        while not NODE.stop:
            for p in PEERS_CFG:
                try: host,port=p.rsplit(":",1); NODE.connect(host,int(port))
                except Exception: pass
            time.sleep(5)
    if PEERS_CFG: threading.Thread(target=reconnector,daemon=True).start()

    srv=ThreadingHTTPServer(("127.0.0.1",a.web_port),Handler)
    url=f"http://localhost:{a.web_port}"
    print("="*68); print(" BGC Miner App dang chay.  Mo trinh duyet:", url); print("="*68)
    print(f"   vi: {NODE.addr}")
    print(f"   cong P2P: {NODE.port} | seed: {PEERS_CFG or '(dao solo)'}")
    if not a.no_open:
        try: threading.Timer(1.0, lambda: webbrowser.open(url)).start()
        except Exception: pass
    try: srv.serve_forever()
    except KeyboardInterrupt: pass
    NODE.close(); srv.shutdown()
    return 0

if __name__=="__main__": sys.exit(main())
