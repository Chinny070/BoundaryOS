# Deployment and verification record

## Network and signer path

The target is GenLayer Studionet, chain ID `61999`, RPC `https://studio.genlayer.com/api`. The current installed GenLayer CLI reports `0.40.0-rc.3`; `account list`, named-account selection, `receipt`, `schema`, and `code <address>` worked in this session. The existing prior live writes were made through the named-wallet CLI SDK flow. This project never opens, copies, exports, logs, or commits wallet keys or keystore contents. The primary and secondary names used for this verification are `my-studionet-wallet` and `bradbury-e2e`.

The live harness in [studionet_resume.py](../tests/integration/studionet_resume.py) persists write intent, expected nonce, outer transaction hash, recovered GenLayer transaction ID, finality, votes, and execution result. On resume it reconciles known broadcasts and checks latest/pending nonce before new writes. It does not automatically resend an ambiguous write or redeploy during a scenario suite. Writes and deployments use CLI deploy scripts with typed SDK arguments; read-only calls use the official Python SDK's typed `read_contract` API at `LATEST_FINAL`. In CLI-signer mode, an ephemeral read-only account is held in memory because the SDK requires `from`; it is not used to sign writes or persisted. The CLI deploy adapter is a separate explicit command with an independently bound deployment checkpoint.

## Canonical deployment

The canonical instance was deployed from the contract source committed at `2e918135669a98de6e7c32a30c288a69a7ea0c2f`. The later changes in the final Git commit update only the test harness and evidence/docs; the contract file and its SHA-256 remain unchanged.

