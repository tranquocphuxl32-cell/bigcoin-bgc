#!/usr/bin/env python3
# =====================================================================
#  BGC regression tests (unittest). Uses the REGTEST network (tiny difficulty).
#  Run:  python test_bgc.py        or   python -m unittest test_bgc -v
# =====================================================================
import os, sys, json, time, socket, tempfile, threading, unittest, http.client
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bigcoin_pq import XmssKey, addr_of
import bgcfl_engine as E
from bgcfl_engine import (Chain, Block, Tx, TxIn, TxOut, mine, MAIN, REGTEST, COIN, MAX_MONEY,
                          GENESIS_TS, MAX_FUTURE_DRIFT, Invalid)
from bgcfl_wallet import Wallet, parse_amount

P=REGTEST

def new_key(h=6):
    k=XmssKey(h=h); return k, addr_of(k.root)

def child(chain, parent=None, addr=None, txs=(), ts=None, extra=0, target=None):
    """A mined block on top of `parent` (default: the tip) that follows every header rule."""
    with chain.lock:
        e=chain.index[parent or chain.tip()]
        height=e.height+1
        tgt=chain._target_after(e) if target is None else target
        ts=e.blk.ts+P.interval if ts is None else ts
    fees=0
    cb=Tx([],[TxOut(P.subsidy(height)+extra+fees, addr or MINER, f"cb{height}")],coinbase=True,height=height)
    return mine(Block(height, e.hash, [cb]+list(txs), ts=ts, target=tgt))

def grow(chain, n, addr=None):
    for _ in range(n):
        ok,m,_=chain.add_block(child(chain, addr=addr)); assert ok, m

def pay(key, outpoint, value, to, fee=0, memo=""):
    tx=Tx([TxIn(outpoint[0], outpoint[1], key.root.hex())],[TxOut(value-fee, to, memo)])
    sig=key.sign(tx.sighash(P.magic))
    for i in tx.vin: i.sig=sig
    return tx

MKEY,MINER=new_key(8)
_,BOB=new_key(4)

def mature_coin(chain, key=None, addr=None):
    """Mine one block to addr, then enough blocks for it to mature. Returns (outpoint, value)."""
    addr=addr or MINER
    grow(chain, 1, addr)
    cb=chain.get_block(chain.tip()).txs[0]
    grow(chain, P.maturity, BOB)
    return (cb.txid(), 0), cb.vout[0].value

