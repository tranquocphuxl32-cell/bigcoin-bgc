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
import os, sys, json, time, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bigcoin_pq import H, xmss_verify, addr_of

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
