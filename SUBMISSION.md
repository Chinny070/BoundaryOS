# Submission materials

## Title

**BoundaryOS — Delegated Agent Action Authorization Primitive**

## Portal description (under 1,000 characters)

BoundaryOS is a reusable GenLayer Intelligent Contract for versioned authority delegation to autonomous agents. Deterministic code authenticates policy owners and agents and enforces action scopes, explicit denies, integer amount and unit limits, shared aggregate quotas, expiry, nonces, delegation bounds, freeze, revocation, policy freshness, and one-time receipt consumption. Actions that pass those gates receive a semantic purpose judgment whose typed result must agree across validators. Ambiguity requires human review and protocol disagreement is not approval. Procurement executors, DAO automation, and delegated service-agent contracts can consume action-bound receipts. Evidence provenance is `CALLER_ASSERTED`; caller claims are not externally authenticated facts.

## Release evidence

- Repository: <https://github.com/Chinny070/BoundaryOS>
- Corrected-source Studionet instance: [`0xe6b915d1DAb0EC9035D07368938413798d77c959`](https://explorer-studio.genlayer.com/address/0xe6b915d1DAb0EC9035D07368938413798d77c959).
- Deployment transaction: [`0xbb04d21b3d0784a2c61fcaedc0b83635571118ba1d18b5a59654d041df457eec`](https://explorer-studio.genlayer.com/tx/0xbb04d21b3d0784a2c61fcaedc0b83635571118ba1d18b5a59654d041df457eec), finalized `MAJORITY_AGREE`, VM `SUCCESS`, one round, five agree votes.
- Deployed contract source is commit `03447b9ba09bced9ab151bc7212b423d7bcd8c82`, file SHA-256 `7fc5610a160d0094eac3158680fc93237e792a3cc6a9a30e60441e9fde7fb627`. GenLayer CLI source retrieval matched the committed source byte-for-byte after removing only the CLI wrapper and outer newlines.
- Corrected-source live evidence covers principal-approved agent registration, semantic `ALLOW / MATCH`, receipt readback/consumption and replay rejection, semantic `DENY_PURPOSE / MISMATCH`, deterministic `DENY_HARD_RULE`, bounded delegation, rejection of amount widening, and delegated child action evaluation as `ALLOW / MATCH`.
- The test consumer fixture is deployed at `0x1efcCe3dFA92abdcd5887ceF8956cd63F7d816f5`. The delegated child receipt consumption and consumer recovery path remain incomplete. Its `request_protected_operation` intent at signer nonce `441` has no transaction hash and remains unresolved; no retry was made. See [the exact transaction and scenario evidence](docs/evidence/principal-approval-release.json) and [deployment record](docs/DEPLOYMENT.md).
- Local checks: 70 Direct Mode and harness helper tests passed; compileall, release configuration, pinned GenVM lint, SDK validation (31 methods), schema, and typecheck passed. [GitHub Actions run 39016951218](https://github.com/Chinny070/BoundaryOS/actions/runs/39016951218) passed on commit `3481f844399fc0fdbda81ed89400fa5d0b09d9a8`: Linux 70 tests plus contract/consumer GenVM validation, and Windows 20 helper tests and release configuration.
- Historical deployments and nonce uncertainties are documented separately. Their behavior does not count as verification for this corrected contract. Evidence source remains caller asserted.

## Readiness verdict

**Not submission-ready.** The corrected contract's deployment, finality, source parity, and the listed live behaviors are verified. The receipt-consumption step for the delegated child remains unknown because the nonce-441 broadcast lacks an identity. Live consumer error recovery/repeated completion, aggregate quota, freeze, revocation, and deployed-state reclamation tests also remain outstanding. Do not submit this release as fully verified until these acceptance gates are completed with finalized transactions and finalized-state readbacks.
