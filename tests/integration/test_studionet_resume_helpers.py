import json
import pytest
from genlayer_py.types import TransactionHashVariant

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
    is_transient_sdk_read_error,
    _finalized_no_majority_without_execution,
    _finalized_contract_execution_error,
    _record_action_nonce,
    parse_cli_accounts,
    scenario_step,
    _resolve_cli_entry,
    verify_legacy_cli_encoding,
    reconcile_checkpoint_before_writes,
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


def test_finalized_vm_error_is_distinguished_from_unresolved_broadcast():
    failed = {
        "status": "FINALIZED",
        "consensus_outcome": "MAJORITY_AGREE",
        "execution_result": "ERROR",
        "classification": "contract_execution_failure",
    }
    assert _finalized_contract_execution_error(failed)
    assert not _finalized_contract_execution_error({**failed, "status": "PROPOSING"})
    assert not _finalized_contract_execution_error({**failed, "execution_result": "SUCCESS"})
    assert not _finalized_contract_execution_error({**failed, "classification": "consensus_failure"})


def test_resumed_action_readback_advances_application_nonce_high_water(tmp_path):
    checkpoint = Checkpoint(tmp_path / "checkpoint.json", "0xc", "0xs", "abc")
    try:
        checkpoint.data["last_action_nonce"] = 5
        _record_action_nonce(checkpoint, 6)
        _record_action_nonce(checkpoint, 4)
        assert checkpoint.data["last_action_nonce"] == 6
    finally:
        checkpoint.close()


def test_resume_mode_reconciles_one_step_without_enabling_suite_writes():
    from studionet_resume import main

    # Argument validation is local and runs before RPC; this combination must
    # be rejected to avoid a resume command unexpectedly proceeding to writes.
    from studionet_resume import VerificationError

    with pytest.raises(VerificationError, match="read/reconcile-only"):
        main(["--resume-step", "setup.create_policy", "--run-live-suite"])


def test_live_suite_refuses_non_cli_signing_backend():
    from studionet_resume import main

    with pytest.raises(VerificationError, match="pinned CLI-backed named-wallet signer"):
        main(["--run-live-suite", "--signer-backend", "sdk"])


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


def test_cli_entry_fails_closed_on_wrong_version_and_accepts_only_legacy_bundle(tmp_path, monkeypatch):
    package = tmp_path / "node_modules" / "genlayer"
    entry = package / "dist" / "index.js"
    entry.parent.mkdir(parents=True)
    (package / "package.json").write_text(json.dumps({"name": "genlayer", "version": "0.40.0-rc.3"}))
    legacy_fixture = (
        'ADD_TRANSACTION_ABI_V5; type: "function"; '
        'var CONSENSUS_MAIN_CONTRACT2 = { abi: [{ inputs: ['
        '{ type: "address" }, { type: "address" }, { type: "uint256" }, '
        '{ type: "uint256" }, { type: "bytes" }], name: "addTransaction" }] }; '
        'var CONSENSUS_DATA_CONTRACT2; '
        'var studionet = defineChain({ consensusMainContract: CONSENSUS_MAIN_CONTRACT2 }); '
        'var VALIDATOR_WALLET_ABI;'
    )
    entry.write_text(legacy_fixture)
    monkeypatch.setenv("BOUNDARYOS_GENLAYER_CLI_ENTRY", str(entry))
    with pytest.raises(VerificationError, match="requires genlayer@0.39.1"):
        _resolve_cli_entry()

    (package / "package.json").write_text(json.dumps({"name": "genlayer", "version": "0.39.1"}))
    assert verify_legacy_cli_encoding()["transaction_abi"] == "ADD_TRANSACTION_ABI_V5"
    entry.write_text(legacy_fixture + " ADD_TRANSACTION_ABI_WITH_FEES")
    with pytest.raises(VerificationError, match="legacy transaction encoder"):
        verify_legacy_cli_encoding()


