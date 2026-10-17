# Deployment and verification record

## Corrected source status

A source review found a concrete resource-exhaustion path: any address could self-register against an admitted principal and occupy its agent slots without that principal's approval. The current repository source closes this path by requiring an address-specific principal approval, reserving bounded active-plus-pending slots, and allowing the principal or contract owner to cancel an unused approval. The corrected source file SHA-256 is `7fc5610a160d0094eac3158680fc93237e792a3cc6a9a30e60441e9fde7fb627`. Its regression coverage includes unauthorized Sybil registration, pending-approval cap and cancellation, policy-cap release, and expired proposal-slot reclamation.

This corrected source has **not** been deployed. The Studionet instance below is the pre-correction implementation and must not be used as proof for the new approval rules. A new deployment and its live acceptance suite are blocked by the unresolved primary signer nonce 2686 described below. No transaction was resubmitted and no source parity claim is made for the current repository source.

## Previous resource-lifecycle candidate deployment

The earlier resource-lifecycle candidate is deployed on Studionet at [`0x7d59607d8E42Cf20e6c6988DdfFe17514D11B4FB`](https://explorer-studio.genlayer.com/address/0x7d59607d8E42Cf20e6c6988DdfFe17514D11B4FB). Deployment transaction [`0x275ef9638bbaa495c20d9662e91780de30ab41d886b4374e7379fe8aafc63518`](https://explorer-studio.genlayer.com/tx/0x275ef9638bbaa495c20d9662e91780de30ab41d886b4374e7379fe8aafc63518) finalized with `MAJORITY_AGREE`, VM `SUCCESS`, one round, and 3 agree / 2 idle votes. That deployed file is byte-identical to `contracts/boundary_os.py` in source commit `6d0d9ddf5b916fa4fc27613e48718021a1cc97f9`; its exact source file SHA-256 is `77c07245b23c77cf7d6a286df92e4a3f99d0ffc89fefbe603e87c979ef5dfbc9`. Official GenLayer CLI 0.39.1 `code` retrieval exactly matched that historical source after removing the CLI result wrapper and surrounding newlines; the normalized deployed body hash is `05a1cde5cfe1b4c0a741791d7d98b2a53f4289bbf79beb9e8acff2f70a54ea5d`. This parity result applies only to commit `6d0d9dd`, not the corrected repository source.

The test-only consumer fixture is separately deployed at `0x4439B1c1Ab602ec780F6E6139ffb7868B3c8bfa6`; deployment transaction `0x525a11eee7fe9c36865de3f33617ebf4cae55b8d204d3ff3bba44c7a9096116d` finalized with `MAJORITY_AGREE` and VM `SUCCESS`. Its cross-contract lifecycle has not yet been exercised.

Read-only Python SDK calls at `LATEST_FINAL` confirmed primary-principal admission, registered/unfrozen agent state, policy ID `resume-a21840a30e6f`, policy instance `1`, and the exact expected policy terms. Three setup writes finalized: principal admission (`0x6d4486c01a0cd50dadd0f02565c8ea3252e535aec53f813c050db77fbffb0dcb`, nonce 2683), agent registration (`0x76bb11216f081fb95411578d3ca47b9fe453cafd30abc1039040c4d0dae9fabc`, nonce 2684), and policy creation (`0xead0a41df709a18e92babfe762c2e95f4ac2d618685c7255d1d304ef4d8bae7d`, nonce 2685); all finalized `MAJORITY_AGREE` with VM `SUCCESS`.

The next `authorize_consumer` attempt at primary signer nonce 2686 exited without a captured hash. Its checkpoint records `latest=2686` and `pending=2686`, but those values do not prove that no transaction was ever broadcast. Studionet returns `Method not found` for `txpool_content`, and the installed CLI exposes no history-by-signer-nonce lookup. The harness therefore leaves the intent unresolved and refuses another primary-signer write. A prior hashless consumer-fixture deployment intent at nonce 2683 was not finalized under its own identity; the later, different principal-admission transaction finalized at nonce 2683. Whether the first attempt was broadcast and later dropped or replaced is unknown. The cross-checkpoint nonce guard was added and unit-tested so separate checkpoint files cannot silently reuse unresolved signer nonces.

The previous cross-checkpoint guard passed [CI run 39010889911](https://github.com/Chinny070/BoundaryOS/actions/runs/39010889911) on commit `3d345b6bc152539d692925f07d21d592be6ea8e8`: 68 Linux tests, pinned GenVM lint/check/schema/typecheck, release configuration, and Windows helper checks. The current approval fix has passed local compile, GenVM lint (3 checks), SDK validation (31 methods: 10 views and 21 writes), schema, and typecheck. The local Windows Direct Mode attempt still fails before contract load because `gltest` unlinks a locked temporary file (`WinError 32`); helper tests pass locally. Current-source Direct Mode results are pending CI. The current source and the previous deployed candidate are not submission-ready for the same source because the new fix is not deployed, and no live acceptance behavior has been run against it. Full evidence and exact blocked intents are in [resource lifecycle candidate evidence](evidence/resource-lifecycle-candidate.json).

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

The prior frozen deployment has substantial documented live evidence, but the resource-lifecycle candidate is **not submission-ready**. Required remaining gates are the full candidate acceptance matrix, live state-reclamation regressions, successful delegated-child authorization/evaluation/receipt consumption, consumer child-error recovery and repeated completion, and CI confirmation of the cross-checkpoint nonce guard. The candidate deployment finality, source parity, and setup readbacks are verified; those facts do not substitute for the missing behavior tests. Caller-asserted evidence, unattributed historical signer nonce gaps, the earlier nonce-2624 uncertainty, and the current nonce-2686 unresolved attempt remain documented limitations.
