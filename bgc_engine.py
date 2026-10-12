#!/usr/bin/env python3
# =====================================================================
#  BGC ENGINE v2 - loi BIGCOIN: PQ + 21tr + timelock + memo + PoA + LUU DIA
#  + FORK-CHOICE / REORG: kho khoi theo hash, chon NHANH DAI NHAT hop le lam active,
#    tu tai to chuc (reorg) khi co nhanh dai hon -> nhieu node hoi tu ve 1 chuoi.
# =====================================================================
import os, sys, json, time, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bigcoin_pq as pq
from bigcoin_pq import XmssKey, H, xmss_verify, addr_of

COIN=100_000_000
MAX_SUPPLY=21_000_000*COIN
GEN_AI=10_000_000*COIN
GEN_FOUNDER=11_000_000*COIN

class TxOut:
    __slots__=("value","address","memo","lock")
    def __init__(s,value,address,memo="",lock=0): s.value=value; s.address=address; s.memo=memo; s.lock=lock
    def ser(s): return f"{s.value}|{s.address}|{s.memo}|L{s.lock}"
    def to_d(s): return {"v":s.value,"a":s.address,"m":s.memo,"l":s.lock}
    @staticmethod
    def from_d(d): return TxOut(d["v"],d["a"],d.get("m",""),d.get("l",0))
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
    def sighash(s): return H(b"BGC-sig"+s.body().encode())
    def to_d(s): return {"i":[i.to_d() for i in s.vin],"o":[o.to_d() for o in s.vout],"cb":s.coinbase}
    @staticmethod
    def from_d(d): return Tx([TxIn.from_d(x) for x in d["i"]],[TxOut.from_d(x) for x in d["o"]],d.get("cb",False))
class Block:
    __slots__=("index","prev","txs","auth","ts","sig")
    def __init__(s,index,prev,txs,auth,ts=None,sig=None): s.index=index; s.prev=prev; s.txs=txs; s.auth=auth; s.ts=ts or int(time.time()); s.sig=sig
    def root(s): return H("".join(t.txid() for t in s.txs).encode()).hex()
    def header(s): return f"{s.index}|{s.prev}|{s.root()}|{s.ts}|{s.auth}"
    def hash(s): return H(s.header().encode()).hex()
    def sighash(s): return H(b"BGC-blk"+s.header().encode())
    def to_d(s): return {"i":s.index,"p":s.prev,"tx":[t.to_d() for t in s.txs],"au":s.auth,"ts":s.ts,"s":s.sig}
    @staticmethod
    def from_d(d): return Block(d["i"],d["p"],[Tx.from_d(x) for x in d["tx"]],d["au"],d["ts"],d.get("s"))

GENESIS_PREV="0"*64

FINALITY=6   # khoi sau nay >= FINALITY khoi so voi tip -> COI NHU CHOT, khong reorg qua

