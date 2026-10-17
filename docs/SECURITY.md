# Security model

## Assets and trust boundaries

BoundaryOS stores principal-owned policy versions, agent/delegation relationships, action proposals, spend counters, and authorization receipts. It does not custody GEN or execute an external business action. A downstream consumer must check the receipt before performing the action.

Authenticated principals, agents, consumers, and the deployer are identified from GenLayer sender addresses. A string inside a policy, action, evidence claim, or LLM response never establishes identity or authority.

## Deterministic invariants

- Principal admission is an owner-controlled step with a fixed 16-principal ceiling. This makes onboarding dependent on the deployer.
- An admitted principal must approve an exact agent address before that address can register itself. Registered agents plus pending approvals are bounded to eight per principal and 128 per contract. An unapproved Sybil cannot consume a principal's agent quota. Principals can cancel their pending approvals, and the contract owner can cancel a pending approval to recover a slot if the principal is unavailable. Each principal can also hold at most four active policies; global limits are 64 policies.
- Only the policy owner creates later policy versions, revokes a policy, or manages consumers.
- Policy versions are append-only. An update makes older receipts stale for current consumption.
- Agent actions are bounded JSON with a canonical digest, a policy version, and a strictly increasing per-agent nonce. Proposals expire after ten minutes; successful receipts expire within five minutes of evaluation and never beyond policy/proposal expiry.
- Amounts use integer arithmetic, one explicit unit, per-action caps, and a policy-wide time-window aggregate cap shared by every delegated child. A successful authorization reserves quota at evaluation (or owner approval); the counter records granted authorization allowance, not verified external spending or execution. This conservative charge avoids concurrent over-authorization but may count an unused allowance until the window changes.
- Explicit action denies, scope limits, unit mismatches, invalid windows, aggregate limits, frozen agents, revoked policies/delegations, stale versions, and replay are decided without AI.
- Delegation depth is at most four edges from the policy root. The resolver validates the ancestry to that registered root, then checks each link from root to leaf: policy ID, parent-child relation, common principal, ancestor freeze/revocation/expiry, nonempty bounded time window, action type subset, amount cap, and exact purpose equality. Cycles, wrong roots, and malformed links fail closed.
- The deployer can freeze all authorization. The policy owner or agent can freeze an agent; only the policy owner can unfreeze it.
- A consumer must be allowlisted and can consume a receipt only once, for the exact action digest, while policy, agent, delegation, and receipt remain live.
- The receipt digest commits to its canonical fields, including consumption status and consuming address; consumption recomputes the digest after those fields change.
- A human owner may resolve semantic ambiguity only after the same deterministic gates pass again.

## Evidence and AI limits

The only supported evidence mode is `CLAIM_ONLY`. Purpose text and evidence strings are bounded assertions in transaction calldata. Validators independently classify the same claims, but they do not retrieve or authenticate the referenced supplier, purchase, or external event. Receipt field `evidence_provenance` is always `CALLER_ASSERTED`.

Live integration checkpoints store public transaction identifiers, nonces, hashes of request arguments, and observed public state only. They never store wallet credentials or complete private signing material. A persisted write intent with no recovered transaction identifier is treated as ambiguous and is never automatically resent; operators must reconcile the public signer nonce and transaction state before manually resolving that checkpoint. Runtime checkpoint files are Git-ignored.

The live harness supports either explicitly configured SDK signers or the installed GenLayer CLI's named-wallet signing path. For CLI signing, the harness selects and verifies the named public accounts and delegates signing to the CLI SDK. It does not read, copy, export, print, or persist wallet keys or keystore contents. Checkpoint files contain public transaction IDs, nonces, request-argument digests, consensus results, and observed public state only. The CLI account flow was exercised successfully on Studionet for the diagnostic suite. This behavior depends on the user's authorized local CLI profile and is not reproduced by configuring raw keys in project files.