def test_live_checkpoint_preflight_blocks_unresolved_broadcast(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    checkpoint = Checkpoint(tmp_path / ".boundaryos" / "checkpoint.json", "0xc", "0xs", "abc")
    try:
        checkpoint.data["steps"]["ambiguous"] = {
            "phase": "broadcast_unknown", "signer_address": "0xs", "reserved_nonce": 42,
        }
        verifier = StudionetVerifier(
            "0xc", checkpoint, type("Account", (), {"address": "0xs"})(), object(), cli_signing=True
        )
        calls = []

        def reconcile(step, max_polls):
            calls.append((step, max_polls))
            raise VerificationError("historical broadcast disposition unknown")

        verifier.reconcile = reconcile
        with pytest.raises(VerificationError, match="historical broadcast disposition unknown"):
            reconcile_checkpoint_before_writes(verifier, 3)
        assert calls == [("ambiguous", 3)]
    finally:
        checkpoint.close()


def test_cli_signer_reads_use_typed_sdk_at_finalized_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    checkpoint = Checkpoint(tmp_path / ".boundaryos" / "checkpoint.json", "0xcontract", "0xsigner", "abc")
    try:
        verifier = StudionetVerifier(
            "0xcontract", checkpoint, type("Account", (), {"address": "0xsigner"})(),
            type("Client", (), {})(), cli_signing=True, cli_active_account="my-wallet",
        )
        calls = []
        def sdk_read(**kwargs):
            calls.append(kwargs)
            return {"registered": True}

        verifier.client.read_contract = sdk_read
        assert verifier.read("get_agent", ["0xsigner"]) == {"registered": True}
        assert calls == [{
            "address": "0xcontract",
            "function_name": "get_agent",
            "args": ["0xsigner"],
            "transaction_hash_variant": TransactionHashVariant.LATEST_FINAL,
        }]
    finally:
        checkpoint.close()


def test_sdk_finalized_read_retries_transient_transport_and_fails_closed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    checkpoint = Checkpoint(tmp_path / ".boundaryos" / "checkpoint.json", "0xcontract", "0xsigner", "abc")
    try:
        verifier = StudionetVerifier(
            "0xcontract", checkpoint, type("Account", (), {"address": "0xsigner"})(),
            type("Client", (), {})(), cli_signing=True,
        )
        attempts = []

        def transient_then_success(**_kwargs):
            attempts.append(1)
            if len(attempts) == 1:
                raise RuntimeError("HTTP 502 Bad Gateway")
            return {"registered": True}

        verifier.client.read_contract = transient_then_success
        monkeypatch.setattr("studionet_resume.time.sleep", lambda _delay: None)
        assert verifier.read("get_agent", ["0xsigner"]) == {"registered": True}
        assert len(attempts) == 2

        attempts.clear()
        def execution_error(**_kwargs):
            attempts.append(1)
            raise RuntimeError("execution failed")

        verifier.client.read_contract = execution_error
        with pytest.raises(RpcFailure, match="GenLayer SDK finalized read get_agent failed"):
            verifier.read("get_agent", ["0xsigner"])
        assert len(attempts) == 1
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
    assert _finalized_no_majority_without_execution({
        "status": "FINALIZED", "consensus_outcome": "NO_MAJORITY", "execution_result": None
    })
    assert not _finalized_no_majority_without_execution({
        "status": "ACCEPTED", "consensus_outcome": "NO_MAJORITY", "execution_result": None
    })
    assert not _finalized_no_majority_without_execution({
        "status": "FINALIZED", "consensus_outcome": "MAJORITY_AGREE", "execution_result": "SUCCESS"
    })


def test_sdk_read_error_classifier_does_not_retry_contract_or_argument_errors():
    assert is_transient_sdk_read_error("UnknownRpcError code=-1")
    assert is_transient_sdk_read_error("HTTP status code 502 Bad Gateway")
    assert not is_transient_sdk_read_error("InvalidInputRpcError code=-32000")
    assert not is_transient_sdk_read_error("contract execution reverted")
    assert is_transient_sdk_read_error("Windows status 0xC0000409 (3221226505)")


def test_expired_scenario_retries_receive_distinct_checkpoints():
    assert scenario_step("semantic_match", "submit", 1) == "semantic_match.submit"
    assert scenario_step("semantic_match", "submit", 2) == "semantic_match.submit.nonce-2"
    assert scenario_step("semantic_match", "evaluate", 2) == "semantic_match.evaluate.nonce-2"