| Evidence | Verified value |
|---|---|
| Canonical Studionet address | `0x6692eB74852dD1b56966ac7AdC0ACDDA4Fe074BF` |
| Deployment transaction | `0x8159a551d133d3a915d532a82cebdb8864233fde7bc8c8595805761193e1c88e` |
| Sender nonce | `2616` |
| Status / consensus / VM | `FINALIZED` / `MAJORITY_AGREE` / `SUCCESS` |
| Validator votes | 5 agree |
| Contract file SHA-256 | `15fb138d0bd6008007d004ce3b89238730da823ce358ef52c59a542c8c6e7d17` |
| Deployed-source parity | `genlayer code` retrieved the deployed source; its body exactly matched the committed file after removing only CLI-added leading/trailing newlines. |
| Explorer transaction | [Open the deployment transaction](https://explorer-studio.genlayer.com/tx/0x8159a551d133d3a915d532a82cebdb8864233fde7bc8c8595805761193e1c88e). The transaction URL returned HTTP 200, but the downloaded page contained only the client-rendered route shell; the detail fields were not present in the static response. Finality and five agreeing validator votes were independently rechecked through the CLI receipt and RPC. |

The canonical deployment setup writes finalized successfully: registration `0xfb05f68e8b3da0896528354e3c3864c0fb0f361dc31f50593332d943c15da4c1` (nonce 2617), policy creation `0xed94ea8d4ce5fe0e5cd7fd69a0a2f04a6643ecbf037f15448ccc781966508790` (nonce 2618), and consumer authorization `0xf7f51499c74915e5c142737c769d202775b137f7baf6e21bae32f4ec5296a4c2` (nonce 2619). Each was `FINALIZED`, `MAJORITY_AGREE`, VM `SUCCESS`.

The canonical semantic smoke submitted action `ddf61a09daafb008fdc845d49bafa5c8b26f84009f7165971922ebd3d16a933f` (nonce 1) and finalized an `ALLOW/MATCH` with a valid receipt. That five-minute receipt expired while resolving a temporary read failure, so the resumable harness created a fresh proposal at nonce 2, `56d9d3de0357987a26195251fbde3d7692fb9dc73bde21878dd309072ff2ee62`. Its submit transaction `0x63dbd820566273d7b5c563a66f85bdbc5e8d7fd2f805561e214d86365ff74387` (nonce 2622) and evaluation transaction `0x3459cf7738fda09493e23598c2478e49225dfc51fc9c94961a59ae566f841515` (nonce 2623) both finalized with `MAJORITY_AGREE` and VM `SUCCESS`; finalized readback again returned `ALLOW/MATCH`, `CALLER_ASSERTED`, and a valid receipt digest.

The consume intent reserved signer nonce 2624, but the CLI exited without returning a transaction hash and its checkpoint contains no outer or GenLayer transaction ID. Historical broadcast disposition therefore remains unknown: nonce equality at the earlier check did not prove that it had never been broadcast. Later, the Studionet address Explorer and RPC exposed a different finalized transaction at exactly that sender nonce: `0xa9cb7539bb75c695f7f3331a8cf73a84f7cc75c5fd0b57443ce351aabc8e48ac`, a value send to `0xb7278A61aa25c888815aFC32Ad3cC52fF24fE575`, finalized with consensus `NO_MAJORITY`. It is not a call to BoundaryOS. Nonces 2625 and 2626 are also occupied by different finalized value sends (`0xadedfb0f5090c388544a598dbd5efdf8d7b0ac61666b00b743810a53f4d1c287` and `0x569c45614e33eeb08d646039f4464bc5f58df0a5f74e7d28def362428005134b`, both `NO_MAJORITY`). At the 16:59:46Z reconciliation, before the subsequent canonical test attempts, primary latest and pending nonce were both 2627. The finalized different transaction at nonce 2624 makes the old consume intent ineligible to execute at that nonce; it does not establish whether the original submission was never broadcast, dropped, or rejected before acceptance. No resend was attempted. The old receipt is expired, and no canonical consumption or replay result is claimed.

The unresolved nonce-2624 intent was not resent. A controlled read-path comparison found that canonical and corrected diagnostic schemas both declare `get_agent(agent_address: str)`. The installed CLI parser classifies every `0x` plus 40-hex token as `CalldataAddress`, and its parser does not unwrap a standalone quoted JSON string into a plain string argument. CLI `call get_agent` therefore cannot faithfully express the declared view argument; its GenVM method-resolution error and occasional Windows `0xC0000409` process abort were client/argument-path failures, not proof of a canonical-only contract defect. The official Python SDK `client.read_contract(..., args=[address_as_python_str], transaction_hash_variant=LATEST_FINAL)` returned real state from both deployments using the same temporary in-memory read caller and Studionet RPC. Canonical finalized reads returned the registered, unfrozen agent, its policy, and the previously recorded `ALLOW/MATCH` receipt; the receipt is now expired.

Using the repaired typed SDK reads, the harness submitted three fresh canonical proposals only after checking prior finalized state. Their transactions at signer EVM nonces 2627, 2628, and 2629 (`0xf181be01aa857eb5a1bb79a815bf7f3a6799d6640094b641d38ec55c6a5e0d00`, `0xecca4eb187bd333ba3acd5f686a03f7d020c0bf1e9b26e3168d6be5dfd4c9de4`, and `0xb43ba53769ddd970150dcf16d52d875978bf3ad679914b2bdd72ef376d0e6a04`) each finalized `NO_MAJORITY`, with zero observed rounds/votes and no VM execution result. Finalized `get_action` and `get_receipt` reads confirmed all three derived action IDs were absent. These are consensus availability failures, not contract denials or successful submits. The harness stopped after the third bounded attempt; no additional writes were sent. The canonical scenario matrix remains **partial** and is not submission-ready.

Canonical transaction and state facts are recorded in [studionet-canonical-release.json](evidence/studionet-canonical-release.json). Complete scenario verification on the same corrected source, including successful one-time consumption and expected replay rejection, was independently completed on the noncanonical diagnostic instance below.

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

- Chain ID `61999`, account access, signing with both named accounts, and deployment/receipt/code/schema operations were previously verified. CLI 0.40.0-rc.3 and an isolated official CLI 0.39.1 invocation both failed on `get_agent` for canonical and diagnostic instances. The CLI's scalar parser maps an address-shaped token to address calldata, while the contract schema requires a string. The Python SDK's typed `read_contract` at `LATEST_FINAL` successfully returned and decoded actual canonical and diagnostic state; this is the harness read path now.
- CLI 0.40.0-rc.3 attempted the unsupported `sim_getFeeConfig` request and produced a finalized `NO_MAJORITY`; it was not used for the successful live suite.
- The harness no longer uses its legacy manually serialized Python `gen_call` read path or the CLI view call; it uses the SDK's supported typed read API with finalized state. CLI call errors are not counted as contract results. Three new writes were accepted for processing but finalized `NO_MAJORITY` before any round or VM result; all three are recorded as consensus failures with absent proposal/receipt state, not contract-level denials.
- Cloudflare 502 and Windows `WinError 10013` were transient/environmental issues. The resumable process recovered from polling nonfinal states without duplicate broadcast. Latest-runner cache extraction is blocked by Windows `WinError 5`; lint/schema/type validation used the runner already cached for the contract's pinned SDK hash. The latest runner is not claimed validated.
- One CLI generic `write --args` route coerced structured string arguments incorrectly and finalized with VM `ERROR`. It is excluded from passing contract tests. The harness instead uses the supported CLI SDK deploy-script path with JSON-preserved typed arguments.

## Local validation

Verified after the frozen-agent defect fix and resumable CLI read changes:

| Command | Result |
|---|---|
| `python -m pytest tests/direct/ tests/integration/test_studionet_resume_helpers.py -q --tb=short` | **42 passed** |
| `python -m compileall -q contracts tests` | **Passed** |
| `genvm-lint lint contracts/boundary_os.py` | **Passed, 3 checks** |
| `genvm-lint check contracts/boundary_os.py --json` | **Passed, 22 methods (8 views, 14 writes);** warning notes a newer uncached runner. |
| `genvm-lint typecheck contracts/boundary_os.py` | **Passed, no type errors** |

## Readiness

The contract source remains deployed canonically and source parity was previously reverified against the frozen contract bytes. The corrected-source diagnostic instance passed the complete live scenario suite. Canonical SDK finalized reads are now working and canonical setup plus an expired semantic ALLOW/MATCH receipt remain readable. Three fresh submit attempts finalized `NO_MAJORITY` with zero rounds/votes and no execution result; their action and receipt state was independently confirmed absent. Thus canonical semantic ALLOW/MATCH, receipt consumption/replay, mismatch, hard denial, revocation/freshness, freeze, delegation, and quota have not all been verified on this canonical instance. The old nonce-2624 consume intent remains historically unknown, though it cannot execute at that nonce because a different finalized transaction occupies it. Explorer detail data was not rendered in the static HTTP response; deployment finality, source identity, and votes were independently checked through GenLayer RPC/CLI. The project remains **not submission-ready** until Studionet consensus resumes and the canonical smoke assertions are finalized and read back.
