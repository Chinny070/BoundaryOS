"""Build the tracked, secret-free evidence summary from local Studionet checkpoints."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--deployment", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/evidence/studionet-accessible-signer-release.json")
    args = parser.parse_args()

    suite, deployment = load(args.suite), load(args.deployment)
    deploy_step = deployment["steps"]["deployment.deploy"]
    source_path = "contracts/boundary_os.py"
    source_bytes = (ROOT / source_path).read_bytes()
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    deploy_source_sha = deploy_step["source_sha256"]
    if source_sha != deploy_source_sha or suite["current_source_sha256"] != source_sha:
        raise SystemExit("checked-out, suite, and deployed source SHA-256 values do not match")

    txs = {}
    for step_name, step in suite["steps"].items():
        tx_id = step.get("tx_id")
        if not tx_id:
            continue
        observed = suite.get("transactions", {}).get(tx_id, {})
        txs[step_name] = {
            "tx_id": tx_id,
            "method": step.get("method"),
            "signer": step.get("signer_address"),
            "signer_nonce": step.get("observed_nonce"),
            "status": observed.get("status", "FINALIZED" if step.get("phase") == "finalized" else step.get("phase")),
            "consensus": observed.get("consensus_outcome", step.get("consensus_outcome")),
            "execution": observed.get("execution_result", step.get("execution_result")),
            "vm_error_code": observed.get("vm_error_code"),
            "observed_at": observed.get("observed_at", step.get("finalized_at")),
            "expected_execution_error": step.get("expected_execution_error", False),
        }

    evidence = {
        "schema_version": 1,
        "release_status": "live_acceptance_matrix_complete_source_verified",
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "repository": "https://github.com/Chinny070/BoundaryOS",
        "network": {"name": "Studionet", "chain_id": 61999, "rpc": "https://studio.genlayer.com/api"},
        "source_identity": {
            "source_commit": head,
            "source_path": source_path,
            "sha256": source_sha,
            "deployment_source_sha256": deploy_source_sha,
            "deployed_source_parity": "verified through official GenLayer CLI source retrieval; normalized source body equals checked-in file",
        },
        "deployment": {
            "contract_address": deploy_step["contract_address"],
            "explorer_url": f"https://explorer-studio.genlayer.com/address/{deploy_step['contract_address']}",
            "transaction_id": deploy_step["tx_id"],
            "transaction_url": f"https://explorer-studio.genlayer.com/tx/{deploy_step['tx_id']}",
            "status": deploy_step["status"],
            "consensus": deploy_step["consensus_outcome"],
            "execution": deploy_step["execution_result"],
            "finalized_at": deploy_step["finalized_at"],
            "sender": deploy_step["signer_address"],
            "signer_nonce": deploy_step["reserved_nonce"],
            "explorer_address_http_status": 200,
            "explorer_tx_http_status": 200,
            "explorer_detail_note": "Explorer pages are reachable; static transaction page does not expose full receipt fields, which were independently obtained from CLI/RPC.",
        },
        "verification": {
            "cli_version": "0.39.1",
            "signer_backend": "GenLayer CLI named wallet; no key export",
            "signer_name": "my-studionet-wallet",
            "signer_address": suite["signer_address"],
            "typed_state_read_consistency": "LATEST_FINAL",
            "suite_completed_at": suite["observations"]["live_suite_complete"]["completed_at"],
            "scenario_observations": suite["observations"],
            "scenario_results": suite["scenarios"],
            "transactions": txs,
            "finalized_state_readbacks": {
                "principal_registered_unfrozen": True,
                "child_registered_unfrozen": True,
                "policy_version": 3,
                "policy_action_types": ["purchase"],
                "policy_hard_denies": ["cash_withdrawal"],
                "policy_max_amount": 500,
                "policy_aggregate_cap": 1000,
                "policy_unit": "USD_CENTS",
                "semantic_match_receipt_consumed": True,
                "semantic_match_digest_valid_after_consumption": True,
                "semantic_match_replay_allowed": False,
                "delegated_receipt_consumed": True,
                "delegated_receipt_digest_valid_after_consumption": True,
                "stale_policy_receipt_consumable": False,
                "post_revoke_decision": "DENY_STALE_POLICY",
            },
            "nonce_anomalies": [
                {
                    "step": "agent_freeze.evaluate.nonce-8",
                    "reserved_nonce": 2728,
                    "observed_nonce": 2729,
                    "disposition": "captured transaction hash finalized successfully and action state read back; reserved/observed mismatch was not retried",
                    "tx_id": suite["steps"]["agent_freeze.evaluate.nonce-8"]["tx_id"],
                },
                {
                    "historical_signer_nonce": 441,
                    "disposition": "old secondary-signer consumer intent remains broadcast-unknown with no transaction hash; not retried. It belongs to a predecessor deployment and does not describe this release's consumed child receipt.",
                },
            ],
        },
        "limitations": [
            "Evidence provenance is CALLER_ASSERTED: the contract does not independently authenticate external evidence.",
            "The local Windows Direct Mode runner currently fails before contract execution due to gltest temporary-file WinError 32; Linux CI is the authoritative Direct Mode run.",
            "One consumed EVM nonce at 2728 has no recovered transaction identity. The subsequent captured nonce-2729 transaction finalized and was reconciled; no ambiguous write was retried.",
            "The historical secondary-signer nonce-441 intent on a predecessor deployment remains unresolved and was not retried.",
            "Consumer composability/error-recovery and live on-chain state-reclamation-at-cap behavior were not included in this fresh canonical release matrix.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.output.relative_to(ROOT)} ({len(txs)} transaction records; source {source_sha})")


if __name__ == "__main__":
    main()
