# v0.1.0
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

"""Test-only two-stage consumer for BoundaryOS asynchronous messages."""

import hashlib
import json

from genlayer import *


MAX_CONSUMPTION_RETRIES = 2


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _consumed_receipt_proves_operation(
    receipt: dict[str, object],
    action_id: str,
    action_digest: str,
    consumer_address: str,
    boundary_address: str,
    chain_id: int,
) -> bool:
    """Verify the finalized BoundaryOS consumption commitment for completion."""
    committed = dict(receipt)
    stored_digest = str(committed.pop("receipt_digest", ""))
    calculated_digest = hashlib.sha256(_canonical(committed).encode("utf-8")).hexdigest()
    return (
        len(stored_digest) == 64
        and stored_digest == calculated_digest
        and receipt.get("action_id") == action_id
        and receipt.get("action_digest") == action_digest
        and receipt.get("decision") == "ALLOW"
        and receipt.get("consumed") is True
        and str(receipt.get("consumed_by", "")).lower() == consumer_address.lower()
        and receipt.get("chain_id") == chain_id
        and str(receipt.get("boundary_contract", "")).lower() == boundary_address.lower()
    )


@gl.contract_interface
class BoundaryOSInterface:
    class View:
        def can_consume_authorization(self, action_id: str, consumer_address: str) -> bool: ...
        def get_receipt(self, action_id: str) -> str: ...
        def preview_action_id(self, policy_id: str, agent_address: str, nonce: int, action_json: str) -> str: ...
        def get_action(self, action_id: str) -> str: ...

    class Write:
        def register_agent(self, principal_address: str) -> None: ...
        def submit_action(self, policy_id: str, nonce: int, action_json: str) -> None: ...
        def evaluate_action(self, action_id: str) -> None: ...
        def consume_authorization(self, action_id: str, expected_action_digest: str) -> str: ...


