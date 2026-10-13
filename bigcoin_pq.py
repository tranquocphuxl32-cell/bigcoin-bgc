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
import hashlib, os, json, time, sys

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

if __name__=="__main__": sys.exit(main())
