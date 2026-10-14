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
| Disposable action proposal | `0x64fe023e2f90c845a5e04054eabe2b3620f08b1b8cbd1f5afb57518ce807ecda` — `FINALIZED`; `submit_action`; sender nonce 4; 3 `agree`, 2 `idle`; validator execution `SUCCESS`; no leader VM error. Returned action ID: `8e591880333480e0ea2e0d0cec8c1e6aab43a916644ecf39770db92efe38b73ce`. Proposal recording only; no decision or ALLOW is implied. |
| Live semantic authorization / deterministic hard-denial transaction | None verified |
| Explorer evidence | [Studionet Explorer transaction search](https://explorer-studio.genlayer.com/txs?search=0x64fe023e2f90c845a5e04054eabe2b3620f08b1b8cbd1f5afb57518ce807ecda) displayed `FINALIZED` / GenVM `SUCCESS` / `Accepted`; direct RPC status returned `FINALIZED`. Detail page returned Cloudflare 502 during inspection. |
| Canonical deployment source commit | None |

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
python -m pytest tests/integration/test_boundary_os_studionet.py -q -s --tb=short -p no:cacheprovider
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
| `python -m pytest tests/integration/test_boundary_os_studionet.py -q -s --tb=short -p no:cacheprovider` | **Blocked before broadcast:** a fresh run remained idle for several minutes without output. It was stopped; public RPC showed both latest and pending signer nonce remained `0x5`, so no new test transaction was submitted. No live decision result is verified. |

The current GenVM runner could not be extracted into the user cache due to Windows `WinError 5`; validation used the runner already cached for the pinned SDK hash. The linter's latest-version lookup was blocked by sandboxed network access (`WinError 10013`). Do not describe this as validation against the latest runner. A first lint display also hit Windows cp1252 encoding; rerunning with `PYTHONIOENCODING=utf-8` passed all 3 checks.

The integration test uses a **disposable** contract. On 2026-10-13 its deployment, registration, policy creation, and consumer authorization finalized with `MAJORITY_AGREE`. The next `submit_action` was broadcast at sender nonce 4 and recovered from Studionet RPC and Explorer as `FINALIZED` with three `agree`, two `idle`, validator execution `SUCCESS`, and no leader VM error. The action ID is recorded above. This establishes proposal submission only. The earlier client poll saw Cloudflare 502 on `eth_getTransactionByHash`; a separate read-only SDK call returned `gen_call failed (code=-32603): RLP string ends with 309 superfluous bytes`. Evidence fits an RPC / SDK / client polling or read failure after the write; it does not establish a contract evaluation failure. On 2026-10-14 a new integration invocation stalled before broadcasting; latest and pending signer nonces remained `0x5`, so it did not duplicate any transaction. No semantic ALLOW, mismatch denial, receipt readback/consumption, replay rejection, revocation, delegation, or quota network pass is established. The Explorer address search showed the transaction; its detail page returned Cloudflare 502. No source-parity proof exists.

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
