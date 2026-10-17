import ast
import hashlib
import json
from pathlib import Path

import pytest


_FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "boundary_consumer.py"
_SOURCE = _FIXTURE_PATH.read_text(encoding="utf-8")
_TREE = ast.parse(_SOURCE)
_HELPERS = ast.Module(
    body=[node for node in _TREE.body if isinstance(node, ast.FunctionDef) and node.name in {"_canonical", "_consumed_receipt_proves_operation"}],
    type_ignores=[],
)
_NAMESPACE = {"hashlib": hashlib, "json": json}
exec(compile(_HELPERS, str(_FIXTURE_PATH), "exec"), _NAMESPACE)
_proves = _NAMESPACE["_consumed_receipt_proves_operation"]
_canonical = _NAMESPACE["_canonical"]


ACTION_ID = "a" * 64
ACTION_DIGEST = "b" * 64
CONSUMER_ADDRESS = "0x" + "1" * 40
BOUNDARY_ADDRESS = "0x" + "2" * 40
CHAIN_ID = 61999


def _receipt(**changes):
    value = {
        "action_id": ACTION_ID,
        "action_digest": ACTION_DIGEST,
        "decision": "ALLOW",
        "consumed": True,
        "consumed_by": CONSUMER_ADDRESS.upper().replace("0X", "0x"),
        "chain_id": CHAIN_ID,
        "boundary_contract": BOUNDARY_ADDRESS.upper().replace("0X", "0x"),
        "expires_at": 1,
    }
    value.update(changes)
    value["receipt_digest"] = hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()
    return value


def _check(receipt):
    return _proves(
        receipt,
        ACTION_ID,
        ACTION_DIGEST,
        CONSUMER_ADDRESS,
        BOUNDARY_ADDRESS,
        CHAIN_ID,
    )


def test_valid_finalized_consumption_proof_allows_delayed_completion_after_expiry():
    receipt = _receipt(expires_at=1)
    assert _check(receipt)


@pytest.mark.parametrize(
    "changes",
    [
        {"action_id": "c" * 64},
        {"action_digest": "d" * 64},
        {"decision": "DENY_PURPOSE"},
        {"consumed": False},
        {"consumed_by": "0x" + "3" * 40},
        {"chain_id": 61998},
        {"boundary_contract": "0x" + "4" * 40},
    ],
)
def test_consumption_proof_rejects_identity_or_authorization_mismatch(changes):
    assert not _check(_receipt(**changes))


def test_consumption_proof_rejects_tampered_committed_field():
    receipt = _receipt()
    receipt["consumed_by"] = "0x" + "5" * 40
    assert not _check(receipt)


def test_consumer_fixture_declares_the_child_consumption_write():
    source = _FIXTURE_PATH.read_text(encoding="utf-8")
    declaration = (
        "def consume_authorization(self, action_id: str, expected_action_digest: str) -> str"
    )
    assert declaration in source
