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
| Deployment source SHA-256 fingerprint | `78e7623d7fa68828e0339bb668e976bb8b57b60f81dddd222ff0ca21f7043c16` (local source at run time; no on-chain source-parity proof) |
| Registration transaction | `0x27b06fae6e1d6192f6eacbb563da0b9e9c1ddfc2b79372ef45e5c3b9249787b2` — `FINALIZED`, `MAJORITY_AGREE` |
| Policy creation transaction | `0xecfd49ddefa1e3a7b3d033555d7bd3965b82c4c73e3e5840401f13e2e719387e` — `FINALIZED`, `MAJORITY_AGREE` |
| Consumer authorization transaction | `0x47a8261a9868c789e41dcdb9db5f3ab77fc867694381d6dc8bf6b75e75533f16` — `FINALIZED`, `MAJORITY_AGREE` |
| Live authorization / semantic-consensus transaction | None verified; action submission wait failed at the RPC |
| Live deterministic hard-denial transaction | None |
| Explorer URL | Not independently verified |
| Canonical deployment source commit | None |

The local environment currently has Python 3.12.10, `genlayer-test` 0.29.2, `genlayer-py` 0.16.3, `genvm-linter` 0.11.1rc2, and GenLayer CLI 0.40.0-rc.3. The contract header uses the runner SDK hash accepted by the cached SDK validation. The linter reports that a newer runner hash exists, but the sandbox could not extract that runner in the user cache (WinError 5); its current full validation therefore uses the cached runner. See the final report for the exact command output and limitation.

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

Run on 2026-10-13 with Python 3.12.10, `genlayer-test` 0.29.2, `genlayer-py` 0.16.3, `genvm-linter` 0.11.1rc2, and GenLayer CLI 0.40.0-rc.3:

| Command | Result |
|---|---|
| `python -m pytest tests/direct/ -q --tb=short` | **28 passed** |
| `python -m compileall -q contracts tests` | **Passed** |
| `genvm-lint check contracts/boundary_os.py --json` | **Passed:** 3 lint checks; SDK schema validation found 22 methods (8 views, 14 writes, no constructor args). Warning: a newer runner is available. |
| `genvm-lint typecheck contracts/boundary_os.py` | **Passed:** no type errors |
| `genvm-lint lint contracts/boundary_os.py` | **Passed:** 3 checks |
| `python -m pytest tests/integration/test_boundary_os_studionet.py -q -s --tb=short -p no:cacheprovider` | **Blocked:** four setup transactions finalized; later RPC calls failed with an RLP internal error / Cloudflare 502. No live action authorization or hard-denial pass. |

The current GenVM runner could not be extracted into the user cache due to Windows `WinError 5`; validation used the runner already cached for the pinned SDK hash. The linter's attempt to look up the latest version was also blocked by sandboxed network access. Do not describe this as validation against the latest runner.

The integration test deploys a **disposable** contract, creates an agent/policy/consumer, then tries a permitted action, live semantic evaluation, receipt consumption, and deterministic hard-deny case. On 2026-10-13 the disposable deployment and the first three setup writes finalized with `MAJORITY_AGREE`. The next `submit_action` attempt failed while polling because `https://studio.genlayer.com/api` returned a Cloudflare 502 HTML response to `eth_getTransactionByHash`. A preceding run also received `gen_call failed (code=-32603): RLP string ends with 309 superfluous bytes` for a read-only call. Therefore the live authorization, hard-denial, consumption, and receipt-read assertions have **not** passed. These failures are recorded as external RPC blockers, not contract success.

The deployment run used the local source whose SHA-256 fingerprint is listed above. The source was not fetched back from chain or independently compared, and no Explorer page was verified. The disposable address must not be presented as a canonical release deployment.

## Canonical deployment procedure

1. Commit and identify the exact contract blob to deploy.
2. Confirm the selected Studionet account, chain, signer address, and fee behavior without exposing private keys.
3. Deploy with the current official GenLayer CLI or Studio flow and record the outer EVM hash and GenLayer transaction ID separately.
4. Wait for `FINALIZED`; `ACCEPTED` is provisional.
5. Run finalized registration, policy creation, permitted evaluation, deterministic denial, consumer consumption, and revocation flows. Record each transaction ID and read the finalized state.
6. Retrieve deployed source/code through the official network API, compare it to the committed `contracts/boundary_os.py` bytes, and record the match.
7. Confirm the address page on the GenLayer Explorer and update the table above with direct evidence.

Do not mark a disposable test deployment canonical. Do not claim consensus from an accepted-only receipt or local simulation. The contract does not custody assets.
