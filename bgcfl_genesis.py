#!/usr/bin/env python3
# =====================================================================
#  BGC-FL GENESIS - shows the CANONICAL block 0 (shared by EVERY machine).
#  Like Bitcoin: everyone must start from the SAME genesis block to be on the same
#  network. The block is hard-coded in bgcfl_engine.make_genesis(), so no file needs to
#  be shared. The genesis coinbase pays 0 BGC to an address whose key nobody knows
#  -> NO premine, nobody gets a head start.
#  Usage: python bgcfl_genesis.py [--regtest] [out.json]   -> prints (and optionally saves) block 0
# =====================================================================
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bgcfl_engine import make_genesis, MAIN, REGTEST, GENESIS_MSG, COIN

def build(params=MAIN):
    return make_genesis(params)

def main():
    args=[a for a in sys.argv[1:] if a!="--regtest"]
    params=REGTEST if "--regtest" in sys.argv else MAIN
    blk=build(params)
    if args:
        with open(args[0],"w") as f: json.dump(blk.to_d(), f)
    cb=blk.txs[0].vout[0]
    print("="*70)
    print(f" BGC-FL GENESIS ({params.name}) - block 0, shared by every machine")
    print("="*70)
    if args: print(f"  file      : {args[0]}")
    print(f"  hash      : {blk.hash()}")
    print(f"  coinbase  : {cb.value/COIN:g} BGC -> {cb.address[:40]}.. (UNSPENDABLE)")
    print(f"  message   : {GENESIS_MSG}")
    print("  => Built into the code: every node starts from THIS block (no premine).")
    return 0

if __name__=="__main__": sys.exit(main())
