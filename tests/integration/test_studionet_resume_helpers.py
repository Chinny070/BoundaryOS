import json

import pytest

from studionet_resume import (
    CliAccount,
    Checkpoint,
    ConsensusFailure,
    ContractExecutionFailure,
    RpcFailure,
    StudionetVerifier,
    VerificationError,
    classify_rpc_error,
    encode_cli_write_intent,
    _consensus_outcome,
    derive_action_id,
    parse_cli_accounts,
)


def test_rpc_failure_classification_separates_contract_and_transport():
    assert classify_rpc_error({"code": -32000, "message": "execution failed", "data": {"receipt": {"execution_result": "ERROR"}}}) == "contract_execution"
    assert classify_rpc_error({"code": -32603, "message": "internal error"}) == "rpc_or_protocol"
    assert classify_rpc_error({"code": -32601, "message": "method not found"}) == "rpc_application"


def test_checkpoint_is_atomic_persistent_and_bound_to_public_identity(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / ".boundaryos" / "checkpoint.json"
    checkpoint = Checkpoint(path, "0xcontract", "0xsigner", "abc123")
    checkpoint.data["transactions"]["0xtx"] = {"status": "FINALIZED"}
    checkpoint.data["test_marker"] = "persisted"
    checkpoint.save()
    checkpoint.close()

    recovered = Checkpoint(path, "0xCONTRACT", "0xSIGNER", "def456")
    try:
        assert recovered.data["test_marker"] == "persisted"
        assert recovered.data["transactions"]["0xtx"]["status"] == "FINALIZED"
        assert recovered.data["current_source_sha256"] == "def456"
        serialized = path.read_text(encoding="utf-8")
        assert "private_key" not in serialized.lower()
    finally:
        recovered.close()


def test_checkpoint_lock_prevents_parallel_nonce_users(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    first = Checkpoint(tmp_path / ".boundaryos" / "a.json", "0xc", "0xs", "a")
    try:
        with pytest.raises(RuntimeError, match="checkpoint lock exists"):
            Checkpoint(tmp_path / ".boundaryos" / "b.json", "0xc", "0xs", "b")
    finally:
        first.close()


def test_known_malformed_action_id_is_detectably_not_a_digest():
    from studionet_resume import INCORRECT_RECORDED_ID, KNOWN_PROPOSAL_ID

    assert len(KNOWN_PROPOSAL_ID) == 64
    assert len(INCORRECT_RECORDED_ID) == 65


def test_resume_mode_reconciles_one_step_without_enabling_suite_writes():
    from studionet_resume import main

    # Argument validation is local and runs before RPC; this combination must
    # be rejected to avoid a resume command unexpectedly proceeding to writes.
    from studionet_resume import VerificationError

    with pytest.raises(VerificationError, match="read/reconcile-only"):
        main(["--resume-step", "setup.create_policy", "--run-live-suite"])


def test_cli_account_parser_keeps_only_public_identity_and_active_state():
    accounts, active = parse_cli_accounts(
        "my-studionet-wallet 0x" + "1" * 40 + " (active) (unlocked)\n"
        "bradbury-e2e 0x" + "2" * 40 + " (unlocked)\n"
        "locked-account 0x" + "3" * 40 + "\n"
    )
    assert active == "my-studionet-wallet"
    assert accounts["my-studionet-wallet"] == CliAccount("my-studionet-wallet", "0x" + "1" * 40, True)
    assert accounts["bradbury-e2e"].unlocked is True
    assert accounts["locked-account"].unlocked is False


def test_cli_sdk_adapter_preserves_typed_string_arguments():
    arguments = ["purchase-policy", "0x" + "a" * 40, '{"amount":17,"purpose":"office supplies"}', 5]
    intent = json.loads(encode_cli_write_intent("0xcontract", "create_policy", arguments, 3))
    assert intent["args"] == arguments
    assert intent["rotations"] == 3


def test_cli_signer_reads_use_sdk_adapter_instead_of_legacy_python_gen_call(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    checkpoint = Checkpoint(tmp_path / ".boundaryos" / "checkpoint.json", "0xcontract", "0xsigner", "abc")
    try:
        verifier = StudionetVerifier(
            "0xcontract", checkpoint, type("Account", (), {"address": "0xsigner"})(),
            type("Client", (), {"provider": type("Provider", (), {"url": "https://example.invalid"})()})(),
            cli_signing=True,
            cli_active_account="my-wallet",
        )
        calls = []
        monkeypatch.setattr(verifier, "_cli_read", lambda method, args: calls.append((method, args)) or {"registered": True})
        assert verifier.read("get_agent", ["0xsigner"]) == {"registered": True}
        assert calls == [("get_agent", ["0xsigner"])]
    finally:
        checkpoint.close()


def test_local_action_id_derivation_is_canonical_and_address_case_independent():
    action = {"action_type": "purchase", "amount": 25, "unit": "USD_CENTS", "purpose": "paper", "evidence_claim": "caller claim"}
    compact = json.dumps(action, sort_keys=True, separators=(",", ":"))
    spaced = json.dumps(action, sort_keys=True, indent=2)
    lower = "0xaffe15eec45b68835cc9e5b4ab85dd5deae8e70b"
    checksum = "0xaffE15eEc45b68835cc9E5B4Ab85dD5deaE8e70b"
    assert derive_action_id("policy-1", lower, 7, compact) == derive_action_id("policy-1", checksum, 7, spaced)


def test_consensus_failure_is_not_mislabeled_as_contract_execution():
    assert _consensus_outcome({"result": 5, "result_name": "NO_MAJORITY"}) == "NO_MAJORITY"
    assert _consensus_outcome({"result": 1}) == "MAJORITY_AGREE"
    assert _consensus_outcome({"result": 6}) is None
    assert issubclass(ConsensusFailure, RuntimeError)
