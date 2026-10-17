# Submission materials

## Title

**BoundaryOS — Delegated Agent Action Authorization Primitive**

## Portal description (under 1,000 characters)

BoundaryOS is a reusable GenLayer Intelligent Contract for versioned authority delegation to autonomous agents. Deterministic code authenticates policy owners and agents and enforces action scopes, explicit denies, integer amount/unit limits, shared aggregate quotas, expiry, nonces, delegation bounds, freeze, revocation, policy freshness, and one-time receipt consumption. For actions that pass those gates, the leader and validators independently classify whether bounded caller-asserted purpose claims fit the policy; only matching typed results can produce ALLOW. Ambiguity requires human review and protocol disagreement is not approval. Procurement executors, DAO automation, and delegated service-agent contracts can consume the same action-bound receipts. Caller claims are not represented as verified external facts.

## Release evidence

- Repository: <https://github.com/Chinny070/BoundaryOS>
- Last independently documented Studionet release: contract `0xb95a995A42E68455223DCC05403c98fDf40657FB`, deployment transaction `0x7238677bd99f6a1b8ecdda5fc7bf73c7e4e8c9b5dce88fee303ef4361b4a8268`. This deployment finalized with `MAJORITY_AGREE`, VM `SUCCESS`, one round, and 3 agree / 2 idle validator votes. Its frozen source was commit `df980984f752d2cf367743d4f0a458e8af5712e0`, SHA-256 `86720777484aea493439d960cb741639b2320f00d81bd790b3dc14ee547f0937`, and the official CLI retrieval matched that prior commit's source.
- Its canonical live record contains the prior address's semantic match/mismatch, deterministic denials, receipt creation/consumption/replay, quota, freeze, delegation-boundary, policy freshness, and revocation evidence. See [canonical release record](docs/evidence/studionet-canonical-release.json), [prior deployment record](docs/DEPLOYMENT.md), and [predecessor history](docs/evidence/studionet-legacy-canonical-history.json). Those records establish only the source and transactions named in them.
- The current candidate adds principal admission, bounded per-principal quotas, active proposal reclamation, policy reclamation, and policy-instance action-ID separation. It is not deployed and has no verified live source parity. Current checks and blockers are in [candidate evidence](docs/evidence/resource-lifecycle-candidate.json).
- Current checks: 18 resumable-harness helper tests passed; compileall passed; contract GenVM lint passed (3 checks), SDK schema validation passed (29 methods), and typecheck passed on the pinned cached runner `v0.2.16`. Consumer fixture lint passed (3 checks), schema passed (5 methods), and typecheck passed. Release configuration passed. Windows Direct Mode could not load the contract because of `gltest`'s locked temporary file (`WinError 32`). Linux CI runs 39007250085, 39007541381, and 39007742692 executed the suite and reported 63 passed/4 failed, 65 passed/2 failed, and 66 passed/1 failed; observed issues were confined to test fixture setup/arguments, and another run is pending after their corrections. This session has `CODEX_SANDBOX_NETWORK_DISABLED=1`, so no candidate network transactions or source reads were performed.
- Security boundary: evidence provenance remains `CALLER_ASSERTED`; the contract does not independently verify caller-supplied external facts. Historical signer nonce gaps and predecessor nonce-2624 uncertainty remain in the prior deployment records.

## Readiness verdict

**Not submission-ready.** The prior deployment has historical verification evidence, but the current source candidate has not passed Direct Mode, live delegation happy-path, consumer composability, canonical deployment, deployed-source parity, or candidate state-readback gates. Resume in a compatible Linux/GenLayer environment, preserve finality checks, and update the release claim only after those candidate-specific results are evidenced. Do not represent the historical deployment as the candidate deployment.
