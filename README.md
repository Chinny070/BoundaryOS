# BoundaryOS

BoundaryOS is a standalone GenLayer Intelligent Contract for checking whether an authenticated agent's proposed action fits a principal's current delegation policy. It combines deterministic permission and quota checks with an independently repeated semantic purpose judgment, then stores an action-bound, version-bound receipt.

**Current release status:** 42 Direct Mode and resumable-harness helper tests pass; compile, GenVM lint, schema validation, and typecheck pass with the locally cached pinned runner. The canonical Studionet instance is deployed at `0x6692eB74852dD1b56966ac7AdC0ACDDA4Fe074BF`; deployed source parity remains tied to the frozen deployment commit. Canonical registration, policy, consumer authorization, and semantic ALLOW/MATCH with valid receipt readback finalized. The old consume intent at signer nonce 2624 remains historically unknown, but that nonce is occupied by a different finalized value-send. The CLI view-read failure was traced to typed-argument encoding: `get_agent` takes a string, while the CLI coerces address-shaped arguments to address calldata. The official Python SDK now provides successful `LATEST_FINAL` canonical state reads and is used by the resumable harness. Three fresh canonical `submit_action` attempts subsequently finalized `NO_MAJORITY` with zero rounds/votes and no execution result; finalized readback confirmed no proposals or receipts were created. Canonical smoke remains partial and the project is not submission-ready. The corrected-source diagnostic instance has the complete live matrix. See [Deployment](docs/DEPLOYMENT.md), [canonical evidence](docs/evidence/studionet-canonical-release.json), [diagnostic evidence](docs/evidence/studionet-fixed-diagnostic.json), and [Submission](SUBMISSION.md).

## What the contract protects

The contract can protect only actions whose consumers check BoundaryOS. It does not stop an unrelated off-chain agent from acting, prove the truth of caller-submitted evidence, or establish malicious intent.

Principals authorize only agents that first register themselves. Each policy has immutable numbered versions and a canonical SHA-256 commitment. Agents submit bounded action facts with a strictly increasing nonce. Deterministic code enforces owner identity, action scope, hard denies, integer amount and unit constraints, aggregate quotas, validity windows, freezes, delegation depth/subsets, revocation, policy freshness, and receipt consumption. Only an action that passes those gates reaches GenLayer's semantic evaluator.

Evidence is explicitly `CLAIM_ONLY`: the action's purpose and evidence text are assertions supplied by the caller. Every validator sees the same bounded claims, but this contract does not fetch or authenticate external records. Consumers must not treat a receipt as proof that the claim is true.

## Architecture

`contracts/boundary_os.py` is the single canonical deployable contract.

1. An agent registers from its own sender address and selects the principal it accepts.
2. A principal creates a typed policy for that registered agent.
3. Authorized agents may delegate within the parent's exact action, amount, purpose, and time bounds. Chains are limited to four levels.
4. An agent submits an action with a monotonically increasing nonce. Its stable ID commits to policy, agent, nonce, and canonical action facts. The proposal expires after ten minutes.
5. Evaluation rejects stale, expired, frozen, revoked, hard-denied, over-limit, wrong-unit, and over-quota proposals deterministically.
6. Only the semantic purpose check calls `gl.nondet.exec_prompt` inside `gl.vm.run_nondet_unsafe`. Validators independently rerun the classifier and must agree on the bounded `MATCH`, `MISMATCH`, or `UNCLEAR` field. Ambiguity requires owner review; disagreement can leave the GenLayer transaction undetermined.
7. An `ALLOW` receipt is bound to the action digest, policy version and digest, agent, chain, contract instance, and a short expiry. A whitelisted consumer can consume it once. Policy changes, revocations, freezes, expiry, and prior consumption make it unusable.

Policy-wide amount aggregation is shared across agents and their descendants for the same policy version and time window. This blocks splitting the same authority across multiple delegated agents to evade a declared cap. It does not classify intent as fraud or collusion; independent actions are assessed against the same declared budget.

## Main interface

| Method | Purpose |
|---|---|
| `register_agent(principal_address)` | Agent opts in from its own address and selects one principal |
| `create_policy(policy_id, agent_address, policy_json)` | Principal creates immutable version 1 |
| `update_policy(policy_id, policy_json)` | Principal appends a new immutable version |
| `delegate_authority(...)` / `revoke_delegation(...)` | Bounded, non-escalating agent delegation |
| `submit_action(policy_id, nonce, action_json)` | Creates a ten-minute, action-bound proposal |
| `preview_action_id(...)` | Deterministically computes the proposal ID for consumers |
| `evaluate_action(action_id)` | Applies deterministic gates, then consensus judgment when needed |
| `resolve_review(action_id, approved, review_note)` | Owner handles ambiguity; hard rules and quotas still apply |
| `freeze_agent(...)` / `freeze_contract(...)` | Agent, principal, or deployer emergency controls |
| `revoke_policy(...)` | Principal revokes authority and invalidates receipts |
| `authorize_consumer(...)` / `revoke_consumer(...)` | Controls which consumer addresses can use receipts |
| `can_consume_authorization(...)` / `consume_authorization(...)` | Checks and consumes a fresh `ALLOW` once |
| `get_policy(...)`, `get_action(...)`, `get_receipt(...)`, `get_agent(...)`, `get_delegation(...)` | Bounded machine-readable reads |
| `get_policy_diff(...)` | Reports permission expansion between immutable versions |

The policy JSON schema is documented in [Integration](docs/INTEGRATION.md). Amounts are non-negative integers in a single explicit uppercase unit per policy; no floating-point values or cross-unit sums are accepted.

## Development

Requirements: Python 3.12+, `genlayer-test`, and `genvm-linter`. The contract pins the GenVM runner in its dependency header. Current pins are in [requirements.txt](requirements.txt).

```powershell
python -m pip install -r requirements.txt
$env:PYTHONIOENCODING = 'utf-8'
python -m pytest tests/direct/ tests/integration/test_studionet_resume_helpers.py -q --tb=short
genvm-lint lint contracts/boundary_os.py
genvm-lint check contracts/boundary_os.py --json
genvm-lint typecheck contracts/boundary_os.py
```

The Direct Mode suite uses mocked LLM results only to test local contract behavior and validator rejection. These tests are not live consensus evidence. For real validators, use the resumable Studionet harness in [tests/integration/studionet_resume.py](tests/integration/studionet_resume.py). It supports named wallets managed by the installed GenLayer CLI as well as explicitly configured SDK signers. Live writes require explicit opt-in, stable primary/child signers, nonce checks, persistent checkpoints, finality polling, and finalized-state readback. Reads use GenLayer's typed Python SDK at `LATEST_FINAL`; in CLI-signer mode an ephemeral read-only account is held in memory only because the SDK requires a caller address. Writes still use the named CLI wallet, and wallet secrets are never read or exported. A separate explicit deploy command can deploy a selected source once and reconcile an interrupted deployment; the live scenario suite does not redeploy.

## Supported consumers

The interface is intended for independent procurement executors, DAO automation contracts, and delegated service-agent contracts. Consumers must bind their own action to the exact receipt and must wait for finality before relying on a result. See [Integration](docs/INTEGRATION.md) for the pull-based flow and its asynchronous cross-contract limits.

## Security and readiness

See [Security](docs/SECURITY.md), [Consensus](docs/CONSENSUS.md), and [Decision](DECISION.md). Submission readiness is evidence-based: the live network status, source parity, Git state, and remaining blockers are in [Deployment](docs/DEPLOYMENT.md) and [SUBMISSION.md](SUBMISSION.md). A passing local test alone is not a deployment or finality claim.
