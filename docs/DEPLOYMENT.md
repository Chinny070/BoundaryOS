# Deployment and verification record

## Current corrected-source deployment

The principal-approved registration correction is deployed on GenLayer Studionet. The canonical release candidate is [`0xe6b915d1DAb0EC9035D07368938413798d77c959`](https://explorer-studio.genlayer.com/address/0xe6b915d1DAb0EC9035D07368938413798d77c959). This is a fresh deployment of the corrected source, not a relabeling of a historical instance.

| Evidence | Verified value |
|---|---|
| Network | Studionet, chain ID `61999` |
| Contract | `0xe6b915d1DAb0EC9035D07368938413798d77c959` |
| Deployment transaction | [`0xbb04d21b3d0784a2c61fcaedc0b83635571118ba1d18b5a59654d041df457eec`](https://explorer-studio.genlayer.com/tx/0xbb04d21b3d0784a2c61fcaedc0b83635571118ba1d18b5a59654d041df457eec) |
| Signer nonce | `419` |
| Finality | `FINALIZED`, `MAJORITY_AGREE`, VM `SUCCESS`, one round, five agree votes |
| Contract source commit | `03447b9ba09bced9ab151bc7212b423d7bcd8c82` |
| Contract file SHA-256 | `7fc5610a160d0094eac3158680fc93237e792a3cc6a9a30e60441e9fde7fb627` |
| Deployed source parity | Retrieved with GenLayer CLI `code`; normalized deployed source matched the committed contract text byte-for-byte after removing the CLI result wrapper and outer newlines. Normalized retrieved body SHA-256: `abc1144c5614e4704e3948225a00d298f855f9f76843d7ca8c255a9493c898d3`. |
| Explorer | Address and transaction routes returned HTTP 200. The address page included the contract and deployment transaction. The transaction page's static HTML did not include the contract address; finality and source parity were verified independently through CLI/RPC. |

The test-only consumer fixture is deployed at [`0x1efcCe3dFA92abdcd5887ceF8956cd63F7d816f5`](https://explorer-studio.genlayer.com/address/0x1efcCe3dFA92abdcd5887ceF8956cd63F7d816f5). Its deployment transaction is `0xb78ed578e912103cbb9561c2bf6d02bef8da27c147625a9c1ac3edd3598005db`, finalized with `MAJORITY_AGREE` and VM `SUCCESS`. Its source SHA-256 is `850e271a6ad274551183484b5a219eb8130322bb3070cab70cce5dd6e3f8ecbc`.

The full secret-free transaction and scenario record is [principal-approval-release.json](evidence/principal-approval-release.json). Local checkpoint files remain Git-ignored.

## Live verification on the corrected deployment

The workflow used GenLayer CLI `0.39.1` with named-wallet signing and official Python SDK typed state reads at `LATEST_FINAL`. Every listed transaction was reconciled to a transaction ID and finalized before its state was read.

| Scenario | Verified result |
|---|---|
| Principal admission and address-specific agent approval | Finalized successfully; approved agent registration and policy creation read back at `LATEST_FINAL`. |
| Semantic match | Action `2cfd960294c83457578b2ae0ca94811786b247d6391633927b553325ec5137dd` evaluated as `ALLOW / MATCH`; receipt digest verified. |
| Receipt use and replay | First `consume_authorization` finalized and read back consumed, with a valid recomputed digest. A second consumption finalized with expected VM `ERROR`; the consumed receipt remained consumed. |
| Semantic mismatch | Action `07ae010a2eb7b146b5d108a860c7243f5d4d8d546f096705643e8ffdd0e0143e` evaluated as `DENY_PURPOSE / MISMATCH`; receipt digest verified. |
| Deterministic hard denial | Action `96f5ffb8698c2e86a05b20055e396e7b72aec0cd504a1e9c66b689b08c1e5159` evaluated as `DENY_HARD_RULE / NOT_EVALUATED`; semantic evaluation was skipped. |
| Delegation boundary | A request to widen the parent amount bound finalized as expected VM `ERROR`; a bounded delegation finalized successfully. |
| Delegated child proposal and evaluation | The consumer fixture registered as the child agent, submitted a delegated action, and invoked its evaluation. Both internal child transactions finalized. Independent finalized-state readback showed the child action as `ALLOW / MATCH` with a valid receipt digest. |

The child receipt was **not consumed**. The harness's consumer `request_protected_operation` write at signer nonce `441` exited with code `1` without returning a transaction hash. The checkpoint records `phase=broadcast_unknown`. This attempt may have been broadcast; it is not classified as dropped or never submitted.

Reconciliation did not establish a transaction identity. The RPC returned `Method not found` for `txpool_content`, `eth_pendingTransactions`, and `txpool_status`; the installed CLI does not provide transaction lookup by signer and nonce. `latest=441` and `pending=441` do not prove non-broadcast. The Explorer account activity view did not show this method, but it does not expose mempool records and cannot settle the question. The harness refused to resend the write. The original short-lived child receipt has expired and must not be reused.

The following live tests remain outstanding on this corrected deployment: delegated child receipt consumption and replay through the consumer, consumer child-error recovery and repeated completion, aggregate quota enforcement, freeze, policy revocation, and deployed-state reclamation at the resource caps. Do not transfer their prior-address or local test results to this deployment.

## Resource-cap correction and local evidence

The corrected source requires a principal to approve each exact agent address before registration. Pending approvals reserve bounded active-plus-pending per-principal and global slots, and either the principal or contract owner can cancel an unused approval. Regression tests cover unauthorized/Sybil registration, reservation-cap exhaustion and cancellation, principal-slot isolation, policy-cap reclamation, and expired-proposal reclamation. These establish local behavior; the live Studionet resource-reclamation cases are not yet run.

After adding secret-redacted CLI failure diagnostics, the local checks were:

| Check | Result |
|---|---|
| Direct Mode plus resumable harness helpers | **70 passed** (50 contract tests, 20 helper tests) |
| `python -m compileall -q contracts tests` | Passed |
| `python scripts/check_release_config.py` | Passed |
| Pinned GenVM lint (`v0.2.16`) | Passed, 3 checks |
| SDK validation | Passed, 31 methods: 10 views and 21 writes |
| GenVM schema | Passed, 31 methods |
| GenVM typecheck | Passed |
| GitHub Actions before the latest diagnostics-only helper change | Passed on `b7ecf5d9a14f7e64391e3d921398763aa2c1ea34`: Linux tests and GenVM checks; Windows helper tests and release configuration. |

The system `genvm-lint` shim failed to fetch SDK metadata under sandbox networking (`WinError 10013`); the pinned `.venv-release` runner completed validation. The Windows Direct Mode runner has previously failed before contract execution because `gltest` attempted to unlink a locked temporary file (`WinError 32`). No security protections were disabled.

## Older instances and unresolved history

The older pre-correction resource-lifecycle deployment at `0x7d59607d8E42Cf20e6c6988DdfFe17514D11B4FB` and the historical release at `0xb95a995A42E68455223DCC05403c98fDf40657FB` are not the current corrected deployment. Their transaction records remain in [resource-lifecycle candidate evidence](evidence/resource-lifecycle-candidate.json), [canonical release evidence](evidence/studionet-canonical-release.json), and [historical deployment record](DEPLOYMENT_HISTORICAL.md). Do not use those records as proof for the current address.

The older primary-wallet unresolved intents, including nonce `2686`, and predecessor nonce `2624` remain historical uncertainties. The current consumer write at nonce `441` is a separate unresolved intent on the secondary wallet. No ambiguous write was resent. Checkpoint and nonce reconciliation logic continues to require finalized transaction identity, not latest/pending nonce equality.

## Readiness

**Not submission-ready.** The corrected contract is deployed, finalized, and source-parity verified, and the live scenarios listed above have genuine Studionet finality and state-readback evidence. The delegated child ALLOW receipt has not been consumed, nonce `441` remains unreconciled, and the consumer-composability and live resource-lifecycle gates remain incomplete. Evidence provenance remains `CALLER_ASSERTED`; this contract does not independently authenticate external facts.
