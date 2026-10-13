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

> ⚠️ **Status: runnable network software, NOT security-audited.** The main network now uses
> Bitcoin-like parameters (10-minute blocks, 21M cap, 100-block maturity). Do **not** let
> anyone put real money into BGC before a professional security audit. See
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

- **Fair launch, no premine** — the built-in genesis block pays 0; every coin is mined (Proof-of-Work). Permissionless.
- **21,000,000 cap** with Bitcoin-style **halving** (50 BGC, halving every 210,000 blocks).
- **Per-block difficulty adjustment** (LWMA over 60 blocks, 10-minute target), **median-time-past**
  and future-time limits, **coinbase maturity** (100 blocks), and **fork-choice by chainwork**
  with undo-data reorgs.
- **XMSS post-quantum wallet** that reserves each one-time-signature leaf on disk *before*
  signing (a crash can skip a leaf, never reuse one).
- **Encrypted P2P** with locator-based block sync, frame-size limits and peer limits;
  multiple independent miners converge on one chain.
- **Wallet web panel** bound to `127.0.0.1`, protected by a per-run token and a Host check.
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

The app auto-creates a wallet beside the program and mines into it. Use the **Receive**
panel (QR) to get your address and **Send** to transfer BGC. The genesis block is built into
the code, so every machine agrees on block 0 without sharing any file.

To try things out without touching the real network, add `--regtest`: a private test
network with tiny difficulty and 5-block maturity (its coins are worthless by design).

### Running a public seed node

A network needs at least one always-on node that others can reach:

```bash
python run_miner.py --name seed1 --port 9333 --no-mine   # on a VPS with port 9333 open
python run_miner.py --peers SEED_IP:9333                 # everyone else
python bgc_explorer_server.py bgcfl_data 8800            # optional public block explorer
```

### Upgrading from the old prototype

Version 2 changes the consensus rules (serialization, genesis, parameters), so it starts a
**new chain**: delete the old `bgcfl_data/` folder. Wallet files (`my_bgc_wallet.json`) keep
working and keep the same address.

---

## How it works (and where it maps to Bitcoin Core)

| Component | File | Bitcoin Core equivalent |
|---|---|---|
| Transaction / block data types | `bigcoin_pq.py`, `bgcfl_engine.py` | `primitives/transaction.h`, `block.h` |
| Consensus rules (`_check_inputs`, `_connect`, `_activate`) | `bgcfl_engine.py` | `consensus/tx_verify.cpp`, `validation.cpp` (`ConnectBlock`, `ActivateBestChain`) |
| Difficulty (LWMA) and time rules | `bgcfl_engine.py` (`_target_after`, `_mtp`) | `pow.cpp`, `GetMedianTimePast` |
| Post-quantum signatures (XMSS/WOTS+) | `bigcoin_pq.py` | `secp256k1/` (ECDSA — BGC replaces this) |
| Wallet + coin selection | `bgcfl_wallet.py` | `wallet/` |
| Encrypted transport | `bgc_secure.py` | `net.cpp` + BIP324 |
| P2P gossip & mining loop | `run_miner.py` | `net_processing.cpp`, `node/` |
| HTLC / machine settlement | `bgc_job.py` | Script `OP_CHECKLOCKTIMEVERIFY` + hashlocks |

Emission is identical in spirit to Bitcoin: `subsidy(height) = 50 >> (height // HALVING)`.

---

## Testing

`test_bgc.py` holds the regression tests (double-spends, inflation, reorgs, malformed
blocks, timestamps, difficulty, persistence, sync, wallet safety, web-panel CSRF). The demos
are self-verifying too (exit 0 on success). Run everything:

```bash
python run_tests.py          # fast tests
python run_tests.py --all    # also the encrypted-network tests
```

After changing any module, rebuild the single-file miner with `python build_1file.py`.

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
bgcfl_genesis.py    prints the built-in genesis block (pays 0 = no premine)
run_miner.py        CLI miner / node (P2P sync, mining)
bgc_app.py          browser control panel (DE/EN/VI, QR, history)
bgc_explorer_server.py  public read-only block explorer
BGC_Miner_1file.py  everything amalgamated into one file (python build_1file.py)
bgc_job.py          HTLC escrow for AI/robot settlement
test_bgc.py         regression tests
run_tests.py        test suite runner
```

---

## Honest limitations

- **Not audited.** Consensus, cryptography and networking are hand-written Python. Get a
  professional audit before anyone holds BGC with real value.
- The XMSS/WOTS construction is simplified (no per-chain bitmasks) and is **not**
  interoperable with RFC 8391 XMSS.
- Each wallet can sign **4,096** transactions (h=12); after that, create a new wallet and move
  the coins. Never keep using an *old copy* of a wallet file — it would reuse one-time keys.
- The wallet file stores the seed **unencrypted**: protect the file and keep offline backups.
- No automatic peer discovery yet: nodes find each other through `--peers` seed addresses.
- Mining is pure Python (one CPU core). A miner written in C or for GPUs will dominate the
  hashrate, as on any small PoW chain; a young network is exposed to 51% attacks.
- Quantum resistance is at the **signature** layer (XMSS). The P2P link uses classical ECDH,
  and the PoW hash (SHA-256) loses only half its security to Grover — not a break.
- Nothing here is financial or legal advice; issuing a currency to the public can be
  regulated where you live.

---

## License

MIT — see [LICENSE](LICENSE).

## Author

Built by **Trần Quốc Phú** as the capstone of a hands-on Bitcoin study.
