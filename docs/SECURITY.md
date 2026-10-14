# Security model

## Assets and trust boundaries

BoundaryOS stores principal-owned policy versions, agent/delegation relationships, action proposals, spend counters, and authorization receipts. It does not custody GEN or execute an external business action. A downstream consumer must check the receipt before performing the action.

Authenticated principals, agents, consumers, and the deployer are identified from GenLayer sender addresses. A string inside a policy, action, evidence claim, or LLM response never establishes identity or authority.

## Deterministic invariants

- Agent registration is initiated by the registering agent's sender address.
- Only the policy owner creates later policy versions, revokes a policy, or manages consumers.
- Policy versions are append-only. An update makes older receipts stale for current consumption.
- Agent actions are bounded JSON with a canonical digest, a policy version, and a strictly increasing per-agent nonce. Proposals expire after ten minutes; successful receipts expire within five minutes of evaluation and never beyond policy/proposal expiry.
- Amounts use integer arithmetic, one explicit unit, per-action caps, and a policy-wide time-window aggregate cap shared by every delegated child.
- Explicit action denies, scope limits, unit mismatches, invalid windows, aggregate limits, frozen agents, revoked policies/delegations, stale versions, and replay are decided without AI.
- Delegation depth is at most four; action type sets, amounts, time windows, and purpose boundaries cannot widen. Purpose boundaries must be exact matches.
- The deployer can freeze all authorization. The policy owner or agent can freeze an agent; only the policy owner can unfreeze it.
- A consumer must be allowlisted and can consume a receipt only once, for the exact action digest, while policy, agent, delegation, and receipt remain live.
- The receipt digest commits to its canonical fields, including consumption status and consuming address; consumption recomputes the digest after those fields change.
- A human owner may resolve semantic ambiguity only after the same deterministic gates pass again.

## Evidence and AI limits

The only supported evidence mode is `CLAIM_ONLY`. Purpose text and evidence strings are bounded assertions in transaction calldata. Validators independently classify the same claims, but they do not retrieve or authenticate the referenced supplier, purchase, or external event. Receipt field `evidence_provenance` is always `CALLER_ASSERTED`.

Live integration checkpoints store public transaction identifiers, nonces, hashes of request arguments, and observed public state only. They never store wallet credentials or complete private signing material. A persisted write intent with no recovered transaction identifier is treated as ambiguous and is never automatically resent; operators must reconcile the public signer nonce and transaction state before manually resolving that checkpoint. Runtime checkpoint files are Git-ignored.

The semantic model can be wrong or jointly persuaded by adversarial content. The validator equivalence check is substantive about the decision enum, but consensus is not an oracle for whether a caller's claims are true. Semantic disagreement causes protocol non-finality, not approval. Ambiguity may be sent to authenticated human review; deterministic constraints remain absolute.

## Denial precedence and conflicts

Policy conflict classification is a certificate for the observed gate: explicit hard deny, semantic purpose conflict, semantic ambiguity, human review outcome, deterministic boundary denial, or none. It is not a finding of fraud. Hard deny and deterministic limits take precedence over semantic fit and manual review.

The policy-wide aggregate cap is the authority-laundering guard in v1: related actions cannot evade the same declared cap by changing agent, nonce, or action ID within the window. It can also deny unrelated purchases after the shared budget is exhausted; it does not label those actions collusion. Semantic linkage detection is intentionally not claimed.

## Availability and bounds

Per-instance limits bound JSON inputs, text, agents (128), policies (64), versions (32 per policy), delegations (256), consumers (16 per policy), and proposals (4,096 lifetime). At capacity the instance rejects new state; there is no garbage-collection or rotation method. A pending proposal is agent-owned and expires after ten minutes, but still occupies one lifetime proposal slot.

Consensus disagreement, malformed LLM output, or network unavailability may make evaluation non-final. Consumers must fail closed and may retry with a new nonce only when the previous proposal's state is known.

## Explicit exclusions

BoundaryOS is not KYC, an identity oracle, a payment/escrow platform, a web monitor, or a general prompt-injection detector. It cannot stop actions performed without a consumer check. There is no cross-contract atomicity guarantee established by this repository yet; see [Integration](INTEGRATION.md).
