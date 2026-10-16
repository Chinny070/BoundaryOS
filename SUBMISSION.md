# Submission materials

## Title

**BoundaryOS — Delegated Agent Action Authorization Primitive**

## Portal description (under 1,000 characters)

BoundaryOS is a reusable GenLayer Intelligent Contract for versioned authority delegation to autonomous agents. Deterministic code authenticates policy owners and agents and enforces action scopes, explicit denies, integer amount/unit limits, shared aggregate quotas, expiry, nonces, delegation bounds, freeze, revocation, policy freshness, and one-time receipt consumption. For actions that pass those gates, the leader and validators independently classify whether bounded caller-asserted purpose claims fit the policy; only matching typed results can produce ALLOW. Ambiguity requires human review and protocol disagreement is not approval. Procurement executors, DAO automation, and delegated service-agent contracts can consume the same action-bound receipts. Caller claims are not represented as verified external facts.

## Evidence

- Repository: <https://github.com/Chinny070/BoundaryOS>
- Canonical Studionet contract: `0x6692eB74852dD1b56966ac7AdC0ACDDA4Fe074BF`; finalized deployment transaction `0x8159a551d133d3a915d532a82cebdb8864233fde7bc8c8595805761193e1c88e`. Deployed source parity was rechecked against the frozen source commit and matches SHA-256 `15fb138d0bd6008007d004ce3b89238730da823ce358ef52c59a542c8c6e7d17`. Canonical `get_agent`, `get_policy`, and the prior `ALLOW/MATCH` receipt were successfully read at `LATEST_FINAL` through the typed Python SDK; the receipt is expired and was not reused. Three fresh `submit_action` transactions at EVM nonces 2627–2629 finalized `NO_MAJORITY` with zero rounds/votes and no VM execution result; finalized readback confirmed no action or receipt was created. The historical consume intent's original broadcast disposition remains unknown, and a different finalized value send occupies nonce 2624. The diagnostic instance `0x2A63fEA23FC0D81D17aC9516Ed4Dd169dc9aa9D8` remains expressly noncanonical.
- Canonical deployment and partial smoke evidence: [machine-readable record](docs/evidence/studionet-canonical-release.json). The corrected-source diagnostic deployment and complete live scenario transaction evidence: [machine-readable record](docs/evidence/studionet-fixed-diagnostic.json) and [deployment record](docs/DEPLOYMENT.md).
- Local verification on this revision: 42 tests passed; compileall, 3 GenVM lint checks, SDK schema validation (22 methods), and typecheck passed using the locally cached runner pinned by the contract. The linter could not query the latest runner because Windows returned `WinError 10013`; a newer runner is not claimed tested.
- The resumable integration harness is [studionet_resume.py](tests/integration/studionet_resume.py). It signs writes with existing named CLI accounts, uses typed SDK finalized reads, records secret-free checkpoints, and does not resend ambiguous writes. After three finalized `NO_MAJORITY` submit outcomes with absent finalized proposal state, it stopped canonical writes.
- Security analysis: [docs/SECURITY.md](docs/SECURITY.md). The contract's evidence mode remains `CALLER_ASSERTED`; no external evidence is independently authenticated.

## Readiness verdict

**Not submission-ready.** The canonical deployment and frozen-source parity are documented; the full live matrix passed only on the corrected-source diagnostic instance. The canonical read-path blocker is resolved through the official typed SDK, but Studionet then finalized three fresh canonical proposal submissions as `NO_MAJORITY` with no validator rounds, no execution result, and no resulting action/receipt state. Canonical receipt consumption/replay, semantic mismatch, hard denial, revocation, freeze, delegation, and quota remain unverified. The old nonce-2624 consume intent's historical disposition is still unknown. The Explorer transaction route returned its client-rendered shell; deployment finality and votes were independently checked through CLI/RPC. Do not submit the diagnostic address or claim canonical smoke completion.
