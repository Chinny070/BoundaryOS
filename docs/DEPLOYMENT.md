# Deployment and verification record

## Current release candidate

BoundaryOS is deployed on GenLayer Studionet at [`0x99953d3c9e9c8FAff9289b9a80Ed038233Dc90eF`](https://explorer-studio.genlayer.com/address/0x99953d3c9e9c8FAff9289b9a80Ed038233Dc90eF).

| Evidence | Verified value |
|---|---|
| Network | Studionet, chain ID `61999` |
| Deployment transaction | [`0xa181e3932651e05ae55cadc559df4dfa9d67e1ab5ff17034e155d69cb4e47193`](https://explorer-studio.genlayer.com/tx/0xa181e3932651e05ae55cadc559df4dfa9d67e1ab5ff17034e155d69cb4e47193) |
| Finality | `FINALIZED`, `MAJORITY_AGREE`, VM `SUCCESS`, 1 round; 3 agree and 2 idle votes |
| Deployer | `my-studionet-wallet`, `0xaffE15eEc45b68835cc9E5B4Ab85dD5deaE8e70b` |
| Deployer nonce | `2694` |
| Deployment time | `2026-10-17T21:23:42.620703+01:00` |
| Frozen contract-source commit | `26af28d67decc2c20985f1c715bf85e389a88a86` |
| `contracts/boundary_os.py` SHA-256 | `7fc5610a160d0094eac3158680fc93237e792a3cc6a9a30e60441e9fde7fb627` |
| Deployed source parity | Official GenLayer CLI source retrieval matched the frozen source file after removing the CLI wrapper and outer newlines; SHA-256 checked independently. |
| Explorer | Address and transaction routes returned HTTP 200. The transaction page is client-rendered; finality and consensus fields were verified independently from CLI/RPC records. |

The canonical machine-readable record is [studionet-accessible-signer-release.json](evidence/studionet-accessible-signer-release.json). It contains the secret-free transaction list, scenario outcomes, finalized readbacks, and known limitations. Historical deployments remain in the other evidence files and are not evidence for this address.

## Live acceptance results

The release suite used GenLayer CLI `0.39.1`, the CLI-managed `my-studionet-wallet`, and the official Python SDK typed reads at `LATEST_FINAL`. Each write was reconciled to a transaction hash and finality before state readback.

| Check | Finalized result |
|---|---|
| Semantic match | `ALLOW / MATCH`; receipt read back and digest verified |
| Receipt use and replay | First consume succeeded; receipt became consumed, digest remained valid, and `can_consume` became false. Replay finalized with the expected VM error. |
| Semantic mismatch | `DENY_PURPOSE / MISMATCH` |
| Deterministic hard deny | `DENY_HARD_RULE / NOT_EVALUATED`; semantic evaluation was skipped |
| Delegation | Amount widening rejected; bounded root-to-child delegation succeeded; child action was `ALLOW / MATCH`; child receipt was consumed and its digest remained valid |
| Aggregate quota | Three actions were allowed within the cap; the next action was `DENY_AGGREGATE_CAP / NOT_EVALUATED` |
| Freeze | Action evaluated as `DENY_FROZEN / NOT_EVALUATED`; agent was subsequently unfrozen |
| Policy freshness/revocation | Old-version receipt became unusable after policy update; post-revocation action evaluated as `DENY_STALE_POLICY` |
| State | Principal and child registration, policy version 3, policy fields, receipts, consumption state, and digest checks read at `LATEST_FINAL` |

The transaction IDs, signer nonces, observed outcomes, action IDs, and readback details are in the JSON evidence. The tests exercise the BoundaryOS EOA receipt-consumption path and a delegated child lifecycle. They do not claim live coverage of the separate consumer fixture's error recovery/repeated completion or live on-chain saturation and reclamation at every storage cap; the fixture and local regression tests are documented separately.

## Local validation

- Harness helpers and consumer receipt-proof tests: **30 passed** on Windows.
- `python -m compileall -q contracts tests scripts`: passed.
- `python scripts/check_release_config.py`: passed.
- The contract-pinned GenVM `v0.2.16` lint, SDK validation, schema, and typecheck passed in the preceding verified run. The current CI run is linked from the repository Actions page after push.
- The local Windows Direct Mode runner fails before contract execution with `WinError 32` when `gltest` tries to unlink a temporary file still held open by stdin. No Windows security setting was changed. The full Direct Mode suite must be assessed from the Linux CI job, not this local failure.

## Reconciliation notes and limits

- During the live suite, the harness reserved signer nonce `2728`, while the CLI returned a transaction at nonce `2729`. The returned transaction hash was captured, finalized successfully, and its action state was read back. The nonce mismatch was not retried. The identity/payload of the consumed nonce `2728` is unknown; the harness preserves that uncertainty.
- An older consumer write at secondary signer nonce `441` on a predecessor deployment remains broadcast-unknown with no transaction hash. It was not retried. It is separate from this release: this deployment's EOA delegated receipt was successfully consumed and read back.
- Older nonce uncertainties and earlier deployment failures are retained in [studionet-canonical-release.json](evidence/studionet-canonical-release.json), [principal-approval-release.json](evidence/principal-approval-release.json), and [studionet-legacy-canonical-history.json](evidence/studionet-legacy-canonical-history.json). They are not relabeled as successful transactions on the current address.
- Evidence provenance is `CALLER_ASSERTED`. BoundaryOS does not independently authenticate external evidence or prove that an authorized real-world action occurred.

## Release verdict

**Submission-ready as a standalone Intelligent Contract release, with the limitations above disclosed.** The canonical source is deployed, finalized, source-parity checked, and the required authorization, denial, receipt, delegation, quota, freeze, and revocation scenarios have live consensus results and finalized readbacks. This verdict does not imply external-evidence verification or completion of the optional consumer-fixture and live cap-saturation scenarios.
