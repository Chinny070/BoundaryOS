# Deployment and verification record

## Current candidate status

The last verified Studionet instance below remains a valid historical deployment record for its frozen source. The working-tree source now includes bounded principal admission and active-state reclamation to address lifetime state exhaustion. Those source changes have not been deployed, and the deployed instance does not have verified parity with this candidate. See [resource lifecycle candidate evidence](evidence/resource-lifecycle-candidate.json).

Current candidate verification is incomplete: the 18 resumable-harness helper tests pass; pinned GenVM lint/schema/typecheck pass. The Windows Direct Mode run fails before contract loading because `gltest` cannot unlink its locked temporary file (`WinError 32`). Linux CI run [39007250085](https://github.com/Chinny070/BoundaryOS/actions/runs/39007250085) reported 63 passed and four setup failures; run [39007541381](https://github.com/Chinny070/BoundaryOS/actions/runs/39007541381) reported 65 passed and two setup failures. Both failure sets have been corrected and another CI run is pending. Live delegation happy-path and consumer-composability tests have not been run on this candidate. This session has `CODEX_SANDBOX_NETWORK_DISABLED=1`, so no candidate deployment or Studionet writes were attempted. Do not use the current candidate as a release deployment until Direct Mode passes and the candidate's live source, consensus, and state readbacks are established.

## Last verified Studionet deployment

BoundaryOS is deployed on GenLayer Studionet at `0xb95a995A42E68455223DCC05403c98fDf40657FB`. This is the corrected source release; the predecessor at `0x6692eB74852dD1b56966ac7AdC0ACDDA4Fe074BF` remains historical and is not the current release target.

| Evidence | Verified value |
|---|---|
| Network | Studionet, chain ID `61999`, RPC `https://studio.genlayer.com/api` |
| Canonical contract | `0xb95a995A42E68455223DCC05403c98fDf40657FB` |
| Deployment transaction | `0x7238677bd99f6a1b8ecdda5fc7bf73c7e4e8c9b5dce88fee303ef4361b4a8268` |
| Deployment sender nonce | `2634` |
| Deployment status | `FINALIZED`, `MAJORITY_AGREE`, VM `SUCCESS`, one round; 3 agree and 2 idle votes |
| Frozen source commit | `df980984f752d2cf367743d4f0a458e8af5712e0` |
| `contracts/boundary_os.py` SHA-256 | `86720777484aea493439d960cb741639b2320f00d81bd790b3dc14ee547f0937` |
| Deployed source parity | Official GenLayer CLI 0.39.1 `code` retrieval matches the committed source text after removing only the CLI result wrapper and surrounding newlines. The normalized retrieved body SHA-256 is `d415b664f8b904b39dfd93115bfe39f95df5b87cff0323eb742d5d1d737ef627`; the repository file hash above includes its final newline. |
| Explorer | [Contract address](https://explorer-studio.genlayer.com/address/0xb95a995A42E68455223DCC05403c98fDf40657FB) and [deployment transaction](https://explorer-studio.genlayer.com/tx/0x7238677bd99f6a1b8ecdda5fc7bf73c7e4e8c9b5dce88fee303ef4361b4a8268). Both routes returned HTTP 200. The address-page HTML contained both identifiers. The transaction detail page was client-rendered and did not include the contract address in its static response; finality and validator votes were independently verified through CLI receipt and RPC. |

The canonical release was deployed through the existing CLI-backed resumable workflow. It was not relabeled from a disposable deployment. Deployed source was retrieved independently from the contract address; no redeployment was performed after verification.

## Live release verification

The full resumable suite completed on this canonical address. The suite checkpoint is local and Git-ignored; the committed secret-free, machine-readable evidence—including all 33 finalized scenario transactions, their validator votes and execution results—is [studionet-canonical-release.json](evidence/studionet-canonical-release.json).

| Scenario | Finalized state and readback |
|---|---|
| Setup | Agent registration, policy creation, and consumer authorization finalized successfully. |
| Semantic match | `ALLOW / MATCH`; action is `EVALUATED`; receipt digest valid; provenance `CALLER_ASSERTED`. |
| Receipt consumption | First consumption finalized; receipt is marked consumed by the authorized consumer and its digest remains valid after the state change. |
| Replay | Second consumption finalized with `MAJORITY_AGREE` and expected VM `ERROR`; consumed receipt remained consumed. |
| Semantic mismatch | `DENY_PURPOSE / MISMATCH`; action is `EVALUATED`; receipt digest valid. |
| Deterministic hard deny | `DENY_HARD_RULE / NOT_EVALUATED`; semantic evaluator was skipped. |
| Aggregate quota | Matching actions at 250 cents were allowed through the 1,000-cent cap. A further 1-cent action finalized `DENY_AGGREGATE_CAP / NOT_EVALUATED`. |
| Agent freeze | `DENY_FROZEN / NOT_EVALUATED`; final agent readback is registered and unfrozen after the smoke test cleanup. |
| Delegation boundary | Child request for 501 cents against the 500-cent parent bound finalized as the expected contract rejection; no child delegation record was created. |
| Policy freshness | A fresh version-two receipt was consumable before the version-three update and non-consumable after it. |
| Revocation | A pending action evaluated after policy revocation finalized `DENY_STALE_POLICY`; receipt digest valid. |

The full scenario state was independently reread through the official Python SDK at `LATEST_FINAL`. All tested actions read back as `EVALUATED`, all stored receipt digests recomputed correctly, the semantic-match receipt was consumed, the delegation record was absent, and the primary agent was registered and unfrozen. Evidence provenance remains caller asserted; the contract does not independently authenticate external evidence.

## Nonce reconciliation and harness correction

The first resumed quota run exposed a harness resume bug: the already-finalized fourth matching action had application nonce `6`, but a checkpoint interruption left `last_action_nonce` at `5`. The harness attempted a 1-cent proposal with the reused application nonce `6`; transaction `0x3ead924f2125e0658164a71d56d01247a4dcc129183efd32ca33c426523e9e1c` finalized with `MAJORITY_AGREE` and VM `ERROR`, and finalized reads found no action or receipt for that failed proposal. The harness now advances its application nonce high-water mark from every resumed action readback. It preserves a finalized failed attempt, verifies its action/receipt are absent, and derives a new action ID at nonce `7`. That fresh proposal and its evaluation finalized and read back as `DENY_AGGREGATE_CAP / NOT_EVALUATED`.

The earlier `quota_match_4.submit` intent reserved signer EVM nonce `2651`, while the transaction metadata showed actual nonce `2652`. Its sole known broadcast finalized successfully as transaction `0x539a74e1330bcc4416af1284d22d4cf8debc248669ec1b7702cd3b8d34c5b0e3`; the corresponding action exists at finalized state. It was not resent. Additional consumed primary-signer nonce values `2649`, `2662`, `2665`, `2667`, `2669`, and `2673` have no transaction hashes in the verification checkpoint, so their origin and payload are unknown. At the final read-only preflight, `latest=2674` and `pending=2674`; there was no pending signer transaction. All BoundaryOS release writes listed in the evidence file were individually reconciled by transaction hash and finalized. The cause of the unattributed nonce gaps is not claimed.

The predecessor's unresolved consume intent at nonce `2624` remains documented as historically ambiguous and was never resent. It pertains to the prior address, not this corrected canonical instance. See [predecessor evidence](evidence/studionet-legacy-canonical-history.json) and the full [historical deployment record](DEPLOYMENT_HISTORICAL.md).

## Local validation

Verified locally after the resumable nonce fix and finalized action-state readback:

| Check | Result |
|---|---|
| `python -m pytest tests/direct/ tests/integration/test_studionet_resume_helpers.py -q --tb=short` | **61 passed** |
| `python -m compileall -q contracts tests` | Passed |
| `genvm-lint lint contracts/boundary_os.py` | Passed, 3 checks |
| `genvm-lint check contracts/boundary_os.py --json` | Passed; 22 methods (8 views, 14 writes) |
| `genvm-lint schema contracts/boundary_os.py` | Passed; schema lists 22 methods |
| `genvm-lint typecheck contracts/boundary_os.py` | Passed; no type errors |
| `python scripts/check_release_config.py` | Passed |

For Windows, run the linter from the project release environment with `PYTHONIOENCODING=utf-8` and `GENVM_VERSION=v0.2.16`, the cached runner that matches the contract's pinned SDK. The unpinned newer runner extraction hits Windows `WinError 5`; the global `genvm-lint.exe` shim also points to an incomplete Python installation. No security protection was disabled. The pinned cached-runner checks above pass.

## Readiness

The prior frozen deployment has substantial documented live evidence, but the current source candidate is **not submission-ready**. The active state-isolation and reclamation changes require a successful Direct Mode run, live delegated-child authorization/consumption, live consumer-composability verification, fresh canonical deployment, finality, independent deployed-source parity, and representative finalized-state readback. Keep the old deployment and its evidence identified as the last verified release until these candidate gates pass. Caller-asserted evidence, unattributed signer nonce gaps, and predecessor nonce-2624 uncertainty remain documented limitations.
