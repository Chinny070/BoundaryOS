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
- Direct Mode, compile, lint, SDK validation, and typecheck results are recorded in [Deployment](docs/DEPLOYMENT.md). Validation used the cached runner; latest-runner lookup is blocked by network restrictions.

## Readiness verdict

**Not submission-ready yet.** The working receipt-digest fix has not been deployed; the live run verifies setup and proposal submission only, not a decision or consumption flow; latest GenVM runner lookup is network-blocked; canonical deployment and deployed-source parity are pending. The Explorer search listing verifies the disposable proposal, while its detail endpoint returned Cloudflare 502. Do not submit this evidence section as if the outstanding gates passed.
