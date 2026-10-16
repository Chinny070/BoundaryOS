# Deployment and verification record

## Network and signer path

The target is GenLayer Studionet, chain ID `61999`, RPC `https://studio.genlayer.com/api`. The installed GenLayer CLI `0.39.1` supports account selection, typed SDK deploy scripts, contract reads, and `code <address>`. The supported CLI account flow signs through the user's existing named wallet; this project never opens, copies, exports, logs, or commits wallet keys or keystore contents. The primary and secondary names used for this verification are `my-studionet-wallet` and `bradbury-e2e`.

The live harness in [studionet_resume.py](../tests/integration/studionet_resume.py) persists write intent, expected nonce, outer transaction hash, recovered GenLayer transaction ID, finality, votes, and execution result. On resume it reconciles known broadcasts and checks latest/pending nonce before new writes. It does not automatically resend an ambiguous write or redeploy during a scenario suite. The CLI deploy adapter is a separate explicit command with an independently bound deployment checkpoint.

## Corrected-source diagnostic deployment

This instance was deployed to diagnose the corrected contract and run the full live scenario suite. It is **disposable, not canonical**.

| Evidence | Verified value |
|---|---|
| Address | `0x2A63fEA23FC0D81D17aC9516Ed4Dd169dc9aa9D8` |
| Deployment transaction | `0x28e7fe8cf1c25c30ea44f1c724f0ebc198e7d9306f3e56ca1feb53a5a56c2163` |
| Sender nonce | `2579` |
| Status / consensus / VM | `FINALIZED` / `MAJORITY_AGREE` / `SUCCESS` |
| Validators | 3 agreed, 2 idle |
| Deployed source SHA-256 | `15fb138d0bd6008007d004ce3b89238730da823ce358ef52c59a542c8c6e7d17` |
| Source retrieval and parity | `genlayer code <address>` retrieved public deployed source; after normalizing CLI-added leading/trailing newlines, its bytes exactly matched `contracts/boundary_os.py` and the hash above. |
| Explorer | [Studionet Explorer address search](https://explorer-studio.genlayer.com/txs?search=0x28e7fe8cf1c25c30ea44f1c724f0ebc198e7d9306f3e56ca1feb53a5a56c2163). The Explorer transaction-detail and address pages were not independently inspected in this run. |
| Full diagnostic suite | Completed `2026-10-16T09:12:06Z`; 32 unique finalized scenario/setup transactions, including 2 expected contract rejections; all scenario readback assertions passed. |

Machine-readable public transaction and state evidence is in [studionet-fixed-diagnostic.json](evidence/studionet-fixed-diagnostic.json). The full checkpoint remains under the Git-ignored `.boundaryos/` directory.

### Live scenario results

| Scenario | Finalized state/readback |
|---|---|
| Semantic match | `ALLOW`, `MATCH`, valid receipt digest, `CALLER_ASSERTED` provenance |
| Receipt use | First consume finalized successfully; receipt readback showed consumed state and a recomputed valid digest. Replay finalized with `MAJORITY_AGREE` but VM execution `ERROR`, as expected. |
| Semantic mismatch | `DENY_PURPOSE`, `MISMATCH`, valid receipt digest |
| Explicit hard deny | `DENY_HARD_RULE`, `NOT_EVALUATED` |
| Aggregate quota | Three subsequent matching actions were allowed within the remaining budget; the next action was `DENY_AGGREGATE_CAP`, `NOT_EVALUATED`. |
| Agent freeze | `DENY_FROZEN`, `NOT_EVALUATED`; this exercised the corrected deterministic classification branch. |
| Delegation | Parent cap was 500 units; child request for 501 was finalized as the expected execution rejection. |
| Policy freshness | A version-two ALLOW receipt was consumable before version three and non-consumable after the update; the suite's independent read assertions passed. |
| Revocation | A pending action evaluated after policy revocation and its readback was `DENY_STALE_POLICY`. |

These are live diagnostic-instance results, not canonical release evidence. All action evidence is caller asserted; no third-party facts were independently verified.

## Earlier disposable instance

The earlier instance `0xe5bcECDE0F002E78fa6A9271519d42e81D643d94`, deployed by `0x9597081e8e9a19a8683f2f0fdfe003b3be83ca48636687c929b9eb9adad8c51b`, is superseded diagnostic evidence. It was built from older source; its proposal expired before evaluation. Do not submit or relabel it as canonical.

## Environment and tool findings

- Chain ID `61999`, account access, signing with both named accounts, reads, and deployment worked through the supported GenLayer CLI 0.39.1.
- CLI 0.40.0-rc.3 attempted the unsupported `sim_getFeeConfig` request and produced a finalized `NO_MAJORITY`; it was not used for the successful live suite.
- Legacy Python `gen_call` read encoding returned an RLP decoding error. The supported SDK read path through the CLI was used during the live suite. A later standalone read probe against the same instance returned `InvalidInputRpcError` for each queried method, so those repeated manual probes are not counted as new state evidence; the suite's assertions and readbacks were completed before that probe.
- Cloudflare 502 and Windows `WinError 10013` were transient/environmental issues. The resumable process recovered from polling nonfinal states without duplicate broadcast. Latest-runner cache extraction is blocked by Windows `WinError 5`; lint/schema/type validation used the runner already cached for the contract's pinned SDK hash. The latest runner is not claimed validated.
- One CLI generic `write --args` route coerced structured string arguments incorrectly and finalized with VM `ERROR`. It is excluded from passing contract tests. The harness instead uses the supported CLI SDK deploy-script path with JSON-preserved typed arguments.

## Local validation

Verified after the frozen-agent defect fix:

| Command | Result |
|---|---|
| `python -m pytest tests/direct/ tests/integration/test_studionet_resume_helpers.py -q --tb=short` | **39 passed** |
| `python -m compileall -q contracts tests` | **Passed** |
| `genvm-lint lint contracts/boundary_os.py` | **Passed, 3 checks** |
| `genvm-lint check contracts/boundary_os.py --json` | **Passed, 22 methods (8 views, 14 writes);** warning notes a newer uncached runner. |
| `genvm-lint typecheck contracts/boundary_os.py` | **Passed, no type errors** |

## Canonical release

The canonical release remains pending until a committed source revision is deployed and all of the following are recorded with verifiable evidence:

1. Hash the committed contract bytes and deploy that exact source through the checkpointed `--deploy-source` CLI path.
2. Reconcile the deployment transaction through `FINALIZED`, `MAJORITY_AGREE`, and successful execution; record its address and transaction identifier.
3. Run the explicit live scenario suite against the canonical address, or an equivalent release smoke flow, and read the resulting state after finality.
4. Retrieve source using `genlayer code <address>` and compare the normalized retrieved source bytes with the committed contract file.
5. Verify and record the Explorer address and deployment transaction evidence.
6. Commit the final evidence and docs; push `main` without rewriting history.

Until those gates are met, the diagnostic deployment must remain labeled noncanonical and the project must not be described as submission-ready.
