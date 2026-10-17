# Submission materials

## Title

**BoundaryOS — Delegated Agent Action Authorization Primitive**

## Portal description

BoundaryOS is a reusable GenLayer Intelligent Contract for versioned authority delegation to autonomous agents. Deterministic code authenticates principals and agents and enforces action scopes, explicit denies, integer amount and unit limits, shared aggregate quotas, expiry, nonces, delegation bounds, freezes, revocation, policy freshness, and one-time receipt consumption. Actions that pass those gates receive a semantic purpose judgment whose typed result must agree across validators. Ambiguity requires human review; consensus disagreement is not approval. Consumer contracts can check and consume action-bound receipts. Evidence provenance is `CALLER_ASSERTED`; caller claims are not externally authenticated facts.

## Repository and deployed contract

- GitHub: <https://github.com/Chinny070/BoundaryOS>
- Studionet chain ID: `61999`
- Contract: [`0x99953d3c9e9c8FAff9289b9a80Ed038233Dc90eF`](https://explorer-studio.genlayer.com/address/0x99953d3c9e9c8FAff9289b9a80Ed038233Dc90eF)
- Deployment transaction: [`0xa181e3932651e05ae55cadc559df4dfa9d67e1ab5ff17034e155d69cb4e47193`](https://explorer-studio.genlayer.com/tx/0xa181e3932651e05ae55cadc559df4dfa9d67e1ab5ff17034e155d69cb4e47193)
- Deployment finalized with `MAJORITY_AGREE`, VM `SUCCESS`, one round, three agree and two idle votes.
- Frozen source commit: `26af28d67decc2c20985f1c715bf85e389a88a86`; `contracts/boundary_os.py` SHA-256: `7fc5610a160d0094eac3158680fc93237e792a3cc6a9a30e60441e9fde7fb627`.
- Deployed-source parity was checked through the official GenLayer CLI source retrieval. The normalized retrieved source matches the frozen source file.

## Acceptance evidence

The fresh release deployment passed live Studionet verification for semantic `ALLOW / MATCH`, semantic `DENY_PURPOSE / MISMATCH`, deterministic hard denial, receipt creation/readback, successful one-time receipt consumption, replay rejection, bounded root-to-child delegation and child receipt consumption, rejection of delegation widening, aggregate quota enforcement, agent freeze, stale policy handling, and revocation. All listed transactions finalized and the resulting state was read at `LATEST_FINAL` through the official Python SDK. The secret-free transaction and scenario record is [studionet-accessible-signer-release.json](docs/evidence/studionet-accessible-signer-release.json).

## Validation and caveats

- Harness helper and consumer proof tests: 30 passed in the latest local Windows run.
- Compileall and release configuration/source-identity checks passed.
- Contract-pinned GenVM lint, SDK validation, schema, and typecheck passed in the latest verified run; the Linux CI workflow runs these gates on push.
- Local Windows Direct Mode execution currently fails in the installed `gltest` loader before contract execution (`WinError 32`, temporary file still open). Do not treat that local runner error as a contract test failure or a pass; rely on the full Linux CI suite for Direct Mode.
- The live suite did not exercise the separate consumer fixture's child-error recovery/repeated completion or fill and reclaim every storage cap on-chain. These are outside the verified release matrix and are explicitly disclosed in the deployment record.
- Historical hashless transaction intents at predecessor signer nonces `441` and `2624` remain unresolved and were not resent. A separate release-suite nonce mismatch at `2728/2729` is also retained in the evidence; the captured nonce-2729 transaction finalized and its result was read back.
- BoundaryOS does not establish the truth of caller-supplied evidence, complete off-chain actions, or prevent a consumer from ignoring its receipt. Integrators must enforce the contract result and wait for finality.

## Readiness verdict

**Ready to submit as a standalone Intelligent Contract release, with the caveats above disclosed.** Deployment finality, source identity, live consensus behavior for the listed core authorization scenarios, local regression checks, and public submission documentation are recorded. This verdict does not claim independent external-evidence verification or live acceptance of the optional consumer-fixture and cap-saturation cases.
