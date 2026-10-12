#!/usr/bin/env python3
# =====================================================================
#  BGC-JOB - A SETTLEMENT LAYER FOR AI / HUMANOID-ROBOT WORK (M2M escrow)
#  Ties BGC to AI+robot development: a human (or AI) HIRES a robot and LOCKS BGC into a
#  conditional escrow. When the robot finishes, it reveals PROOF (the preimage of a
#  hashlock = the signed work result) -> it is paid automatically. If the job is not done
#  before the deadline, the requester refunds itself. No intermediary holds the funds.
#  Signatures are POST-QUANTUM. This is an HTLC (hash-time-locked contract) applied to a
#  machine economy.
# =====================================================================
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bigcoin_pq import XmssKey, H, xmss_verify, addr_of
COIN=100_000_000

class Escrow:
    """A conditional BGC lock: pay the worker if they reveal the preimage (proof of completion),
       or refund the requester after the deadline."""
    def __init__(s, value, hashlock, worker, requester, deadline):
        s.value=value; s.hashlock=hashlock; s.worker=worker; s.requester=requester; s.deadline=deadline
    def msg(s, who): return H(b"BGC-escrow"+f"{s.value}|{s.hashlock.hex()}|{s.worker}|{s.requester}|{s.deadline}|{who}".encode())

def claim_by_worker(esc, preimage, worker_root, sig, height):
    """Worker gets paid: must reveal the correct preimage (proof) + sign as the worker."""
    if H(preimage)!=esc.hashlock: return False,"wrong preimage (completion not proven)"
    if addr_of(worker_root)!=esc.worker: return False,"not the worker"
    if not xmss_verify(worker_root, esc.msg("worker"), sig): return False,"bad worker signature"
    return True,f"worker receives {esc.value/COIN} BGC (completion proven)"

def refund_requester(esc, req_root, sig, height):
    """Requester refunds: only after the deadline (robot did not finish)."""
    if height<esc.deadline: return False,f"before deadline (deadline block {esc.deadline}, now {height})"
    if addr_of(req_root)!=esc.requester: return False,"not the requester"
    if not xmss_verify(req_root, esc.msg("refund"), sig): return False,"bad requester signature"
    return True,f"requester refunds {esc.value/COIN} BGC (expired, job not done)"

def main():
    print("="*74); print(" BGC-JOB - AI/ROBOT work settlement via escrow (HTLC), post-quantum"); print("="*74)

    human=XmssKey(h=8); ai=XmssKey(h=8); robot=XmssKey(h=8)   # human, AI coordinating agent, humanoid robot
    HU,AIa,RB=addr_of(human.root),addr_of(ai.root),addr_of(robot.root)
    print(f"\n[1] Agents (each one has its own POST-QUANTUM wallet):")
    print(f"    Human    : {HU[:26]}..")
    print(f"    AI agent : {AIa[:26]}..  (takes the job, coordinates the robot)")
    print(f"    Robot    : {RB[:26]}..  (humanoid robot doing the physical work)")

    # --- scenario: the human hires a robot to "move boxes", pays 20 BGC ---
    # "proof of completion" = the signed work result (e.g. a hash of the sensor log / photo after the job).
    # preimage = a secret that ONLY the robot can produce once it truly finishes (e.g. signing the acceptance report).
    proof_secret=os.urandom(32)                       # robot generates this on completion
    hashlock=H(proof_secret)                          # published in advance in the escrow
    deadline=100
    esc=Escrow(20*COIN, hashlock, RB, HU, deadline)
    print(f"\n[2] The HUMAN locks 20 BGC into escrow:")
    print(f"    condition: robot reveals 'proof of completion' (preimage) -> receives 20 BGC;")
    print(f"               if not done by block {deadline} -> the human refunds itself.")
    print(f"    hashlock (public) = {hashlock.hex()[:24]}..")

    print(f"\n[3] CASES:")
    # (a) robot finishes -> reveals preimage + signs -> gets paid
    sigW=robot.sign(esc.msg("worker"))
    ok,m=claim_by_worker(esc, proof_secret, robot.root, sigW, height=50)
    print(f"    (a) robot finishes, submits proof + signs -> {'PAID' if ok else 'REJECTED'}: {m}")
    # (b) someone tries to claim without proof
    ok2,m2=claim_by_worker(esc, os.urandom(32), robot.root, sigW, height=50)
    print(f"    (b) submits FAKE proof (wrong preimage) -> {'PAID' if ok2 else 'REJECTED'}: {m2}")
    # (c) someone has the preimage but is not the worker
    other=XmssKey(h=6)
    ok3,m3=claim_by_worker(esc, proof_secret, other.root, other.sign(esc.msg("worker")), height=50)
    print(f"    (c) someone else has the proof but is not the hired robot -> {'PAID' if ok3 else 'REJECTED'}: {m3}")
    # (d) early refund (before deadline) -> rejected
    sigR=human.sign(esc.msg("refund"))
    ok4,m4=refund_requester(esc, human.root, sigR, height=50)
    print(f"    (d) human asks for an EARLY refund (before deadline) -> {'REFUNDED' if ok4 else 'REJECTED'}: {m4}")
    # (e) robot does not finish -> after the deadline the human refunds
    ok5,m5=refund_requester(esc, human.root, sigR, height=120)
    print(f"    (e) robot does NOT finish, after deadline -> human {'REFUNDED' if ok5 else 'REJECTED'}: {m5}")

    print(f"\n[4] WHY THIS TIES TO AI/ROBOTS:")
    print(f"    - Each AI agent / robot = a self-custodial, self-signing (post-quantum) wallet -> a machine identity.")
    print(f"    - Escrow = a machine-to-machine 'labor contract': pay BY RESULT, no trust up front.")
    print(f"    - 'Proof of completion' could be: a signed acceptance report, a hash of a sensor log,")
    print(f"      a hash of an AI inference result... the robot is paid only when it TRULY finishes.")
    print(f"    - Multi-layer chains: Human -> AI agent (escrow) -> robot (sub-escrow) -> charging station...")
    print(f"      each layer an atomic escrow, no intermediary. This is the 'agentic economy'.")

    print("\n"+"="*74); print(" CONCLUSION")
    print("  - BGC-JOB turns BGC into a SETTLEMENT LAYER for AI/robot work: pay by result,")
    print("    on-chain proof, post-quantum, no third party holding the funds.")
    print("  - Unlike BTC: BTC has no machine identity + a compact M2M escrow, and is NOT post-quantum.")
    print("  *** HONEST NOTE ***")
    print("  - 'Proof of completion' is only as strong as HOW it is produced: the preimage must be")
    print("    tightly bound to the work (e.g. an oracle/signed acceptance), else a robot could reveal")
    print("    the preimage without doing the work. -> needs a device oracle/attestation; a real-world")
    print("    problem not fully solved here.")
    print("  - This is a prototype; it does not yet defend every kind of collusion (e.g. robot & hirer colluding).")
    print("="*74)
    ok_all = ok and (not ok2) and (not ok3) and (not ok4) and ok5
    return 0 if ok_all else 1

if __name__=="__main__": sys.exit(main())
