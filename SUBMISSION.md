# Submission materials

## Title

**BoundaryOS — Delegated Agent Action Authorization Primitive**

## Portal description (under 1,000 characters)

BoundaryOS is a reusable GenLayer Intelligent Contract for versioned authority delegation to autonomous agents. Deterministic code authenticates policy owners and agents and enforces action scopes, explicit denies, integer amount/unit limits, shared aggregate quotas, expiry, nonces, delegation bounds, freeze, revocation, policy freshness, and one-time receipt consumption. For actions that pass those gates, the leader and validators independently classify whether bounded caller-asserted purpose claims fit the policy; only matching typed results can produce ALLOW. Ambiguity requires human review and protocol disagreement is not approval. Procurement executors, DAO automation, and delegated service-agent contracts can consume the same action-bound receipts. Caller claims are not represented as verified external facts.

## Release evidence

- Repository: <https://github.com/Chinny070/BoundaryOS>
- Canonical Studionet contract: `0xb95a995A42E68455223DCC05403c98fDf40657FB`.
- Deployment transaction: `0x7238677bd99f6a1b8ecdda5fc7bf73c7e4e8c9b5dce88fee303ef4361b4a8268`; finalized with `MAJORITY_AGREE`, VM `SUCCESS`, one round, and 3 agree / 2 idle validator votes.
- Frozen source commit: `df980984f752d2cf367743d4f0a458e8af5712e0`; `contracts/boundary_os.py` SHA-256 `86720777484aea493439d960cb741639b2320f00d81bd790b3dc14ee547f0937`. Official CLI source retrieval matched the committed source text after removing only the CLI response wrapper and surrounding newlines.
- Explorer: [canonical contract address](https://explorer-studio.genlayer.com/address/0xb95a995A42E68455223DCC05403c98fDf40657FB), [deployment transaction](https://explorer-studio.genlayer.com/tx/0x7238677bd99f6a1b8ecdda5fc7bf73c7e4e8c9b5dce88fee303ef4361b4a8268). The transaction detail page is client-rendered; finality and votes were independently checked through CLI receipt and RPC.
- Full machine-readable deployment, transaction, vote, scenario, and state-readback evidence: [canonical release record](docs/evidence/studionet-canonical-release.json). The older address `0x6692eB74852dD1b56966ac7AdC0ACDDA4Fe074BF`, including the unresolved historical consume intent at nonce 2624, is retained separately as [predecessor evidence](docs/evidence/studionet-legacy-canonical-history.json).
- Canonical live verification completed on the deployed address: semantic `ALLOW/MATCH`; semantic `DENY_PURPOSE/MISMATCH`; deterministic hard denial; valid receipt creation/readback; one-time consumption and valid post-consumption digest; finalized replay rejection; `DENY_AGGREGATE_CAP`; `DENY_FROZEN`; child delegation amount-widening rejection; stale receipt invalidation after policy update; and `DENY_STALE_POLICY` after revocation. Each tested action and receipt was reread at `LATEST_FINAL`; all tested decisions had valid receipt digests.
- Local validation: **61 passed** across `tests/direct/` and resumable harness helpers; compileall passed; GenVM lint (3 checks), SDK schema (22 methods), and typecheck passed on the contract-pinned cached runner `v0.2.16`; release configuration passed.
- Security boundary: evidence provenance remains `CALLER_ASSERTED`. No independent truth verification of caller-supplied evidence is claimed. The current signer history contains unattributed consumed nonce gaps; latest and pending nonce matched after the suite, and no ambiguous intent was resent. Details are in the deployment record.

## Readiness verdict

**Technically submission-ready, with the limitations above disclosed.** The corrected canonical source is deployed, source-parity checked, and independently exercised through the full live authorization and denial matrix with finalized consensus records and finalized-state readback. Local regression tests and pinned GenVM validation pass. Do not describe caller claims as independently verified evidence, and do not omit the historical nonce uncertainty or the unattributed nonce gaps from an audit context.
