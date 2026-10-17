# BoundaryOS decision and collision review

## Primitive

**Thesis:** BoundaryOS lets an external consumer contract ask whether a particular authenticated agent action fits a principal's exact, versioned delegation, with deterministic security gates and validator-agreed semantic purpose interpretation.

The reusable boundary is **delegated authority**, not agent identity, agreement adjudication, escrow settlement, or emergency posture management. Three distinct consumers can use the same policy and receipt interface: procurement executors, DAO automation, and delegated service agents.

## Why GenLayer is load-bearing

Exact address, permission, unit, amount, expiry, quota, nonce, and revocation rules are ordinary deterministic code. A natural-language purpose comparison remains semantic: a purchase described as "replacement toner for the office" may fit a policy phrased as "office supplies," while "concert tickets" does not. The contract asks the leader and validators to classify the same bounded claims independently and accepts only matching typed criteria. Without GenLayer consensus, one model operator would author the decisive interpretation. GenLayer disagreement cannot create an approval.

The semantic judgment is intentionally modest. It does not verify a vendor, prove that a transaction happened, certify external evidence, or infer intent. The contract marks all submitted context `CALLER_ASSERTED`.

## Owner portfolio reviewed

Public repository inventory and READMEs were reviewed for these closest projects:

| Repository | Existing scope | BoundaryOS distinction |
|---|---|---|
| [AgentCourt](https://github.com/Chinny070/agentcourt) | Agent-to-agent service agreements, escrow, delivery disputes, web evidence, and consensus adjudication | BoundaryOS authorizes a proposed action before an external consumer executes it; it has no agreement lifecycle, escrow, dispute payout, or evidence retrieval |
| [ProofMesh](https://github.com/Chinny070/proofmesh) | Multi-source public identity control, continuity, trust credentials, and claim conflicts | BoundaryOS consumes authenticated chain sender identity and records a principal/agent relationship; it does not verify real-world or social identity |
| [LATCHKEY](https://github.com/Chinny070/latchkey) | Emergency constitutional adjudication and system-wide postures such as lock or recommission | BoundaryOS provides scoped per-policy authorization receipts; the deployer freeze is only an emergency stop |
| [Aurora Protocol](https://github.com/Chinny070/aurora-protocol) | Evidence-based obligation fulfillment and deterministic escrow settlement | BoundaryOS has no obligations, settlement, or funds; its decision target is delegated permission for one action |
| [Consensus](https://github.com/Chinny070/consensus) | General AI-verifiable agreements with criteria, evidence, escrow, lifecycle, and claims | BoundaryOS models authenticated authority chains, deterministic limits, policy freshness, and consumer-bound one-time receipts |
| [CLAUSE](https://github.com/Chinny070/clause-protocol) | Precommitted warranty adjudication | BoundaryOS does not adjudicate warranty fulfillment or settle remedies |

The portfolio has meaningful thematic overlap in AI-agent policy, contracts, and semantic judgments. BoundaryOS is distinct only when kept focused on **authority provenance and enforceable delegation bounds**. It must not expand into identity attestation, dispute adjudication, or treasury settlement.

## Scope decisions

- Hard prohibitions and numeric/resource bounds stay deterministic. Semantic output cannot overturn them.
- The only evidence mode in v1 is explicit `CLAIM_ONLY`; no unverifiable narrative is represented as independently proven.
- Delegated purpose must exactly preserve its parent's purpose boundary. Narrower natural-language sub-purpose delegation is deferred because this implementation has no deterministic proof of semantic subset.
- Delegation ancestry is resolved to the registered policy root and checked from root to leaf. Each child is compared only with its immediate parent, so valid progressive narrowing works while escalation, cycles, stale ancestry, and excessive depth fail closed.
- Shared aggregate quota is keyed by policy version and time window. A successful ALLOW reserves the requested amount when authorization is granted; this is conservative authorization accounting, not proof of an external payment or action. Multiple child agents cannot divide authority to bypass the declared cap.
- Policy diffs report deterministic expansion separately. A changed semantic purpose or a changed unit/window has unknown direction; the API returns `permissions_expanded: null` when no deterministic expansion is found but such a material change exists.
- A human owner can resolve only `REVIEW_REQUIRED`. The owner cannot override a hard deny, quota, freeze, expiry, revocation, or stale policy.
- State is capped: 128 agent registrations, 64 policies, 32 versions per policy, 256 delegations, 16 consumers per policy, and 4,096 proposals over one instance's lifetime. The contract exposes safe cleanup/reclamation for eligible unused, expired, revoked, and unreferenced records; live verification of filling every cap and reclaiming it is not part of this release's evidence. A deployment whose non-reclaimable lifetime proposal cap is exhausted must be replaced.
- Counterfactual simulation and semantic coordination detection are out of scope. A hypothetical verdict must never be consumable.

## Readiness decision

This document records the idea decision only. Passing Direct Mode and GenVM checks does not establish live validator consensus, deployment, source parity, or submission readiness. Those gates remain governed by [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).
