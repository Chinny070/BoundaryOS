# Deployment and verification record

## Network target

The intended canonical target is GenLayer Studionet (chain ID `61999`, RPC `https://studio.genlayer.com/api`). This file records only evidence actually produced. The network run below was a disposable integration instance, not a canonical release deployment.

## Current record

| Evidence | Status |
|---|---|
| Canonical Studionet contract address | None; release deployment not performed |
| Canonical deployment transaction | None |
| Disposable Studionet contract | `0xe5bcECDE0F002E78fa6A9271519d42e81D643d94` |
| Disposable deployment transaction | `0x9597081e8e9a19a8683f2f0fdfe003b3be83ca48636687c929b9eb9adad8c51b` — `FINALIZED`, `MAJORITY_AGREE` |
| Deployment source SHA-256 fingerprint | `78e7623d7fa68828e0339bb668e976bb8b57b60f81dddd222ff0ca21f7043c16` (local source at run time; no on-chain source-parity proof; predates receipt-digest fix now in source) |
| Current source SHA-256 fingerprint | `B957B969BDB9B605F5DDC70AB3A3D62BEF6DD1DE15ECA6A61CD4E43DF5E94888` (working source 2026-10-14; not deployed) |
| Registration transaction | `0x27b06fae6e1d6192f6eacbb563da0b9e9c1ddfc2b79372ef45e5c3b9249787b2` — `FINALIZED`, `MAJORITY_AGREE` |
| Policy creation transaction | `0xecfd49ddefa1e3a7b3d033555d7bd3965b82c4c73e3e5840401f13e2e719387e` — `FINALIZED`, `MAJORITY_AGREE` |
| Consumer authorization transaction | `0x47a8261a9868c789e41dcdb9db5f3ab77fc867694381d6dc8bf6b75e75533f16` — `FINALIZED`, `MAJORITY_AGREE` |
| Disposable action proposal | `0x64fe023e2f90c845a5e04054eabe2b3620f08b1b8cbd1f5afb57518ce807ecda` — `FINALIZED`; `submit_action`; sender nonce 4; 3 `agree`, 2 `idle`; validator execution `SUCCESS`; no leader VM error. Correct 64-character action ID, recomputed from the finalized transaction calldata and read from finalized state: `08e59188033480e0ea2e0d0cec8c1eaab43a916644ecf39770db92efe38b73ce`. The previously transcribed 65-character ID was invalid. |
| Existing proposal state | `PENDING`, nonce 1, submitted `2026-10-13T00:36:52Z`, expires `2026-10-13T00:46:52Z`; inspected `2026-10-14T20:31:48Z`, therefore expired. `get_receipt` returned empty. It has not been evaluated. |
| Live semantic authorization / deterministic hard-denial transaction | None verified |
| Explorer evidence | [Studionet Explorer transaction search](https://explorer-studio.genlayer.com/txs?search=0x64fe023e2f90c845a5e04054eabe2b3620f08b1b8cbd1f5afb57518ce807ecda) displayed `FINALIZED` / GenVM `SUCCESS` / `Accepted`; direct RPC status returned `FINALIZED`. Detail page returned Cloudflare 502 during inspection. |
| Canonical deployment source commit | None |

The machine-readable inspection output is committed at [docs/evidence/studionet-reconciliation.json](evidence/studionet-reconciliation.json). It includes no private keys or action text. The persistent local checkpoint at `.boundaryos/studionet-checkpoint.json` is ignored by Git; it is safe to retain locally and can be continued with the harness.

Cross-repository procedure review and current-environment root-cause findings are in [Reference deployment-path analysis](REFERENCE_DEPLOYMENT_ANALYSIS.md). The existing Windows GenLayer CLI profile selects the named wallet `my-studionet-wallet`, but the CLI cannot initialize its profile in this Codex sandbox because its required `.genlayer` directory `chmod` receives `EPERM`. The CLI wallet keystore was not read or exported. The separate RPC probe is blocked before HTTP by sandbox network policy (`CODEX_SANDBOX_NETWORK_DISABLED=1`, `WinError 10013`).

The local environment has Python 3.12.10, `genlayer-test` 0.29.2, `genlayer-py` 0.16.3, and `genvm-linter` 0.11.1rc2. The contract header uses the runner SDK hash accepted by cached SDK validation. The linter reports a newer runner hash, but network lookup is blocked (`WinError 10013`); prior extraction into the user cache failed with `WinError 5`. Current full validation therefore uses the cached runner. No latest-runner validation is claimed.

## Reproduce

Install the pinned test/lint dependencies, run Direct Mode and linter checks, then run the real integration test:

```powershell
python -m pip install -r requirements.txt
$env:PYTHONIOENCODING = 'utf-8'
python -m pytest tests/direct/ -q --tb=short
python -m compileall -q contracts tests
genvm-lint lint contracts/boundary_os.py
genvm-lint check contracts/boundary_os.py --json
genvm-lint typecheck contracts/boundary_os.py
python tests/integration/studionet_resume.py --contract 0xe5bcECDE0F002E78fa6A9271519d42e81D643d94 --inspect-existing
# Reconcile one named previously checkpointed write without sending anything:
python tests/integration/studionet_resume.py --resume-step setup.create_policy --contract 0xYOUR_CONTRACT
# Explicitly opt in to diagnostic live writes after stable primary and child
# signers are configured locally; this command does not deploy.
$env:BOUNDARYOS_RUN_LIVE_SUITE = '1'
python tests/integration/studionet_resume.py --run-live-suite --contract 0xYOUR_DISPOSABLE_CONTRACT
```

## Local validation record

Run on 2026-10-14 with Python 3.12.10, `genlayer-test` 0.29.2, `genlayer-py` 0.16.3, and `genvm-linter` 0.11.1rc2:

| Command | Result |
|---|---|
| `python -m pytest tests/direct/ -q` | **28 passed** after receipt-digest fix |
| `python -m compileall -q contracts tests` | **Passed** |
| `genvm-lint check contracts/boundary_os.py` | **Passed:** SDK schema validation found 22 methods (8 views, 14 writes, no constructor args). Newer runner lookup blocked by network restrictions. |
| `genvm-lint typecheck contracts/boundary_os.py` | **Passed:** no type errors |
| `genvm-lint lint contracts/boundary_os.py` | **Passed:** 3 checks |
| `python tests/integration/studionet_resume.py --contract 0xe5bcECDE0F002E78fa6A9271519d42e81D643d94 --inspect-existing` | **Passed (read-only):** chain 61999; proposal transaction `FINALIZED`, execution `SUCCESS`; correct action read as `PENDING` but expired; receipt absent. |
| `python -m pytest tests/direct/ tests/integration/test_studionet_resume_helpers.py -q --tb=short` | **33 passed** after adding resume-mode argument safety coverage. |
| `python -m pytest tests/integration/test_boundary_os_studionet.py -q -s --tb=short -p no:cacheprovider` | **Skipped on 2026-10-14 after five bounded transport retries:** `eth_chainId` raised connection failure. Wrapper identifies this as infrastructure unavailable; no writes were made. |
| Read-only `eth_chainId` probe on 2026-10-15 | **Blocked before HTTP response:** Windows `WinError 10013`; process environment reports `CODEX_SANDBOX_NETWORK_DISABLED=1`. No write was attempted. |
| `python -m pytest tests/integration/test_boundary_os_studionet.py -q -s --tb=short -p no:cacheprovider` | **1 skipped on 2026-10-15** after five bounded transport retries; same sandbox socket failure, no transaction broadcast. |
| `python tests/integration/studionet_resume.py --run-live-suite` | **Blocked before write:** stable signer and child signer configuration are not present in `gltest.config.yaml`; the default test accounts are ephemeral per process. The harness refuses to broadcast without stable local keys. |

Harness controls: transaction calls retry transient 408/425/429/5xx and request failures with bounded attempts/backoff; each step records a secret-free intent before signing and saves the outer EVM hash immediately after SDK broadcast, then persists the GenLayer ID before polling. On resume, known IDs are reconciled with status/state; if only the outer hash was saved, the harness fetches its receipt and decodes the SDK's `NewTransaction` event. It refuses to resend an intent when broadcast state is unknown and checks latest/pending nonces before each new write. `--resume-step` is reconciliation-only. Machine-readable historic evidence is in `docs/evidence/studionet-reconciliation.json`; active checkpoints remain local and Git-ignored.

The current GenVM runner could not be extracted into the user cache due to Windows `WinError 5`; validation used the runner already cached for the pinned SDK hash. The linter's latest-version lookup was blocked by sandboxed network access (`WinError 10013`). Do not describe this as validation against the latest runner. A first lint display also hit Windows cp1252 encoding; rerunning with `PYTHONIOENCODING=utf-8` passed all 3 checks.

The integration test uses a **disposable** contract. On 2026-10-13 its deployment, registration, policy creation, and consumer authorization finalized with `MAJORITY_AGREE`. The next `submit_action` was broadcast at sender nonce 4 and recovered from Studionet RPC and Explorer as `FINALIZED` with three `agree`, two `idle`, validator execution `SUCCESS`, and no leader VM error. Read-only `gen_call` confirmed its correct action ID is `08e59188033480e0ea2e0d0cec8c1eaab43a916644ecf39770db92efe38b73ce`; the earlier 65-character transcription was wrong. The action is still stored as `PENDING` but its ten-minute deadline elapsed on 2026-10-13, and no receipt exists. An invalid-ID `get_action` returns a contract execution error (`action_id exceeds its byte limit`); the corrected ID succeeds through the pinned SDK and raw RPC. This is evidence that the reported RLP issue may have been triggered by decoding the invalid-input error; that exact historical stack was not reproduced. The Cloudflare 502 during polling remains a distinct transport interruption after a successful broadcast. The proposal has not been evaluated because the original agent signer is not present in the current stable local signer configuration.


The default `gltest-test` configuration generates temporary accounts when `gltest.config.yaml` has no explicit Studionet signer. A fresh process produced a different default address, so a new persistent run cannot safely continue a write sequence. The harness therefore requires a stable signer supplied locally as `BOUNDARYOS_STUDIONET_PRIVATE_KEY` (or an explicit `networks.studionet.from`) and a stable secondary signer via `BOUNDARYOS_STUDIONET_CHILD_PRIVATE_KEY` (or `networks.studionet.accounts`). These values must remain local and must not be committed. The installed official CLI profile does have an active named account `my-studionet-wallet`, but its CLI cannot initialize the profile inside this sandbox and the Python SDK cannot consume that protected CLI wallet without importing signing material. The read-only inspector does not require stable signers when Studionet is reachable. In this session RPC access failed before HTTP with `WinError 10013`; the live run stopped before any transaction broadcast. This differs from the historical Cloudflare 502 response and is not a contract failure. An explicit `--rpc-url` can select another currently documented Studionet endpoint only after confirming it is chain 61999; the harness does not accept a different chain.

The deployment run used the local source whose SHA-256 fingerprint is listed above. The source was not fetched back from chain or independently compared. The Explorer transaction search listing was verified, but the transaction detail page returned 502 and no deployed-source parity was verified. The disposable address must not be presented as a canonical release deployment.

## Canonical deployment procedure

1. Commit and identify the exact contract blob to deploy.
2. Confirm the selected Studionet account, chain, signer address, and fee behavior without exposing private keys.
3. Deploy with the current official GenLayer CLI or Studio flow and record the outer EVM hash and GenLayer transaction ID separately.
4. Wait for `FINALIZED`; `ACCEPTED` is provisional.
5. Run finalized registration, policy creation, permitted evaluation, deterministic denial, consumer consumption, and revocation flows. Record each transaction ID and read the finalized state.
6. Retrieve deployed source/code through the official network API, compare it to the committed `contracts/boundary_os.py` bytes, and record the match.
7. Confirm the address page on the GenLayer Explorer and update the table above with direct evidence.

Do not mark a disposable test deployment canonical. Do not claim consensus from an accepted-only receipt or local simulation. The contract does not custody assets.
