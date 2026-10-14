import json

import pytest

from studionet_resume import (
    Checkpoint,
    ContractExecutionFailure,
    RpcFailure,
    classify_rpc_error,
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