class Chain:
    """Kho khoi + fork-choice + reorg + luu dia + round-robin PoA + finality."""
    def __init__(s, authorities, datadir=None):
        # authorities: danh sach root-hex duoc phep ky khoi (PoA; luan phien theo thu tu)
        if isinstance(authorities,str): authorities=[authorities]
        s.auth_list=sorted(set(authorities)); s.auth=set(s.auth_list)
        s.store={}; s.active=[]; s.utxo={}; s.mempool={}; s.datadir=datadir
    def expected_auth(s, index): return s.auth_list[index % len(s.auth_list)]
    def height(s): return len(s.active)
    def tip(s): return s.active[-1] if s.active else GENESIS_PREV
    @property
    def blocks(s): return [s.store[h] for h in s.active]

    # ---- kiem tra 1 giao dich voi 1 trang thai utxo + chieu cao cho truoc ----
    def _check_tx(s, tx, utxo, height, is_genesis=False):
        for o in tx.vout:
            if o.value<0 or o.value>MAX_SUPPLY: return False,"gia tri ngoai khoang"
        out=sum(o.value for o in tx.vout)
        if is_genesis: return (out==MAX_SUPPLY,"genesis phai = 21,000,000")
        if tx.coinbase: return (out==0,"coinbase khong tao coin")
        insum=0; seen=set()
        for i in tx.vin:
            k=(i.txid,i.vout)
            if k in seen: return False,"input trung"
            if k not in utxo: return False,"input khong ton tai/da tieu"
            val,owner,lock=utxo[k]
            if lock>height: return False,f"coin khoa toi khoi {lock}"
            if addr_of(bytes.fromhex(i.owner))!=owner: return False,"owner khong khop"
            if not xmss_verify(bytes.fromhex(i.owner), tx.sighash(), i.sig): return False,"chu ky sai"
            insum+=val; seen.add(k)
        if out>insum: return False,"tao coin tu khong khi (out>in)"
        return True,"ok"

    def _valid_block_shape(s, blk):
        # rotation 'mem' (Clique): khoi do authority khac ngoai luot VAN hop le (de liveness),
        # nhung co trong so thap hon; luat 'khong ky lien tiep' kiem trong _replay (can nhanh).
        if blk.auth not in s.auth: return False,"khong phai authority hop le"
        if not xmss_verify(bytes.fromhex(blk.auth), blk.sighash(), blk.sig): return False,"chu ky khoi sai"
        return True,"ok"
    def block_weight(s, index, auth):
        return 2 if auth==s.expected_auth(index) else 1   # dung luot=2, trai luot=1 (uu tien dung luot)

    def _branch(s, tip_hash):
        """Dung lai nhanh genesis..tip_hash tu kho (theo prev). None neu dut/khong co genesis."""
        chain=[]; h=tip_hash
        while h!=GENESIS_PREV:
            if h not in s.store: return None
            b=s.store[h]; chain.append(b); h=b.prev
            if len(chain)>1_000_000: return None
        chain.reverse()
        if not chain or chain[0].index!=0: return None
        return chain

    def _replay(s, branch):
        """Phat lai nhanh -> (ok, utxo, weight). Kiem khoi + tx + supply-guard + luat ky."""
        utxo={}; weight=0; recent=[]; LIMIT=len(s.auth_list)//2
        for h_i,blk in enumerate(branch):
            if blk.index!=h_i: return False,None,0
            if h_i>0 and blk.prev!=branch[h_i-1].hash(): return False,None,0
            if h_i>0 and LIMIT>0 and blk.auth in recent[-LIMIT:]: return False,None,0  # khong ky lien tiep
            for ti,tx in enumerate(blk.txs):
                ok,_=s._check_tx(tx, utxo, h_i, is_genesis=(h_i==0 and ti==0))
                if not ok: return False,None,0
            for tx in blk.txs:
                for i in tx.vin: utxo.pop((i.txid,i.vout),None)
                for vo,o in enumerate(tx.vout):
                    if o.value>0: utxo[(tx.txid(),vo)]=(o.value,o.address,o.lock)
            if sum(v for v,_,_ in utxo.values())!=MAX_SUPPLY: return False,None,0   # supply-guard
            weight += s.block_weight(h_i, blk.auth); recent.append(blk.auth)
        return True,utxo,weight

    def add_block(s, blk, persist=True):
        """Nhan 1 khoi vao kho, roi chay fork-choice. Tra (accepted, msg, reorged)."""
        ok,m=s._valid_block_shape(blk)
        if not ok: return False,m,False
        hh=blk.hash()
        if hh in s.store: return False,"da co",False
        s.store[hh]=blk
        if persist and s.datadir: s._save(blk)
        reorged=s._reorg_to_best()
        return True,"ok",reorged

    def _reorg_to_best(s):
        """Chon nhanh DAI HON HAN hop le lam active (hoa thi giu nhanh cu = first-seen)."""
        prevset={b.prev for b in s.store.values()}
        tips=[h for h in s.store if h not in prevset]     # la: khong ai tham chieu lam prev
        best=None; best_utxo=None; best_w=-1
        if s.active:                                      # uu tien active hien tai khi hoa trong so
            ok0,u0,w0=s._replay([s.store[h] for h in s.active])
            if ok0: best=[s.store[h] for h in s.active]; best_utxo=u0; best_w=w0
        finalized=s.active[:max(0,len(s.active)-FINALITY)]  # tien to da CHOT, khong duoc reorg qua
        for t in tips:
            br=s._branch(t)
            if not br: continue
            brh=[b.hash() for b in br]
            if brh[:len(finalized)]!=finalized: continue  # vi pham finality -> bo qua
            ok,utxo,w=s._replay(br)
            if ok and w>best_w:                           # chon TONG TRONG SO cao nhat (Clique)
                best=br; best_utxo=utxo; best_w=w
        if best is None: return False
        new_active=[b.hash() for b in best]
        if new_active==s.active: return False
        reorged = (s.active != new_active[:len(s.active)])   # active cu KHONG phai tien to -> reorg
        old=set(s.active)
        s.active=new_active; s.utxo=best_utxo
        for h in old-set(new_active):                     # tx o nhanh bi bo -> tra lai mempool
            for tx in s.store[h].txs:
                if not tx.coinbase: s.add_mempool(tx)
        for h in new_active:                              # tx da vao chuoi -> bo khoi mempool
            for tx in s.store[h].txs: s.mempool.pop(tx.txid(),None)
        return reorged

    def add_mempool(s, tx):
        ok,m=s._check_tx(tx, s.utxo, s.height())
        if ok: s.mempool[tx.txid()]=tx
        return ok,m
    def check_tx(s, tx): return s._check_tx(tx, s.utxo, s.height())

    def audit_supply(s): return sum(v for v,_,_ in s.utxo.values())
    def balance(s,a,spendable_only=False):
        h=s.height(); return sum(v for v,o,lk in s.utxo.values() if o==a and (not spendable_only or lk<=h))
    def locked(s,a):
        h=s.height(); return sum(v for v,o,lk in s.utxo.values() if o==a and lk>h)

    # ---- persistence ----
    def _path(s): return os.path.join(s.datadir,"chain.jsonl")
    def _save(s, blk):
        os.makedirs(s.datadir,exist_ok=True)
        with open(s._path(),"a") as f: f.write(json.dumps(blk.to_d())+"\n")
    def load(s):
        if not s.datadir or not os.path.exists(s._path()): return 0
        n=0
        with open(s._path()) as f:
            for line in f:
                line=line.strip()
                if line:
                    s.add_block(Block.from_d(json.loads(line)), persist=False); n+=1
        return n
