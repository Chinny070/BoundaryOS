# Submission materials

## Title

**BoundaryOS — Delegated Agent Action Authorization Primitive**

## Portal description (under 1,000 characters)

BoundaryOS is a reusable GenLayer Intelligent Contract for versioned authority delegation to autonomous agents. Deterministic code authenticates policy owners and agents and enforces action scopes, explicit denies, integer amount/unit limits, shared aggregate quotas, expiry, nonces, delegation bounds, freeze, revocation, policy freshness, and one-time receipt consumption. For actions that pass those gates, the leader and validators independently classify whether bounded caller-asserted purpose claims fit the policy; only matching typed results can produce ALLOW. Ambiguity requires human review and protocol disagreement is not approval. Procurement executors, DAO automation, and delegated service-agent contracts can consume the same action-bound receipts. Caller claims are not represented as verified external facts.

## Evidence to provide

- Repository: <https://github.com/Chinny070/BoundaryOS>
- Canonical Studionet Explorer address: **pending**. The disposable test instance is `0xe5bcECDE0F002E78fa6A9271519d42e81D643d94` and must not be submitted as a release deployment.
- Deployment source commit: **pending canonical deployment**. Disposable deployment source fingerprint: `78e7623d7fa68828e0339bb668e976bb8b57b60f81dddd222ff0ca21f7043c16`; on-chain parity is unverified. Current source hash is recorded in [Deployment](docs/DEPLOYMENT.md) and has not been deployed.
- Finalized setup transactions and one finalized proposal submission are recorded in [Deployment](docs/DEPLOYMENT.md). Proposal finality does not prove semantic authorization. Live decision, receipt, denial, revocation, delegation, and quota transaction evidence is not yet verified.
- Machine-readable reconciliation of the expired disposable proposal and the 2026-10-15 preflight is in [studionet-reconciliation.json](docs/evidence/studionet-reconciliation.json). The resumable integration harness is [studionet_resume.py](tests/integration/studionet_resume.py); the read-only network inspector now passes through an approved elevated invocation. Live writes remain blocked because stable signer private keys are not configured for the Python SDK harness.
- The deployment-path comparison for the three requested reference projects is [REFERENCE_DEPLOYMENT_ANALYSIS.md](docs/REFERENCE_DEPLOYMENT_ANALYSIS.md). The active CLI profile, a funded secondary account, and Studionet chain ID 61999 were verified without exposing keys. Ordinary Codex subprocesses still have network/profile restrictions; approved elevated read-only commands work.
- Direct Mode, compile, lint, SDK schema validation, and typecheck results are recorded in [Deployment](docs/DEPLOYMENT.md). A newer GenVM runner is available, but the contract-pinned cached runner passed the checks; the newer runner was not validated.

## Readiness verdict

**Not submission-ready yet.** The receipt-digest fix remains undeployed. Existing live evidence confirms setup and proposal submission only; it does not prove semantic authorization, denial, consumption, replay protection, revocation, delegation, or quota outcomes. A read-only preflight now confirms chain 61999 and working CLI wallet access under approved elevation, but the resumable SDK suite refuses to write without stable local primary and secondary signer keys. The canonical deployment and deployed-source parity are pending. The available newer GenVM runner has not been validated. The expired disposable proposal remains unconsumed and receipt-free; the old deployment must not be relabeled canonical.
