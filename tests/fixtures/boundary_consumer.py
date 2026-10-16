# v0.1.0
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

"""Test-only two-stage consumer for BoundaryOS asynchronous messages."""

import hashlib
import json
from datetime import datetime, timezone

from genlayer import *


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _now() -> int:
    return int(datetime.now(timezone.utc).timestamp())


@gl.contract_interface
class BoundaryOSInterface:
    class View:
        def can_consume_authorization(self, action_id: str, consumer_address: str) -> bool: ...
        def get_receipt(self, action_id: str) -> str: ...

    class Write:
        pass


class BoundaryConsumer(gl.Contract):
    boundary: Address
    pending: TreeMap[str, str]
    completed: TreeMap[str, bool]

    def __init__(self, boundary_address: str) -> None:
        self.boundary = Address(boundary_address)

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
        boundary.emit(on="finalized").consume_authorization(action_id, action_digest)

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
        stored_digest = receipt.pop("receipt_digest", "")
        calculated_digest = hashlib.sha256(_canonical(receipt).encode("utf-8")).hexdigest()
        if stored_digest != calculated_digest:
            raise gl.vm.UserError("BoundaryOS receipt digest is invalid")
        if (
            receipt.get("decision") != "ALLOW"
            or receipt.get("consumed") is not True
            or receipt.get("consumed_by", "").lower() != str(gl.message.contract_address).lower()
            or receipt.get("action_digest") != expected_digest
            or _now() >= int(receipt.get("expires_at", 0))
        ):
            raise gl.vm.UserError("finalized BoundaryOS receipt does not authorize this operation")
        # This test-only consumer records the protected operation. It performs
        # no payment or external side effect.
        self.completed[action_id] = True

    @gl.public.view
    def operation_completed(self, action_id: str) -> bool:
        return self.completed.get(action_id, False)
