# Integration guide

BoundaryOS exposes a small JSON/string interface intended for procurement consumers, DAO automation, and delegated service agents. A consumer should first wait for the evaluation transaction to reach `FINALIZED`, then read the receipt at finalized state. An `ALLOW` result in a pending/accepted transaction is not yet authorization.

## Policy document

Pass `policy_json` with exactly these fields:

```json
{
  "action_types": ["purchase"],
  "hard_denies": ["cash_withdrawal"],
  "max_amount": 50000,
  "aggregate_cap": 150000,
  "unit": "USD_CENTS",
  "window_seconds": 86400,
  "valid_from": 0,
  "valid_until": 1900000000,
  "purpose": "purchase ordinary office supplies",
  "evidence_required": true,
  "evidence_mode": "CLAIM_ONLY"
}
```

`amount`, `max_amount`, and `aggregate_cap` are non-negative integers. Booleans and floats are rejected. All amounts in a policy use the same unit string; no currency conversion occurs. `valid_from` and `valid_until` are Unix seconds. `window_seconds` is between 1 second and 30 days. `aggregate_cap` must be at least `max_amount`. Action type identifiers are unique lowercase strings. `evidence_mode` must be `CLAIM_ONLY`; `evidence_required` determines whether the caller must include a non-empty claim.

## Action document

Pass `action_json` with exactly:

```json
{
  "action_type": "purchase",
  "amount": 1200,
  "unit": "USD_CENTS",
  "purpose": "buy printer paper for the office",
  "evidence_claim": "Caller claims supplier quote REF-123"
}
```

Action/evidence JSON is bounded. The stable action ID commits to policy ID and its monotonic instance generation, normalized agent address, nonce, and canonicalized action facts. `preview_action_id(...)` lets clients calculate that ID before submitting. Clients deriving it locally must include the current generation returned by `get_policy_instance(...)` as well as the canonical action digest. The receipt includes the action digest independently.

## Lifecycle

1. The deployer admits the principal with `admit_principal(principal_address)`; admission is bounded and owner-controlled. The agent then calls `register_agent(principal_address)` from its own address, selecting the principal that may create its policy. A child must select the same principal as its delegating parent.
2. The principal calls `create_policy(...)` for that registered agent.
3. Each child agent registers itself. Its parent calls `delegate_authority(...)` with a scope no broader than its own. A child can further delegate within the inherited bounds.
4. The principal authorizes consumer contract addresses with `authorize_consumer(...)`.
5. The agent calls `preview_action_id(...)` to compute the stable ID, then calls `submit_action(policy_id, nonce, action_json)`. The GenLayer write API returns a transaction receipt, so the ID is previewed instead of relying on a method return value in that receipt.
6. The proposing agent calls `evaluate_action(action_id)`. Wait for the GenLayer transaction to finalize. Protocol-level disagreement is not a receipt.
7. The consumer reads `get_receipt(action_id)` at finalized state and checks decision, action digest, policy digest/version, chain ID, BoundaryOS contract address, agent, and expiry.
8. A whitelisted consumer calls `consume_authorization(action_id, expected_action_digest)` once. It must observe the finalized consumption before treating the authorization as spent.

An external consumer must use GenLayer's supported contract/message API and must not assume a synchronous EVM-style cross-contract write. The test-only fixture in [`tests/fixtures/boundary_consumer.py`](../tests/fixtures/boundary_consumer.py) demonstrates a two-stage flow: it checks the current receipt, emits `consume_authorization` on parent finality, then requires a later transaction to read the consumed receipt at finalized state before recording its protected operation. A test-only method emits one child call with an intentionally incorrect digest to verify that a finalized child execution error leaves the receipt usable; a bounded retry then emits the correct consume call. Repeated completion is rejected. The fixture records no payment or external side effect. Its source is linted and schema-checked, but candidate live consumer evidence remains pending; see the [candidate verification record](evidence/resource-lifecycle-candidate.json).

GenLayer internal write messages are asynchronous and their child transaction reaches consensus independently. Therefore the flow is explicitly multi-transaction: submit the consumer request, wait for the emitted BoundaryOS consume transaction to finalize, then call the consumer completion method. A receipt consumption is not proof that the external operation occurred, and the repository does not claim atomic cross-contract authorization. See the official [Intelligent Contract interaction guide](https://docs.genlayer.com/developers/intelligent-contracts/features/interacting-with-intelligent-contracts) and [message lifecycle reference](https://docs.genlayer.com/developers/intelligent-contracts/features/messages).

## Receipt checks

`can_consume_authorization(action_id, consumer_address)` is a read-only convenience check. `consume_authorization` is authoritative and changes state. A receipt becomes unusable after policy update/revocation, emergency or agent freeze, delegated authority revocation/expiry, receipt expiry, mismatched digest, or prior consumption.

Do not interpret `semantic_fit` as verified evidence. `evidence_provenance` is `CALLER_ASSERTED`. A human review can approve only an ambiguous case, and the approval cannot override a deterministic denial.

For an off-chain GenLayerJS client, use the official `waitForFinalization` path before querying finalized state; see [GenLayer reading data](https://docs.genlayer.com/developers/decentralized-applications/reading-data). For contract-to-contract writes, see [Interacting with Intelligent Contracts](https://docs.genlayer.com/developers/intelligent-contracts/features/interacting-with-intelligent-contracts).
