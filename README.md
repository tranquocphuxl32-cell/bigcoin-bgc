# Bigcoin (BGC) — a post-quantum cryptocurrency for the AI & robotics era

> **BGC: the post-quantum currency, born for the age of AI and robots.**

Bigcoin (BGC) is a from-scratch cryptocurrency, written in pure Python, that follows
Bitcoin's architecture (UTXO, Proof-of-Work, halving, 21M cap, longest-chain /
most-chainwork consensus) but adds two things Bitcoin does not have today:

- **Post-quantum signatures** — hash-based **XMSS** (NIST SP 800-208), so a future
  quantum computer cannot forge spends.
- **End-to-end encrypted peer-to-peer** transport (ECDH secp256k1 + HKDF-SHA256 +
  ChaCha20-Poly1305).

It also ships an **agentic / machine-to-machine settlement layer** (HTLC escrow) so
AI agents and humanoid robots can pay each other by result.

> ⚠️ **Status: learning / research prototype — NOT security-audited.** Difficulty and
> block-interval parameters are small for demonstration. Do **not** use with real value
> before re-tuning the parameters and getting a professional security audit. See
> [Honest limitations](#honest-limitations).

---

## Why

Bitcoin's ECDSA signatures are vulnerable to a sufficiently large quantum computer
(Shor's algorithm). Bitcoin will have to *fix* this later via a contentious migration.
BGC *avoids* the problem from genesis by using hash-based signatures, which only lose
half their security to Grover's algorithm (a doubling of the hash size restores it).

BGC is **not** a "Bitcoin killer" and makes no attempt to replace Bitcoin. It is an
honest exploration of what a quantum-resistant, fair-launch chain for machine economies
looks like.

---

## Features

- **Fair launch, no premine** — every coin is mined (Proof-of-Work). Permissionless.
- **21,000,000 cap** with Bitcoin-style **halving** emission.
- **Difficulty retarget**, **coinbase maturity**, and **fork-choice by chainwork** (reorg-safe).
- **XMSS post-quantum wallet** that persists its one-time-signature leaf index to disk
  before signing (prevents key reuse on restart).
- **Encrypted P2P** gossip; multiple independent miners converge on one chain.
- **HTLC escrow** (`bgc_job.py`) for pay-by-result AI/robot jobs.
- **One-file build** (`BGC_Miner_1file.py`) and a **browser control panel** (`bgc_app.py`)
  with multi-language UI (German / English / Vietnamese), address QR code, and transaction history.
- Pure Python standard library (only optional dependency: `qrcode`, for the QR feature).

---

## Quick start

Requires Python 3.9+. No installation needed for the core.

```bash
# 1) Mine with the browser app (opens a local control panel)
python bgc_app.py                     # solo mining
python bgc_app.py --peers IP:9333     # join a network

# 2) Or the single self-contained file (same features, one file to share)
python BGC_Miner_1file.py

# 3) Or the command-line miner
python run_miner.py                   # commands: bal | addr | send <addr> <amt> | peers | quit
```

The app auto-creates a wallet and a deterministic genesis block beside the program, then
mines into your wallet. Use the **Receive** panel (QR) to get your address and **Send** to
transfer BGC. All nodes must share the same `bgcfl_genesis.json` (it is generated
deterministically, so every machine agrees on block 0).

---

## How it works (and where it maps to Bitcoin Core)

| Component | File | Bitcoin Core equivalent |
|---|---|---|
| Transaction / block data types | `bigcoin_pq.py`, `bgcfl_engine.py` | `primitives/transaction.h`, `block.h` |
| Consensus rules (`_check_tx`, `_replay`) | `bgcfl_engine.py` | `consensus/tx_verify.cpp`, `validation.cpp` (`ConnectBlock`) |
| Post-quantum signatures (XMSS/WOTS+) | `bigcoin_pq.py` | `secp256k1/` (ECDSA — BGC replaces this) |
| Wallet + coin selection | `bgcfl_wallet.py` | `wallet/` |
| Encrypted transport | `bgc_secure.py` | `net.cpp` + BIP324 |
| P2P gossip & mining loop | `run_miner.py` | `net_processing.cpp`, `node/` |
| HTLC / machine settlement | `bgc_job.py` | Script `OP_CHECKLOCKTIMEVERIFY` + hashlocks |

Emission is identical in spirit to Bitcoin: `subsidy(height) = 50 >> (height // HALVING)`.

---

## Testing

The demos are self-verifying (exit 0 on success). Run the suite:

```bash
python run_tests.py          # fast tests
python run_tests.py --all    # also the slower encrypted-network tests
```

Each script can also be run on its own to watch the mechanism, e.g.
`python demo_2017_nha_giau_thua.py` shows that a richer faction with more hashrate and
changed rules is still rejected by honest nodes.

---

## Project structure

```
bigcoin_pq.py       XMSS post-quantum signatures + core primitives
btclib.py           secp256k1 helpers (used by the encrypted transport)
bgc_secure.py       encrypted P2P socket (ECDH + ChaCha20-Poly1305)
bgcfl_engine.py     fair-launch PoW engine: UTXO, retarget, maturity, chainwork
bgcfl_wallet.py     persistent quantum-resistant wallet
bgcfl_genesis.py    deterministic genesis block (unspendable coinbase = no premine)
run_miner.py        CLI miner / node
bgc_app.py          browser control panel (DE/EN/VI, QR, history)
BGC_Miner_1file.py  everything amalgamated into one file
bgc_job.py          HTLC escrow for AI/robot settlement
run_tests.py        test suite
```

---

## Honest limitations

- **Not audited.** This is a prototype for learning and demonstration.
- Demo parameters (difficulty, block interval, maturity depth) are small and **must be
  re-tuned** for any real network.
- Quantum resistance is at the **signature** layer (XMSS). The PoW hash (SHA-256) is only
  mildly affected by quantum computers (Grover halves security — not a break).
- A real, living network additionally needs stable seed nodes, defense against 51% attacks,
  and a large enough mining community.
- Nothing here is financial or legal advice.

---

## License

MIT — see [LICENSE](LICENSE).

## Author

Built by **Trần Quốc Phú** as the capstone of a hands-on Bitcoin study.
