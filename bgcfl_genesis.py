#!/usr/bin/env python3
# =====================================================================
#  BGC-FL GENESIS - creates the CANONICAL block 0 (shared by EVERY machine).
#  Like Bitcoin: everyone must start from the SAME genesis block to be on the same
#  network. This block is "mined" once and saved to bgcfl_genesis.json; everyone uses
#  that exact file. The genesis coinbase goes to an UNSPENDABLE address (hashed from the
#  message) -> NO premine, nobody gets a head start.
#  Usage: python bgcfl_genesis.py   -> writes bgcfl_genesis.json
# =====================================================================
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bigcoin_pq import H
from bgcfl_engine import Block, Tx, TxOut, mine, subsidy, GENESIS_TARGET, COIN

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

def main():
    out = sys.argv[1] if len(sys.argv)>1 else "bgcfl_genesis.json"
    blk = build()
    json.dump(blk.to_d(), open(out,"w"))
    print("="*70)
    print(" BGC-FL GENESIS created (block 0, shared by every machine)")
    print("="*70)
    print(f"  file      : {out}")
    print(f"  hash      : {blk.hash()}")
    print(f"  nonce     : {blk.nonce}")
    print(f"  coinbase  : {subsidy(0)/COIN:g} BGC -> {BURN[:40]}.. (UNSPENDABLE)")
    print(f"  message   : {MSG}")
    print("  => Everyone uses THIS exact file as the starting point (no premine).")
    return 0

if __name__=="__main__": sys.exit(main())
