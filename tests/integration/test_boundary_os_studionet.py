"""Live Studionet test. This deploys a disposable instance and uses real validators."""

import json
import hashlib

from gltest import get_contract_factory, get_default_account
from gltest.assertions import tx_execution_succeeded
from gltest.types import TransactionHashVariant, TransactionStatus
from gltest.utils import extract_contract_address


def _action_id(policy_id, agent_address, nonce, action_json):
    canonical_action = json.dumps(
        json.loads(action_json), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    action_digest = hashlib.sha256(canonical_action.encode("utf-8")).hexdigest()
    return hashlib.sha256(
        f"{policy_id}|{agent_address}|{nonce}|{action_digest}".encode("utf-8")
    ).hexdigest()


def _assert_finalized(receipt):
    assert tx_execution_succeeded(receipt), receipt
    status = receipt.get("status_name") or receipt.get("status")
    assert status == TransactionStatus.FINALIZED or status == "FINALIZED", receipt
    assert receipt.get("tx_id") or receipt.get("hash"), receipt


def _summary(receipt):
    round_data = receipt.get("last_round") or {}
    return {
        "tx_id": receipt.get("tx_id") or receipt.get("hash"),
        "status": receipt.get("status_name") or receipt.get("status"),
        "consensus": receipt.get("result_name"),
        "validator_votes": round_data.get("validator_votes_name"),
    }


def test_real_studionet_semantic_authorization_and_hard_deny():
    account = get_default_account()
    factory = get_contract_factory("BoundaryOS")
    deployment = factory.deploy_contract_tx(
        args=[],
        account=account,
        consensus_max_rotations=3,
        wait_interval=1000,
        wait_retries=90,
        wait_transaction_status=TransactionStatus.FINALIZED,
    )
    _assert_finalized(deployment)
    contract_address = extract_contract_address(deployment)
    print(json.dumps({"deployment": _summary(deployment), "contract_address": contract_address}), flush=True)
    contract = factory.build_contract(contract_address, account=account)

    registration = contract.register_agent(args=[account.address]).transact(
        consensus_max_rotations=3,
        wait_interval=1000,
        wait_retries=90,
        wait_transaction_status=TransactionStatus.FINALIZED,
    )
    _assert_finalized(registration)
    print(json.dumps({"registration": _summary(registration)}), flush=True)

    policy_json = json.dumps(
        {
            "action_types": ["purchase"],
            "hard_denies": ["cash_withdrawal"],
            "max_amount": 500,
            "aggregate_cap": 1000,
            "unit": "USD_CENTS",
            "window_seconds": 3600,
            "valid_from": 0,
            "valid_until": 4_000_000_000,
            "purpose": "buy plain A4 printer paper and ink toner for company office use",
            "evidence_required": True,
            "evidence_mode": "CLAIM_ONLY",
        }
    )
    policy_receipt = contract.create_policy(
        args=["live-smoke", account.address, policy_json]
    ).transact(
        consensus_max_rotations=3,
        wait_interval=1000,
        wait_retries=90,
        wait_transaction_status=TransactionStatus.FINALIZED,
    )
    _assert_finalized(policy_receipt)
    print(json.dumps({"policy": _summary(policy_receipt)}), flush=True)

    consumer_receipt = contract.authorize_consumer(
        args=["live-smoke", account.address]
    ).transact(
        consensus_max_rotations=3,
        wait_interval=1000,
        wait_retries=90,
        wait_transaction_status=TransactionStatus.FINALIZED,
    )
    _assert_finalized(consumer_receipt)
    print(json.dumps({"consumer": _summary(consumer_receipt)}), flush=True)

    action_json = json.dumps(
        {
            "action_type": "purchase",
            "amount": 250,
            "unit": "USD_CENTS",
            "purpose": "buy plain A4 printer paper and ink toner for company office use",
            "evidence_claim": "Caller claims public supplier quote REF-BOUNDARYOS-1",
        }
    )
    action_id = _action_id("live-smoke", account.address, 1, action_json)
    proposal_receipt = contract.submit_action(args=["live-smoke", 1, action_json]).transact(
        consensus_max_rotations=3,
        wait_interval=1000,
        wait_retries=90,
        wait_transaction_status=TransactionStatus.FINALIZED,
    )
    _assert_finalized(proposal_receipt)

    decision_receipt = contract.evaluate_action(args=[action_id]).transact(
        consensus_max_rotations=5,
        wait_interval=1000,
        wait_retries=180,
        wait_transaction_status=TransactionStatus.FINALIZED,
    )
    _assert_finalized(decision_receipt)
    result_json = contract.get_receipt(args=[action_id]).call(
        transaction_hash_variant=TransactionHashVariant.LATEST_FINAL
    )
    result = json.loads(result_json)
    assert result["decision"] == "ALLOW", result
    assert result["semantic_fit"] == "MATCH", result
    assert result["evidence_provenance"] == "CALLER_ASSERTED", result
    assert contract.can_consume_authorization(args=[action_id, account.address]).call(
        transaction_hash_variant=TransactionHashVariant.LATEST_FINAL
    ) is True

    consumption = contract.consume_authorization(
        args=[action_id, result["action_digest"]]
    ).transact(
        consensus_max_rotations=3,
        wait_interval=1000,
        wait_retries=90,
        wait_transaction_status=TransactionStatus.FINALIZED,
    )
    _assert_finalized(consumption)
    assert contract.can_consume_authorization(args=[action_id, account.address]).call(
        transaction_hash_variant=TransactionHashVariant.LATEST_FINAL
    ) is False

    # A hard-denied action is recorded but never enters semantic consensus.
    denied_json = json.dumps(
        {
            "action_type": "cash_withdrawal",
            "amount": 1,
            "unit": "USD_CENTS",
            "purpose": "withdraw cash for office expenses",
            "evidence_claim": "Caller claim only",
        }
    )
    denied_id = _action_id("live-smoke", account.address, 2, denied_json)
    denied_proposal = contract.submit_action(args=["live-smoke", 2, denied_json]).transact(
        consensus_max_rotations=3,
        wait_interval=1000,
        wait_retries=90,
        wait_transaction_status=TransactionStatus.FINALIZED,
    )
    _assert_finalized(denied_proposal)
    denied_receipt = contract.evaluate_action(args=[denied_id]).transact(
        consensus_max_rotations=3,
        wait_interval=1000,
        wait_retries=90,
        wait_transaction_status=TransactionStatus.FINALIZED,
    )
    _assert_finalized(denied_receipt)
    denied = json.loads(
        contract.get_receipt(args=[denied_id]).call(
            transaction_hash_variant=TransactionHashVariant.LATEST_FINAL
        )
    )
    assert denied["decision"] == "DENY_HARD_RULE", denied

    print(json.dumps({
        "disposable_contract": contract_address,
        "action_id": action_id,
        "authorization": _summary(decision_receipt),
        "receipt": result,
        "denied_action_id": denied_id,
        "hard_deny": _summary(denied_receipt),
    }, sort_keys=True))
