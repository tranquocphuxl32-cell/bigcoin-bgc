#!/usr/bin/env python3
# =====================================================================
#  BGC test suite — runs the self-verifying demos and reports pass/fail.
#  Each demo exits 0 on success, non-zero on failure.
#  Usage:  python run_tests.py            (fast tests)
#          python run_tests.py --all      (also network tests, slower)
# =====================================================================
import os, sys, subprocess, time

HERE = os.path.dirname(os.path.abspath(__file__))

FAST = [
    ("test_bgc.py",              "Regression tests: consensus, wallet, P2P, wallet web API"),
    ("bgcfl_demo.py",            "Fair launch: no premine, permissionless mining, anti-inflation, reorg, PQ spend"),
    ("bgcfl_demo2.py",          "Fair-launch PoW: retarget + coinbase maturity + chainwork reorg + no premine"),
    ("bgc_job.py",               "HTLC escrow for AI/robot job settlement (quantum-safe)"),
    ("bgc_trao_doi.py",          "Two-party transfer: sign, confirm, fraud attempts rejected"),
    ("demo_2017_nha_giau_thua.py","Rich faction (more hashrate + rule change) rejected by user nodes"),
]
NETWORK = [
    ("bgcfl_net.py",             "Multi-miner encrypted P2P network converges on one chain"),
    ("bgc_trao_doi_mang.py",     "Two networked nodes exchange BGC both ways over encrypted P2P"),
]

def run(name, desc, timeout):
    path = os.path.join(HERE, name)
    if not os.path.exists(path):
        print(f"  SKIP  {name:28} (file not found)"); return None
    t0 = time.time()
    try:
        r = subprocess.run([sys.executable, path], cwd=HERE,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=timeout)
        ok = (r.returncode == 0); dt = time.time()-t0
        print(f"  {'PASS' if ok else 'FAIL'}  {name:28} {dt:5.1f}s  {desc}")
        if not ok and r.stderr:
            print("        " + r.stderr.decode(errors='replace').strip().splitlines()[-1][:120])
        return ok
    except subprocess.TimeoutExpired:
        print(f"  TIME  {name:28} (>{timeout}s)"); return False

def main():
    all_tests = "--all" in sys.argv
    print("="*72); print(" BGC TEST SUITE"); print("="*72)
    results = []
    for name, desc in FAST:
        results.append(run(name, desc, 120))
    if all_tests:
        print("  --- network tests (slower) ---")
        for name, desc in NETWORK:
            results.append(run(name, desc, 180))
    passed = sum(1 for r in results if r)
    total  = sum(1 for r in results if r is not None)
    print("="*72)
    print(f" RESULT: {passed}/{total} passed")
    print("="*72)
    return 0 if passed == total and total > 0 else 1

if __name__ == "__main__":
    sys.exit(main())
