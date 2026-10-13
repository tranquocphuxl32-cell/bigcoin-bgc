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
import os, sys, json, time, hashlib, threading, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bigcoin_pq import H, xmss_verify, addr_of

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
