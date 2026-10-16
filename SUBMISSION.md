# Submission materials

## Title

**BoundaryOS — Delegated Agent Action Authorization Primitive**

## Portal description (under 1,000 characters)

BoundaryOS is a reusable GenLayer Intelligent Contract for versioned authority delegation to autonomous agents. Deterministic code authenticates policy owners and agents and enforces action scopes, explicit denies, integer amount/unit limits, shared aggregate quotas, expiry, nonces, delegation bounds, freeze, revocation, policy freshness, and one-time receipt consumption. For actions that pass those gates, the leader and validators independently classify whether bounded caller-asserted purpose claims fit the policy; only matching typed results can produce ALLOW. Ambiguity requires human review and protocol disagreement is not approval. Procurement executors, DAO automation, and delegated service-agent contracts can consume the same action-bound receipts. Caller claims are not represented as verified external facts.

## Evidence

- Repository: <https://github.com/Chinny070/BoundaryOS>
- Canonical Studionet address and deployment transaction: **pending**. The corrected-source diagnostic instance `0x2A63fEA23FC0D81D17aC9516Ed4Dd169dc9aa9D8` is expressly noncanonical.
- Corrected-source diagnostic deployment and full live scenario transaction evidence: [machine-readable record](docs/evidence/studionet-fixed-diagnostic.json) and [deployment record](docs/DEPLOYMENT.md).
- Local verification: 39 tests passed; compileall, 3 GenVM lint checks, SDK schema validation (22 methods), and typecheck passed using the locally cached runner pinned by the contract. A newer runner could not be downloaded/extracted in this Windows environment and is not claimed tested.
- The CLI-backed resumable integration harness is [studionet_resume.py](tests/integration/studionet_resume.py). It signs with existing named CLI accounts, verifies finality and state readback, records secret-free checkpoints, and does not resend unresolved writes.
- Security analysis: [docs/SECURITY.md](docs/SECURITY.md). The contract's evidence mode remains `CALLER_ASSERTED`; no external evidence is independently authenticated.

## Readiness verdict

**Release candidate verified on a disposable Studionet instance; canonical submission remains pending.** The corrected source passed local gates and a complete live semantic/deterministic scenario suite, and the deployed diagnostic source matched the working source by hash after newline normalization. Do not submit the diagnostic address. Canonical deployment, canonical-instance smoke tests, deployed source parity, and Explorer address evidence must be added to [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) before describing the project as submission-ready.