class BoundaryConsumer(gl.Contract):
    boundary: Address
    pending: TreeMap[str, str]
    completed: TreeMap[str, bool]
    retry_count: TreeMap[str, u64]

    def __init__(self, boundary_address: str) -> None:
        self.boundary = Address(boundary_address)

    @gl.public.write
    def register_as_agent(self, principal_address: str) -> None:
        BoundaryOSInterface(self.boundary).emit(on="finalized").register_agent(principal_address)

    @gl.public.write
    def submit_delegated_action(
        self, policy_id: str, nonce: int, expected_action_id: str, action_json: str
    ) -> None:
        boundary = BoundaryOSInterface(self.boundary)
        expected = boundary.view().preview_action_id(
            policy_id, str(gl.message.contract_address), nonce, action_json
        )
        if expected != expected_action_id:
            raise gl.vm.UserError("delegated action ID does not match BoundaryOS preview")
        boundary.emit(on="finalized").submit_action(policy_id, nonce, action_json)

    @gl.public.write
    def evaluate_delegated_action(self, action_id: str) -> None:
        boundary = BoundaryOSInterface(self.boundary)
        action_raw = boundary.view().get_action(action_id)
        if not action_raw:
            raise gl.vm.UserError("delegated action is absent")
        action = json.loads(action_raw)
        if action.get("agent", "").lower() != str(gl.message.contract_address).lower():
            raise gl.vm.UserError("delegated action belongs to another agent")
        if action.get("state") != "PENDING":
            raise gl.vm.UserError("delegated action is not pending")
        boundary.emit(on="finalized").evaluate_action(action_id)

    @gl.public.write
    def request_protected_operation(self, action_id: str, action_digest: str) -> None:
        if self.pending.get(action_id, "") or self.completed.get(action_id, False):
            raise gl.vm.UserError("consumer action is already pending or completed")
        boundary = BoundaryOSInterface(self.boundary)
        consumer_address = str(gl.message.contract_address)
        if not boundary.view().can_consume_authorization(action_id, consumer_address):
            raise gl.vm.UserError("BoundaryOS authorization is absent, stale, or not consumable")
        receipt_raw = boundary.view().get_receipt(action_id)
        if not receipt_raw:
            raise gl.vm.UserError("BoundaryOS receipt is absent")
        receipt = json.loads(receipt_raw)
        if receipt.get("action_digest") != action_digest:
            raise gl.vm.UserError("consumer action digest does not match BoundaryOS receipt")
        self.pending[action_id] = action_digest
        self.retry_count[action_id] = u64(0)
        boundary.emit(on="finalized").consume_authorization(action_id, action_digest)

    @gl.public.write
    def request_protected_operation_with_test_child_error(
        self, action_id: str, action_digest: str
    ) -> None:
        """Emit one genuine failing child transaction to test bounded recovery."""
        if self.pending.get(action_id, "") or self.completed.get(action_id, False):
            raise gl.vm.UserError("consumer action is already pending or completed")
        boundary = BoundaryOSInterface(self.boundary)
        consumer_address = str(gl.message.contract_address)
        if not boundary.view().can_consume_authorization(action_id, consumer_address):
            raise gl.vm.UserError("BoundaryOS authorization is absent, stale, or not consumable")
        receipt_raw = boundary.view().get_receipt(action_id)
        if not receipt_raw:
            raise gl.vm.UserError("BoundaryOS receipt is absent")
        receipt = json.loads(receipt_raw)
        if receipt.get("action_digest") != action_digest:
            raise gl.vm.UserError("consumer action digest does not match BoundaryOS receipt")
        self.pending[action_id] = action_digest
        self.retry_count[action_id] = u64(0)
        # This test-only call uses a well-formed but incorrect digest. The
        # BoundaryOS child transaction must finalize with a contract error.
        boundary.emit(on="finalized").consume_authorization(action_id, "0" * 64)

    @gl.public.write
    def retry_pending_consumption(self, action_id: str) -> None:
        expected_digest = self.pending.get(action_id, "")
        if not expected_digest or self.completed.get(action_id, False):
            raise gl.vm.UserError("consumer action is not pending")
        attempts = int(self.retry_count.get(action_id, u64(0)))
        if attempts >= MAX_CONSUMPTION_RETRIES:
            raise gl.vm.UserError("consumer receipt retry limit reached")
        boundary = BoundaryOSInterface(self.boundary)
        consumer_address = str(gl.message.contract_address)
        if not boundary.view().can_consume_authorization(action_id, consumer_address):
            raise gl.vm.UserError("BoundaryOS authorization is no longer consumable")
        self.retry_count[action_id] = u64(attempts + 1)
        boundary.emit(on="finalized").consume_authorization(action_id, expected_digest)

    @gl.public.write
    def complete_protected_operation(self, action_id: str) -> None:
        expected_digest = self.pending.get(action_id, "")
        if not expected_digest or self.completed.get(action_id, False):
            raise gl.vm.UserError("consumer action is not pending")
        boundary = BoundaryOSInterface(self.boundary)
        receipt_raw = boundary.view().get_receipt(action_id)
        if not receipt_raw:
            raise gl.vm.UserError("consumed BoundaryOS receipt is absent")
        receipt = json.loads(receipt_raw)
        if not _consumed_receipt_proves_operation(
            receipt,
            action_id,
            expected_digest,
            str(gl.message.contract_address),
            str(self.boundary),
            int(gl.message.chain_id),
        ):
            raise gl.vm.UserError("finalized BoundaryOS receipt does not authorize this operation")
        # This test-only consumer records the protected operation. It performs
        # no payment or external side effect.
        self.completed[action_id] = True
        del self.pending[action_id]
        if action_id in self.retry_count:
            del self.retry_count[action_id]

    @gl.public.view
    def operation_completed(self, action_id: str) -> bool:
        return self.completed.get(action_id, False)
