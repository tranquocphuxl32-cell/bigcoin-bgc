#!/usr/bin/env python3
# =====================================================================
#  BGC P2P v2 - mang ngang hang TCP, MA HOA kieu BIP324 (bgc_secure), fork-choice-aware.
#  Giao thuc (JSON tung ban tin, gui qua kenh ma hoa): hello | getblocks | blocks | tx | block
#  Moi ban tin = 1 khung ma hoa ChaCha20-Poly1305 -> ke nghe len khong doc/sua duoc.
# =====================================================================
import socket, threading, json, sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bgc_engine import Block, Tx
from bgc_secure import SecureSocket

class Peer:
    def __init__(s, sec): s.sec=sec
    def send(s, msg):
        try: s.sec.send(json.dumps(msg).encode())
        except Exception: pass

class P2P:
    def __init__(s, node, host="127.0.0.1", port=0, encrypted=True):
        s.node=node; s.enc=encrypted; s.peers=[]; s.lock=threading.Lock(); s.stop=False
        s.out_targets=set()   # (host,port) dang co ket noi ra -> chong noi trung khi reconnect
        s.srv=socket.socket(); s.srv.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        s.srv.bind((host,port)); s.port=s.srv.getsockname()[1]; s.srv.listen(8)
        threading.Thread(target=s._accept,daemon=True).start()
        threading.Thread(target=s._ticker,daemon=True).start()   # dong bo dinh ky -> hoi tu chac chan
    def _ticker(s):
        while not s.stop:
            time.sleep(0.3)
            s.broadcast({"t":"hello","h":s.node.chain.height()})
    def _accept(s):
        while not s.stop:
            try: c,_=s.srv.accept()
            except OSError: break
            threading.Thread(target=s._serve,args=(c,False),daemon=True).start()
    def connect(s, host, port):
        tgt=(host,int(port))
        with s.lock:
            if tgt in s.out_targets: return     # da co ket noi ra toi peer nay
            s.out_targets.add(tgt)
        try:
            c=socket.create_connection((host,port),timeout=3)
            threading.Thread(target=s._serve,args=(c,True,tgt),daemon=True).start()
        except OSError as e:
            with s.lock: s.out_targets.discard(tgt)
    def _serve(s, sock, initiator, tgt=None):
        try: sec=SecureSocket(sock, initiator=initiator) if s.enc else _Plain(sock)
        except Exception:
            if tgt:
                with s.lock: s.out_targets.discard(tgt)
            return
        p=Peer(sec)
        with s.lock: s.peers.append(p)
        p.send({"t":"hello","h":s.node.chain.height()})
        try:
            while not s.stop:
                msg=json.loads(sec.recv())
                s._on(p,msg)
        except Exception: pass
        with s.lock:
            if p in s.peers: s.peers.remove(p)
            if tgt: s.out_targets.discard(tgt)   # cho phep reconnect lai sau
    def broadcast(s,msg):
        with s.lock: ps=list(s.peers)
        for p in ps: p.send(msg)
    def _on(s,p,msg):
        t=msg.get("t")
        if t=="hello":
            if msg["h"]>s.node.chain.height(): p.send({"t":"getblocks","from":0})
            elif msg["h"]<s.node.chain.height(): p.send({"t":"blocks","b":[b.to_d() for b in s.node.chain.blocks]})
        elif t=="getblocks":
            p.send({"t":"blocks","b":[b.to_d() for b in s.node.chain.blocks[msg.get("from",0):]]})
        elif t=="blocks":
            for bd in msg["b"]: s.node.chain.add_block(Block.from_d(bd))
        elif t=="tx":
            ok,_=s.node.chain.add_mempool(Tx.from_d(msg["tx"]))
            if ok: s.broadcast(msg)
        elif t=="block":
            blk=Block.from_d(msg["b"]); before=s.node.chain.height()
            s.node.chain.add_block(blk)
            if s.node.chain.height()>before: s.broadcast(msg)          # tien len -> relay
            if s.node.chain.height() < blk.index+1:                    # thieu khoi cha -> xin dong bo
                p.send({"t":"getblocks","from":0})
    def close(s):
        s.stop=True
        try: s.srv.close()
        except OSError: pass
        with s.lock:
            for p in s.peers:
                try: p.sec.close()
                except Exception: pass

class _Plain:   # du phong khong ma hoa (chi de so sanh); mac dinh KHONG dung
    def __init__(s,sock): s.sock=sock; s.buf=b""
    def send(s,data):
        import struct; s.sock.sendall(struct.pack("<I",len(data))+data)
    def recv(s):
        import struct
        from bgc_secure import _recvn
        ln=struct.unpack("<I",_recvn(s.sock,4))[0]; return _recvn(s.sock,ln)
    def close(s):
        try: s.sock.close()
        except OSError: pass
