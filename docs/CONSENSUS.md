# Consensus design

## Exact consensus boundary

Only `BoundaryOS._semantic_decision` is nondeterministic. Identity, policy ownership/version, delegation ancestry, explicit hard denies, action scope, integer amounts, currency/unit, validity, freeze, nonce, aggregate quota, stale receipt checks, and one-time consumption are deterministic Python checks.

When an action passes all deterministic checks, the contract invokes:

```python
gl.vm.run_nondet_unsafe(leader_fn, validator_fn)
```

Both closures call `gl.nondet.exec_prompt` independently with the same bounded policy-purpose text, action type, declared purpose, and explicitly caller-asserted evidence claim. They return only one decision field: `fit` in `MATCH`, `MISMATCH`, or `UNCLEAR`.

## Leader and validator behavior

The leader parses a JSON response and admits only the exact one-key schema. Malformed shapes and unknown enum values normalize to `UNCLEAR`. The validator first requires a `gl.vm.Return`, checks its calldata type, exact key set, and enum, independently calls the model, validates that answer the same way, then compares the `fit` enum exactly. Explanatory prose is never part of the result.

A well-formed but false leader `MATCH` is rejected when independent validator judgment differs. A validator exception or disagreement is protocol-level non-agreement; it does not become a stored `REVIEW_REQUIRED` receipt. A model response of `UNCLEAR`, if accepted under the equivalence rule, is a contract-level review state. A stored receipt exists only after the enclosing GenLayer transaction finalizes.

## Mapping consensus to a decision

After consensus:

- `MATCH` becomes `ALLOW` only after deterministic gates have passed and the aggregate amount is charged.
- `MISMATCH` becomes `DENY_PURPOSE`.
- `UNCLEAR` becomes `REVIEW_REQUIRED`, which is not consumable unless the authenticated policy owner explicitly resolves it. That manual path repeats current deterministic checks and cannot bypass hard rules, quotas, revocation, freeze, expiry, or policy freshness.
- Deterministic denials do not call the model.

The prompt treats caller content as data, never authority. Even so, the contract does not prove model correctness or prevent both independent models from being persuaded by the same adversarial claim. Its security rests on deterministic gates bounding what a semantic false positive can authorize, and on consumers treating claims as claims.

## Finality

Contract storage records a decision only as part of the finalized state transition for that evaluation transaction. A local Direct Mode result, transaction submission, or `ACCEPTED` status is not a finalized authorization. Off-chain clients must wait for GenLayer `FINALIZED` and read at the finalized state. See the [official transaction/finality docs](https://docs.genlayer.com/developers/decentralized-applications/reading-data) and [GenLayer equivalence principle](https://docs.genlayer.com/developers/intelligent-contracts/equivalence-principle).

## What Direct Mode proves

Direct Mode tests exercise mocked leader and validator calls, typed output validation, enum normalization, deterministic gates, and the harness's validator replay. They do not prove that Studionet validators independently produced those outputs. Only the live integration test can provide that evidence, and only when the returned transaction receipt and final state confirm it.
