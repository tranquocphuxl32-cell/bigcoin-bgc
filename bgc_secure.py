#!/usr/bin/env python3
# =====================================================================
#  BGC SECURE - a BIP324-style ENCRYPTED P2P channel: ECDH (secp256k1) + HKDF-SHA256 +
#  ChaCha20-Poly1305. An eavesdropper cannot read or alter messages. Forward secrecy
#  (ephemeral session key per connection). Wraps a plain socket -> sends/receives encrypted frames.
#  NOTE: this encrypts the LINK with classical ECDH; if broken by a quantum computer it only
#  exposes network METADATA, NOT the coins (coin signatures are hash-based PQ). It can later be
#  upgraded to a post-quantum KEM (ML-KEM). AEAD cipher: self-written ChaCha20-Poly1305 (RFC8439).
# =====================================================================
import os, sys, struct, hmac, hashlib, socket, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from btclib import P, N, G, pmul, newkey   # secp256k1 cho ECDH

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

if __name__=="__main__":
    g,r=self_test()
    print("[bgc_secure] server nhan (giai ma):", g.decode())
    print("[bgc_secure] client nhan (giai ma):", r.decode())
    print("[bgc_secure] OK - kenh ECDH + ChaCha20-Poly1305 hoat dong" if g and r else "LOI")
