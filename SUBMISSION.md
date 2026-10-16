# Submission materials

## Title

**BoundaryOS — Delegated Agent Action Authorization Primitive**

## Portal description (under 1,000 characters)

BoundaryOS is a reusable GenLayer Intelligent Contract for versioned authority delegation to autonomous agents. Deterministic code authenticates policy owners and agents and enforces action scopes, explicit denies, integer amount/unit limits, shared aggregate quotas, expiry, nonces, delegation bounds, freeze, revocation, policy freshness, and one-time receipt consumption. For actions that pass those gates, the leader and validators independently classify whether bounded caller-asserted purpose claims fit the policy; only matching typed results can produce ALLOW. Ambiguity requires human review and protocol disagreement is not approval. Procurement executors, DAO automation, and delegated service-agent contracts can consume the same action-bound receipts. Caller claims are not represented as verified external facts.

## Evidence

- Repository: <https://github.com/Chinny070/BoundaryOS>
- Canonical Studionet contract: `0x6692eB74852dD1b56966ac7AdC0ACDDA4Fe074BF`; finalized deployment transaction `0x8159a551d133d3a915d532a82cebdb8864233fde7bc8c8595805761193e1c88e`. Deployed source parity was rechecked against the frozen source commit and matches SHA-256 `15fb138d0bd6008007d004ce3b89238730da823ce358ef52c59a542c8c6e7d17`. Canonical semantic ALLOW/MATCH and receipt readback passed. The earlier consume intent has no transaction ID and its original broadcast disposition remains unknown; a different finalized value send now occupies nonce 2624, so that intent cannot execute at that nonce. The diagnostic instance `0x2A63fEA23FC0D81D17aC9516Ed4Dd169dc9aa9D8` remains expressly noncanonical.
- Canonical deployment and partial smoke evidence: [machine-readable record](docs/evidence/studionet-canonical-release.json). The corrected-source diagnostic deployment and complete live scenario transaction evidence: [machine-readable record](docs/evidence/studionet-fixed-diagnostic.json) and [deployment record](docs/DEPLOYMENT.md).
- Local verification: 44 tests passed; compileall, 3 GenVM lint checks, SDK schema validation (22 methods), and typecheck passed using the locally cached runner pinned by the contract. A newer runner could not be downloaded/extracted in this Windows environment and is not claimed tested.
- The CLI-backed resumable integration harness is [studionet_resume.py](tests/integration/studionet_resume.py). It signs with existing named CLI accounts, verifies finality and state readback, records secret-free checkpoints, and does not resend unresolved writes.
- Security analysis: [docs/SECURITY.md](docs/SECURITY.md). The contract's evidence mode remains `CALLER_ASSERTED`; no external evidence is independently authenticated.

## Readiness verdict

**Not submission-ready.** The canonical deployment and source parity are verified, and the full live matrix passed on the corrected-source diagnostic instance. Canonical smoke reached semantic ALLOW/MATCH and valid receipt readback but did not finish receipt consumption. RPC and Explorer history now show a different finalized transaction occupies primary signer nonce 2624; that prevents the old consume intent from executing, although whether it was originally broadcast or dropped/rejected remains unknown. Canonical verification retried with both the primary and secondary named wallets and isolated checkpoints, but the current CLI read path failed on `get_agent` before any new write. Canonical consumption/replay, semantic mismatch, hard denial, revocation, freeze, delegation, and quota assertions remain unverified. The Explorer transaction route returned its client-rendered shell; deployment finality and votes were independently verified through CLI/RPC. Do not submit the diagnostic address or claim canonical smoke completion.