class ConsensusTests(unittest.TestCase):
    def test_genesis_is_built_in_and_pays_nothing(self):
        a=Chain(params=P); b=Chain(params=P)
        self.assertEqual(a.genesis_hash, b.genesis_hash)
        self.assertNotEqual(Chain(params=MAIN).genesis_hash, a.genesis_hash)
        self.assertEqual(a.audit_supply(), 0)

    def test_main_supply_is_21_million(self):
        s=MAIN.max_supply()
        self.assertLessEqual(s, 21_000_000*COIN)
        self.assertGreater(s, 20_999_999*COIN)

    def test_coinbase_maturity(self):
        c=Chain(params=P); grow(c, 1)
        cb=c.get_block(c.tip()).txs[0]
        ok,m=c.add_mempool(pay(MKEY, (cb.txid(),0), cb.vout[0].value, BOB))
        self.assertFalse(ok); self.assertIn("immature", m)
        grow(c, P.maturity, BOB)
        ok,m=c.add_mempool(pay(MKEY, (cb.txid(),0), cb.vout[0].value, BOB))
        self.assertTrue(ok, m)

    def test_double_spend_inside_one_block_is_rejected(self):
        c=Chain(params=P); op,val=mature_coin(c)
        _,eve=new_key(4)
        t1=pay(MKEY, op, val, BOB); t2=pay(MKEY, op, val, eve)
        tip=c.tip(); supply=c.audit_supply()
        ok,m,_=c.add_block(child(c, txs=[t1,t2]))
        self.assertFalse(ok); self.assertIn("spent", m)
        self.assertEqual(c.tip(), tip); self.assertEqual(c.audit_supply(), supply)

    def test_mempool_rejects_conflicting_spend(self):
        c=Chain(params=P); op,val=mature_coin(c)
        _,eve=new_key(4)
        self.assertTrue(c.add_mempool(pay(MKEY, op, val, BOB))[0])
        ok,m=c.add_mempool(pay(MKEY, op, val, eve))
        self.assertFalse(ok); self.assertIn("double-spend", m)

    def test_coinbase_cannot_inflate(self):
        c=Chain(params=P)
        ok,m,_=c.add_block(child(c, extra=1))
        self.assertFalse(ok); self.assertIn("inflation", m)

    def test_fees_go_to_the_miner_via_template(self):
        c=Chain(params=P); op,val=mature_coin(c)
        _,m2=new_key(4)
        self.assertTrue(c.add_mempool(pay(MKEY, op, val, BOB, fee=3*COIN))[0])
        blk=c.block_template(m2, "t")
        blk.ts=c.get_block(c.tip()).ts+P.interval
        ok,m,_=c.add_block(mine(blk)); self.assertTrue(ok, m)
        self.assertEqual(c.balance(m2), P.subsidy(blk.index)+3*COIN)
        self.assertEqual(len(c.mempool), 0)

    def test_spend_of_output_created_earlier_in_same_block(self):
        c=Chain(params=P); op,val=mature_coin(c)
        bk,baddr=new_key(4)
        t1=pay(MKEY, op, val, baddr)
        t2=pay(bk, (t1.txid(),0), val, BOB)
        ok,m,_=c.add_block(child(c, txs=[t1,t2])); self.assertTrue(ok, m)
        self.assertEqual(c.balance(baddr), 0)

    def test_reorg_to_more_work_returns_txs_to_mempool(self):
        c=Chain(params=P); op,val=mature_coin(c)
        fork=c.tip()
        tx=pay(MKEY, op, val, BOB)
        ok,m,_=c.add_block(child(c, txs=[tx])); self.assertTrue(ok, m)
        a1=c.tip()
        # competing branch from `fork`, two blocks long -> more chainwork
        _,other=new_key(4)
        b1=child(c, parent=fork, addr=other, ts=c.get_block(fork).ts+P.interval+1)
        ok,m,re1=c.add_block(b1); self.assertTrue(ok, m); self.assertEqual(c.tip(), a1)
        b2=child(c, parent=b1.hash(), addr=other)
        ok,m,reorged=c.add_block(b2); self.assertTrue(ok, m)
        self.assertTrue(reorged); self.assertEqual(c.tip(), b2.hash())
        self.assertIn(tx.txid(), c.mempool)            # back to the mempool, not lost
        expected=sum(P.subsidy(b.index) for b in c.blocks[1:])   # genesis pays nothing
        self.assertEqual(c.audit_supply(), expected)

    def test_malformed_block_does_not_brick_the_node(self):
        c=Chain(params=P); op,val=mature_coin(c)
        bad=pay(MKEY, op, val, BOB); bad.vin[0].sig={"i":0,"w":["00"*32],"p":[]}
        ok,m,_=c.add_block(child(c, txs=[bad])); self.assertFalse(ok)
        grow(c, 2)                                        # still accepts good blocks afterwards
        for junk in [None, 5, {}, {"i":"x"}, {"i":1,"p":"00"*32,"tx":[{"cb":"yes"}],"ts":1,"n":0,"tg":1}]:
            with self.assertRaises(Invalid): Block.from_d(junk)

    def test_block_hash_commits_to_signatures(self):
        c=Chain(params=P); op,val=mature_coin(c)
        blk=child(c, txs=[pay(MKEY, op, val, BOB)])
        h=blk.hash(); blk.txs[1].vin[0].sig["w"][0]="11"*32
        self.assertNotEqual(blk.hash(), h)

    def test_timestamp_rules(self):
        c=Chain(params=P); grow(c, 12)
        e=c.index[c.tip()]
        ok,m,_=c.add_block(child(c, ts=c._mtp(e)))
        self.assertFalse(ok); self.assertIn("too old", m)
        future=child(c, ts=int(time.time())+MAX_FUTURE_DRIFT+600)
        ok,m,_=c.add_block(future)
        self.assertFalse(ok); self.assertIn("future", m)
        self.assertNotIn(future.hash(), c.bad)            # may become valid later

    def test_difficulty_follows_block_times(self):
        c=Chain(params=P)
        for _ in range(P.window):                         # 5x too fast -> harder
            ok,m,_=c.add_block(child(c, ts=c.get_block(c.tip()).ts+2)); self.assertTrue(ok, m)
        fast=c.next_target(); self.assertLess(fast, P.pow_limit)
        for _ in range(P.window):                         # 3x too slow -> easier again
            ok,m,_=c.add_block(child(c, ts=c.get_block(c.tip()).ts+30)); self.assertTrue(ok, m)
        self.assertGreater(c.next_target(), fast)

    def test_wrong_difficulty_rejected(self):
        c=Chain(params=P); grow(c, 3)
        ok,m,_=c.add_block(child(c, target=c.next_target()//2))
        self.assertFalse(ok); self.assertIn("difficulty", m)

    def test_target_above_pow_limit_rejected(self):
        c=Chain(params=MAIN)
        blk=Block(1, c.tip(), [Tx([],[TxOut(0,MINER,"")],coinbase=True,height=1)], ts=GENESIS_TS+600, target=(1<<255))
        ok,m,_=c.add_block(mine(blk)); self.assertFalse(ok); self.assertIn("limit", m)

    def test_orphan_is_connected_when_parent_arrives(self):
        src=Chain(params=P); grow(src, 2)
        b1,b2=src.blocks[1],src.blocks[2]
        c=Chain(params=P)
        ok,m,_=c.add_block(b2); self.assertFalse(ok); self.assertTrue(m.startswith("orphan"))
        ok,m,_=c.add_block(b1); self.assertTrue(ok, m)
        self.assertEqual(c.tip(), src.tip())

    def test_persistence_reload(self):
        with tempfile.TemporaryDirectory() as d:
            c=Chain(datadir=d, params=P); grow(c, 6)
            r=Chain(datadir=d, params=P); n=r.load()
            self.assertEqual(n, 6); self.assertEqual(r.tip(), c.tip())
            self.assertEqual(r.utxo, c.utxo)
            with open(os.path.join(d, "blocks-regtest.jsonl"), "a") as f: f.write('{"torn line')
            self.assertEqual(Chain(datadir=d, params=P).load(), 6)

    def test_sync_with_locator(self):
        a=Chain(params=P); grow(a, 30)
        b=Chain(params=P); grow(b, 3, BOB)                 # b is on its own short fork
        for _ in range(10):
            got=a.blocks_after(b.locator(), max_count=7)
            if not got: break
            for d in got: b.add_block(Block.from_d(json.loads(json.dumps(d))))
        self.assertEqual(b.tip(), a.tip())

    def test_serialization_is_unambiguous(self):
        t1=Tx([],[TxOut(1,MINER,"x;2|"+BOB+"|y")],coinbase=True,height=1)
        t2=Tx([],[TxOut(1,MINER,"x"),TxOut(2,BOB,"y")],coinbase=True,height=1)
        self.assertNotEqual(t1.txid(), t2.txid())
        self.assertNotEqual(Tx([],[TxOut(1,MINER,"")],True,1).txid(), Tx([],[TxOut(1,MINER,"")],True,2).txid())

    def test_sighash_is_network_specific(self):
        tx=Tx([TxIn("00"*32,0,"00"*32)],[TxOut(1,MINER,"")])
        self.assertNotEqual(tx.sighash(MAIN.magic), tx.sighash(REGTEST.magic))

class WalletTests(unittest.TestCase):
    def test_parse_amount(self):
        self.assertEqual(parse_amount("0.1"), 10_000_000)
        self.assertEqual(parse_amount(0.1), 10_000_000)
        self.assertEqual(parse_amount("21000000"), MAX_MONEY)
        for bad in ["0", "-1", "abc", "1e-9", "nan", "21000000.00000001"]:
            with self.assertRaises(ValueError): parse_amount(bad)

    def test_leaf_reserved_before_signing_and_no_self_conflict(self):
        with tempfile.TemporaryDirectory() as d:
            path=os.path.join(d,"w.json"); w=Wallet(path, h=6)
            c=Chain(params=P)
            grow(c, 2, w.address); grow(c, P.maturity, BOB)
            tx=w.send(c, BOB, "10", memo="hi")
            self.assertEqual(Wallet(path, h=6).key.next, 1)   # persisted
            self.assertTrue(c.add_mempool(tx)[0])
            tx2=w.send(c, BOB, "10")                          # must use the OTHER coin
            ok,m=c.add_mempool(tx2); self.assertTrue(ok, m)
            with self.assertRaises(RuntimeError): w.send(c, BOB, "10")   # nothing left that is free
            with self.assertRaises(ValueError): w.send(c, "BGCQ123", "1")

class NetworkTests(unittest.TestCase):
    def test_secure_socket_roundtrip_and_frame_limit(self):
        import bgc_secure as S
        a,b=socket.socketpair(); box={}
        t=threading.Thread(target=lambda: box.setdefault("b", S.SecureSocket(b, initiator=False))); t.start()
        sa=S.SecureSocket(a, initiator=True); t.join(5); sb=box["b"]
        sa.send(b"hello"*1000); self.assertEqual(sb.recv(), b"hello"*1000)
        a.sendall((S.MAX_FRAME+1000).to_bytes(4,"little"))
        with self.assertRaises(ConnectionError): sb.recv()
        a.close(); b.close()

    def test_two_nodes_sync_and_transfer(self):
        import run_miner as R
        with tempfile.TemporaryDirectory() as d:
            wa=Wallet(os.path.join(d,"a.json"), h=6); wb=Wallet(os.path.join(d,"b.json"), h=6)
            A=R.MinerNode("A", wa, os.path.join(d,"A"), 0, params=P, bind="127.0.0.1")
            B=R.MinerNode("B", wb, os.path.join(d,"B"), 0, params=P, bind="127.0.0.1")
            try:
                for _ in range(P.maturity+3):
                    ok,m,_=A.chain.add_block(child(A.chain, addr=wa.address)); self.assertTrue(ok, m)
                B.connect("127.0.0.1", A.port)
                self.assertTrue(wait(lambda: B.chain.tip()==A.chain.tip(), 20), "B did not sync")
                tx=wa.send(A.chain, wb.address, "7")
                self.assertTrue(A.submit_tx(tx)[0])
                self.assertTrue(wait(lambda: tx.txid() in B.chain.mempool, 10), "tx not relayed")
                B.start_mining()
                confirmed=lambda ch: ch.utxo.get((tx.txid(),0),(0,))[0]==7*COIN
                self.assertTrue(wait(lambda: confirmed(A.chain) and confirmed(B.chain), 60), "tx not confirmed")
                B.stop_mining(wait=True)
                self.assertTrue(wait(lambda: A.chain.tip()==B.chain.tip(), 20), "nodes did not converge")
            finally:
                A.close(); B.close()

class AppTests(unittest.TestCase):
    def test_wallet_api_requires_token_and_local_host(self):
        import bgc_app as APP, run_miner as R
        from http.server import ThreadingHTTPServer
        with tempfile.TemporaryDirectory() as d:
            w=Wallet(os.path.join(d,"w.json"), h=4)
            APP.NODE=R.MinerNode("T", w, os.path.join(d,"data"), 0, params=P, bind="127.0.0.1")
            srv=ThreadingHTTPServer(("127.0.0.1",0), APP.Handler); APP.WEB_PORT=srv.server_address[1]
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            def req(method, path, headers=None, body=None):
                c=http.client.HTTPConnection("127.0.0.1", APP.WEB_PORT, timeout=5)
                h={"Host":f"localhost:{APP.WEB_PORT}"}; h.update(headers or {})
                c.request(method, path, body=body, headers=h); r=c.getresponse(); return r.status, r.read()
            try:
                body=json.dumps({"to":BOB,"amount":"1"})
                self.assertEqual(req("POST","/api/send",{"Content-Type":"text/plain"},body)[0], 403)
                self.assertEqual(req("GET","/api/status")[0], 403)
                self.assertEqual(req("GET","/",{"Host":"evil.example"})[0], 403)
                st,page=req("GET","/"); self.assertEqual(st, 200)
                self.assertIn(APP.TOKEN.encode(), page)
                st,_=req("GET","/api/status",{"X-BGC-Token":APP.TOKEN}); self.assertEqual(st, 200)
                self.assertNotIn(b"innerHTML='<div><div>'+label", page)   # no HTML injection from memos
            finally:
                srv.shutdown(); srv.server_close(); APP.NODE.close()

def wait(cond, t):
    end=time.time()+t
    while time.time()<end:
        if cond(): return True
        time.sleep(0.1)
    return cond()

if __name__=="__main__":
    unittest.main(verbosity=2)