The semantic model can be wrong or jointly persuaded by adversarial content. The validator equivalence check is substantive about the decision enum, but consensus is not an oracle for whether a caller's claims are true. Semantic disagreement causes protocol non-finality, not approval. Ambiguity may be sent to authenticated human review; deterministic constraints remain absolute.

## Denial precedence and conflicts

Policy conflict classification is a certificate for the observed gate: explicit hard deny, semantic purpose conflict, semantic ambiguity, human review outcome, deterministic boundary denial, or none. It is not a finding of fraud. Hard deny and deterministic limits take precedence over semantic fit and manual review.

The policy-wide aggregate cap is the authority-laundering guard in v1: related actions cannot evade the same declared cap by changing agent, nonce, or action ID within the window. It can also deny unrelated purchases after the shared budget is exhausted; it does not label those actions collusion. Semantic linkage detection is intentionally not claimed.

## Availability and bounds

The current source candidate bounds JSON inputs and text; admits at most 16 principals; reserves at most eight combined registered-agent and pending-approval slots per principal and 128 across the instance; allows four active policies per principal and 64 globally; and caps the instance at 32 immutable versions per policy, 112 live delegations, 16 consumers per policy, 2,048 active proposals, and 16 active proposals per agent. These are concurrent/active quotas where reclamation is provided, rather than lifetime creation counters. Each policy-version spend record stores only the active window bucket; an observed backward consensus-time bucket fails closed instead of resetting the accumulated spend.

Pending agent approvals can be canceled by their approving principal or the contract owner; a principal cannot release its admission while any approval, agent, or policy remains. An agent can unregister only after its policy is revoked/expired (or its delegation revoked/expired), its children are removed, and its active actions have been reclaimed. Pending actions can be reclaimed after their ten-minute proposal window; evaluated ALLOW receipts remain stored until expiry, and other evaluated records can be removed once their decision is no longer live. A revoked or expired policy can be reclaimed only after all policy agents and active actions have been removed. Reclamation deletes the related bounded versions, consumers, spend buckets, receipts, actions, and indexes. Consumers can be removed to release allowlist slots. Policy instance generations remain monotonic so a reclaimed/recreated policy ID does not recreate old action IDs.

These limits prevent unbounded accumulation from ordinary active use and permit safe reuse after expiry or revocation. They do not guarantee service availability if an owner or principal refuses to perform required cleanup. The deployer controls principal admission, and the policy owner controls policy/consumer lifecycle. The instance rejects writes at any active capacity boundary until the corresponding eligible state is reclaimed.

Consensus disagreement, malformed LLM output, or network unavailability may make evaluation non-final. Consumers must fail closed and may retry with a new nonce only when the previous proposal's state is known.

## Explicit exclusions

BoundaryOS is not KYC, an identity oracle, a payment/escrow platform, a web monitor, or a general prompt-injection detector. It cannot stop actions performed without a consumer check. There is no cross-contract atomicity guarantee established by this repository yet; see [Integration](INTEGRATION.md).
## Verified release instance

The corrected source is deployed on Studionet at `0xe6b915d1DAb0EC9035D07368938413798d77c959`; deployment finality and retrieved source parity are recorded in [the deployment record](DEPLOYMENT.md) and [machine-readable release evidence](evidence/principal-approval-release.json). Live tests verified semantic match and mismatch, deterministic denial, root receipt consumption and replay rejection, a delegation-boundary rejection, and delegated child action evaluation as `ALLOW / MATCH`.

The delegated child receipt has not been consumed. Its consumer call has an unresolved hashless write intent at signer nonce `441`, and the harness correctly refuses to resend it. Consumer recovery/repeated completion, live quota, freeze, revocation, and resource reclamation remain unverified on this deployment. The older `0x7d...` and `0xb95...` instances are historical evidence only; their results do not establish behavior for the corrected address. The release is not submission-ready. In all instances, receipt provenance remains `CALLER_ASSERTED`; no external evidence is independently authenticated.
