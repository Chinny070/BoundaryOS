"""Resumable Studionet verification for BoundaryOS.

This tool never deploys. It saves a write intent before signing, captures the
outer transaction hash as soon as the SDK submits it, recovers the GenLayer ID
from the finalized EVM receipt if SDK polling is interrupted, and will not
resend an unresolved intent. Checkpoints contain identifiers and evidence only;
wallet keys and full signing material are never serialized.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

import requests
from genlayer_py import create_account
from genlayer_py import create_client
from genlayer_py.abi.calldata import decode, encode
from genlayer_py.abi.transactions import serialize
from genlayer_py.chains import studionet
from genlayer_py.contracts.utils import make_calldata_object
from gltest.accounts import get_default_account
from gltest.accounts import get_accounts
from gltest_cli.config.general import get_general_config
from gltest_cli.config.types import PluginConfig
from gltest_cli.config.user import load_user_config
from hexbytes import HexBytes
from web3._utils.events import event_abi_to_log_topic, get_event_data
import yaml


CHAIN_ID = 61999
RPC_URL = "https://studio.genlayer.com/api"
EXPLORER_TX_URL = "https://explorer-studio.genlayer.com/txs?search="
DEFAULT_CONTRACT = "0xe5bcECDE0F002E78fa6A9271519d42e81D643d94"
KNOWN_PROPOSAL_TX = "0x64fe023e2f90c845a5e04054eabe2b3620f08b1b8cbd1f5afb57518ce807ecda"
KNOWN_PROPOSAL_ID = "08e59188033480e0ea2e0d0cec8c1eaab43a916644ecf39770db92efe38b73ce"
INCORRECT_RECORDED_ID = "8e591880333480e0ea2e0d0cec8c1e6aab43a916644ecf39770db92efe38b73ce"
DEFAULT_CHECKPOINT = Path(".boundaryos/studionet-checkpoint.json")
PRIMARY_KEY_ENV = "BOUNDARYOS_STUDIONET_PRIVATE_KEY"
CHILD_KEY_ENV = "BOUNDARYOS_STUDIONET_CHILD_PRIVATE_KEY"
RETRY_LIMIT = 5


class VerificationError(RuntimeError):
    """Base class for categorized verification failures."""


class TransportFailure(VerificationError):
    """HTTP/connectivity error after bounded retry."""


class RpcFailure(VerificationError):
    """JSON-RPC application error, distinct from transport failure."""


class ContractExecutionFailure(VerificationError):
    """A contract call/write returned an execution error."""


class UnresolvedBroadcast(VerificationError):
    """A transaction may have been broadcast, but its ID was not persisted."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def classify_rpc_error(error: dict[str, Any]) -> str:
    """Classify an RPC error without mistaking a contract revert for transport."""
    data = error.get("data")
    receipt = data.get("receipt", {}) if isinstance(data, dict) else {}
    if (
        error.get("message") == "execution failed"
        or (isinstance(receipt, dict) and receipt.get("execution_result") == "ERROR")
    ):
        return "contract_execution"
    if error.get("code") in (-32603, -32000):
        return "rpc_or_protocol"
    return "rpc_application"


class Checkpoint:
    """Atomic, secret-free verification journal bound to one contract/signer."""

    def __init__(self, path: Path, contract: str, signer: str, source_sha256: str, bind_signer: bool = True):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = Path(".boundaryos") / f"studionet-{signer.lower()}.lock"
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise VerificationError(
                f"checkpoint lock exists at {self.lock_path}; verify its owner is stopped before removing it"
            ) from exc
        with os.fdopen(descriptor, "w", encoding="utf-8") as lock:
            lock.write(json.dumps({"pid": os.getpid(), "created_at": _now()}))
        self._owns_lock = True

        if path.exists():
            self.data = json.loads(path.read_text(encoding="utf-8"))
            bindings = [("contract_address", contract)]
            if bind_signer:
                bindings.append(("signer_address", signer))
            for key, expected in bindings:
                actual = self.data.get(key, "")
                if actual.lower() != expected.lower():
                    self.close()
                    raise VerificationError(f"checkpoint {key} does not match the requested run")
            if self.data.get("chain_id") != CHAIN_ID:
                self.close()
                raise VerificationError("checkpoint belongs to a different chain")
            self.data["current_source_sha256"] = source_sha256
            self.data["last_read_signer_address"] = signer
        else:
            self.data = {
                "schema_version": 1,
                "network": "studionet",
                "chain_id": CHAIN_ID,
                "contract_address": contract,
                "signer_address": signer,
                "current_source_sha256": source_sha256,
                "created_at": _now(),
                "transactions": {},
                "steps": {},
                "scenarios": {},
                "observations": {},
                "last_action_nonce": None,
            }
        self.save()

    def save(self) -> None:
        self.data["updated_at"] = _now()
        payload = json.dumps(self.data, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
        handle, temp_name = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as temp:
                temp.write(payload)
                temp.flush()
                os.fsync(temp.fileno())
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def close(self) -> None:
        if getattr(self, "_owns_lock", False):
            try:
                self.lock_path.unlink(missing_ok=True)
            finally:
                self._owns_lock = False


class StudionetVerifier:
    def __init__(self, contract: str, checkpoint: Checkpoint, account: Any, client: Any):
        self.contract = contract
        self.checkpoint = checkpoint
        self.account = account
        self.client = client
        self.session = requests.Session()
        self.rpc_url = str(getattr(getattr(client, "provider", None), "url", RPC_URL))
        self.request_id = 0

    def emit(self, event: str, **fields: Any) -> None:
        print(json.dumps({"event": event, **fields}, sort_keys=True), flush=True)

    def rpc(self, method: str, params: list[Any]) -> Any:
        last_error: Exception | None = None
        for attempt in range(RETRY_LIMIT):
            self.request_id += 1
            try:
                response = self.session.post(
                    self.rpc_url,
                    json={"jsonrpc": "2.0", "id": self.request_id, "method": method, "params": params},
                    timeout=(8, 25),
                )
                if response.status_code in (408, 425, 429) or response.status_code >= 500:
                    raise requests.HTTPError(f"transient HTTP {response.status_code}")
                if response.status_code >= 400:
                    raise RpcFailure(f"HTTP {response.status_code} from {method}")
                body = response.json()
                error = body.get("error")
                if error:
                    kind = classify_rpc_error(error)
                    safe = {"code": error.get("code"), "message": error.get("message"), "kind": kind}
                    if kind == "contract_execution":
                        raise ContractExecutionFailure(json.dumps(safe))
                    raise RpcFailure(json.dumps(safe))
                return body.get("result")
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                if attempt + 1 < RETRY_LIMIT:
                    time.sleep(min(0.5 * (2**attempt), 6.0))
        safe_detail = "transient HTTP response" if isinstance(last_error, requests.HTTPError) else type(last_error).__name__
        raise TransportFailure(f"{method} failed after {RETRY_LIMIT} bounded attempts: {safe_detail}")

    def read(self, method: str, args: list[Any] | None = None) -> Any:
        calldata = encode(make_calldata_object(method=method, args=args or []))
        request_data = serialize([calldata, b"\x00"])
        result = self.rpc(
            "gen_call",
            [{
                "type": "read",
                "to": self.contract,
                "from": self.account.address,
                "data": request_data,
                "transaction_hash_variant": "latest-final",
            }],
        )
        if not isinstance(result, str):
            raise RpcFailure(f"gen_call returned {type(result).__name__}, expected encoded calldata")
        try:
            return decode(bytes.fromhex(result.removeprefix("0x")))
        except Exception as exc:
            raise RpcFailure(f"gen_call result decode failed: {type(exc).__name__}: {exc}") from exc

    def tx_record(self, tx_id: str) -> dict[str, Any]:
        status = self.rpc("gen_getTransactionStatus", [tx_id])
        tx = self.rpc("eth_getTransactionByHash", [tx_id])
        if not isinstance(tx, dict):
            tx = {}
        consensus = tx.get("consensus_data") or {}
        votes = consensus.get("votes") or {}
        leader = consensus.get("leader_receipt") or [{}]
        leader = leader[0] if leader else {}
        return {
            "tx_id": tx_id,
            "status": status,
            "sender": tx.get("from_address"),
            "nonce": tx.get("nonce"),
            "raw_consensus_result": tx.get("result"),
            "validator_votes": votes,
            "execution_result": tx.get("execution_result") or leader.get("execution_result"),
            "vm_error_code": (leader.get("genvm_result") or {}).get("error_code"),
            "contract_state_hash": tx.get("contract_state_hash"),
            "observed_at": _now(),
        }

    def poll_finalized(
        self,
        tx_id: str,
        max_polls: int = 30,
        expected_execution_error: bool = False,
    ) -> dict[str, Any]:
        delay = 1.0
        for poll in range(max_polls):
            try:
                record = self.tx_record(tx_id)
                current = self.checkpoint.data["transactions"].get(tx_id, {})
                current.update(record)
                current["poll_count"] = poll + 1
                self.checkpoint.data["transactions"][tx_id] = current
                self.checkpoint.save()
                self.emit("transaction_status", **record, poll=poll + 1)
                if record["status"] == "FINALIZED":
                    if record["execution_result"] not in ("SUCCESS", "FINISHED_WITH_RETURN"):
                        current["classification"] = (
                            "expected_contract_revert" if expected_execution_error else "contract_execution_failure"
                        )
                        self.checkpoint.save()
                        if expected_execution_error and record["execution_result"] == "ERROR":
                            return current
                        raise ContractExecutionFailure(f"finalized transaction did not execute successfully: {record}")
                    current["classification"] = "finalized_execution_success"
                    self.checkpoint.save()
                    return current
                if record["status"] in ("CANCELED", "CANCELLED", "REVERTED"):
                    current["classification"] = "terminal_failure"
                    self.checkpoint.save()
                    raise ContractExecutionFailure(f"transaction reached terminal status {record['status']}")
            except TransportFailure as exc:
                self.emit("poll_transport_failure", tx_id=tx_id, detail=str(exc))
            if poll + 1 < max_polls:
                time.sleep(delay)
                delay = min(delay * 1.6, 8.0)
        raise TransportFailure(f"transaction {tx_id} did not reach FINALIZED within {max_polls} polls")

    def reconcile(self, step: str, max_polls: int = 30) -> dict[str, Any] | None:
        item = self.checkpoint.data.setdefault("steps", {}).get(step)
        if not item:
            return None
        tx_id = item.get("tx_id")
        if not tx_id and item.get("outer_tx_hash"):
            tx_id = self._recover_genlayer_tx_id(step, item, max_polls=max_polls)
        if tx_id:
            self.emit("reconcile_existing_tx", step=step, tx_id=tx_id)
            return self.poll_finalized(
                tx_id,
                max_polls=max_polls,
                expected_execution_error=bool(item.get("expected_execution_error")),
            )
        if item.get("phase") in ("intent_saved", "broadcast_unknown"):
            signer = item.get("signer_address", self.account.address)
            latest = int(self.rpc("eth_getTransactionCount", [signer, "latest"]), 16)
            pending = int(self.rpc("eth_getTransactionCount", [signer, "pending"]), 16)
            item.update({"phase": "broadcast_unknown", "latest_nonce": latest, "pending_nonce": pending, "reconciled_at": _now()})
            self.checkpoint.save()
            raise UnresolvedBroadcast(
                f"step {step} has an intent but no persisted transaction id; nonce evidence latest={latest}, pending={pending}; refusing to resend"
            )
        return None

    def _recover_genlayer_tx_id(self, step: str, item: dict[str, Any], max_polls: int) -> str:
        """Recover the consensus transaction ID from its persisted EVM broadcast."""
        outer_hash = item["outer_tx_hash"]
        delay = 1.0
        receipt = None
        for poll in range(max_polls):
            try:
                receipt = self.rpc("eth_getTransactionReceipt", [outer_hash])
                if receipt:
                    break
            except TransportFailure as exc:
                self.emit("outer_receipt_transport_failure", step=step, outer_tx_hash=outer_hash, detail=str(exc))
            if poll + 1 < max_polls:
                time.sleep(delay)
                delay = min(delay * 1.6, 8.0)
        if not isinstance(receipt, dict):
            raise TransportFailure(f"outer transaction {outer_hash} has no retrievable receipt after {max_polls} polls")
        receipt_status = receipt.get("status", "0x0")
        if isinstance(receipt_status, str):
            receipt_status = int(receipt_status, 16)
        if receipt_status != 1:
            item.update({"phase": "outer_reverted", "outer_receipt_status": receipt.get("status"), "reconciled_at": _now()})
            self.checkpoint.save()
            raise ContractExecutionFailure(f"outer transaction {outer_hash} reverted before consensus submission")

        abi = self.client.chain.consensus_main_contract["abi"]
        event_abi = next((entry for entry in abi if entry.get("type") == "event" and entry.get("name") == "NewTransaction"), None)
        if event_abi is None:
            raise RpcFailure("configured SDK consensus ABI has no NewTransaction event")
        tx_id = None
        topic = event_abi_to_log_topic(event_abi)
        for raw_log in receipt.get("logs", []):
            if not raw_log.get("topics") or HexBytes(raw_log["topics"][0]) != topic:
                continue
            log = dict(raw_log)
            log["topics"] = [HexBytes(value) for value in raw_log["topics"]]
            log["data"] = HexBytes(raw_log["data"])
            for key in ("blockNumber", "transactionIndex", "logIndex"):
                if isinstance(log.get(key), str):
                    log[key] = int(log[key], 16)
            for key in ("blockHash", "transactionHash"):
                if isinstance(log.get(key), str):
                    log[key] = HexBytes(log[key])
            decoded_event = get_event_data(self.client.codec, event_abi, log)
            tx_id = self.client.to_hex(decoded_event["args"]["txId"])
            break
        if not tx_id:
            raise RpcFailure(f"successful outer receipt {outer_hash} had no NewTransaction event")
        item.update({
            "phase": "broadcast_recovered",
            "tx_id": tx_id,
            "outer_receipt_status": receipt.get("status"),
            "outer_block_number": receipt.get("blockNumber"),
            "recovered_at": _now(),
        })
        self.checkpoint.save()
        self.emit("transaction_id_recovered_from_outer_receipt", step=step, outer_tx_hash=outer_hash, tx_id=tx_id)
        return tx_id

    def write_once(
        self,
        step: str,
        method: str,
        args: list[Any],
        rotations: int = 3,
        max_polls: int = 30,
        signer: Any | None = None,
        expected_execution_error: bool = False,
    ) -> dict[str, Any]:
        signer = signer or self.account
        existing = self.reconcile(step, max_polls=max_polls)
        if existing:
            return existing
        latest = int(self.rpc("eth_getTransactionCount", [signer.address, "latest"]), 16)
        pending = int(self.rpc("eth_getTransactionCount", [signer.address, "pending"]), 16)
        if latest != pending:
            raise UnresolvedBroadcast(f"signer has pending transactions (latest={latest}, pending={pending}); refusing a new write")
        intent = {
            "phase": "intent_saved",
            "method": method,
            "signer_address": signer.address,
            "reserved_nonce": pending,
            "args_sha256": hashlib.sha256(_canonical(args)).hexdigest(),
            "expected_execution_error": expected_execution_error,
            "created_at": _now(),
        }
        self.checkpoint.data.setdefault("steps", {})[step] = intent
        self.checkpoint.save()
        self.emit("write_intent_saved", step=step, method=method, reserved_nonce=pending)
        provider = self.client.provider
        original_make_request = provider.make_request

        def record_outer_hash(rpc_method: str, rpc_params: list[Any]) -> Any:
            response = original_make_request(rpc_method, rpc_params)
            if rpc_method == "eth_sendRawTransaction" and isinstance(response, dict) and response.get("result"):
                intent.update({"phase": "outer_broadcast", "outer_tx_hash": response["result"], "outer_broadcast_at": _now()})
                self.checkpoint.save()
                self.emit("outer_transaction_broadcast", step=step, method=method, outer_tx_hash=response["result"], reserved_nonce=pending)
            return response

        try:
            provider.make_request = record_outer_hash
            try:
                tx_id = self.client.write_contract(
                    address=self.contract,
                    function_name=method,
                    account=signer,
                    consensus_max_rotations=rotations,
                    args=args,
                )
            finally:
                provider.make_request = original_make_request
        except Exception as exc:
            intent.update({
                "phase": "outer_broadcast" if intent.get("outer_tx_hash") else "broadcast_unknown",
                "error_class": type(exc).__name__,
                "error_classification": "sdk_or_transport_failure",
                "updated_at": _now(),
            })
            try:
                intent["latest_nonce"] = int(self.rpc("eth_getTransactionCount", [signer.address, "latest"]), 16)
                intent["pending_nonce"] = int(self.rpc("eth_getTransactionCount", [signer.address, "pending"]), 16)
            except Exception as reconcile_exc:
                intent["nonce_reconciliation_error_class"] = type(reconcile_exc).__name__
            self.checkpoint.save()
            raise UnresolvedBroadcast(
                f"SDK write raised {type(exc).__name__}; checkpoint retained with any captured outer hash and automatic resend disabled"
            ) from exc
        tx_id = str(tx_id)
        intent.update({"phase": "broadcast", "tx_id": tx_id, "broadcast_at": _now()})
        self.checkpoint.save()
        self.emit("transaction_broadcast", step=step, method=method, tx_id=tx_id, reserved_nonce=pending)
        try:
            tx_meta = self.rpc("eth_getTransactionByHash", [tx_id])
        except Exception as exc:
            intent["metadata_reconciliation_error"] = f"{type(exc).__name__}: {str(exc)[:250]}"
            self.checkpoint.save()
            tx_meta = None
        if isinstance(tx_meta, dict):
            tx_nonce = tx_meta.get("nonce")
            if isinstance(tx_nonce, str):
                tx_nonce = int(tx_nonce, 16)
            intent["observed_nonce"] = tx_nonce
            if tx_nonce is not None and tx_nonce != pending:
                intent["phase"] = "nonce_conflict"
                self.checkpoint.save()
                raise UnresolvedBroadcast(f"transaction nonce {tx_nonce} differed from reserved nonce {pending}; refusing to continue")
        self.checkpoint.save()
        return self.poll_finalized(tx_id, max_polls=max_polls, expected_execution_error=expected_execution_error)


def _as_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return value
    return value


def initialize_runtime(require_stable_signers: bool = False) -> tuple[Any, Any, str, list[Any], bool, bool]:
    """Load the configured Studionet signer without printing key material."""
    config_path = Path("gltest.config.yaml")
    general = get_general_config()
    general.user_config = load_user_config(str(config_path))
    network = general.user_config.networks.get("studionet")
    if network is None:
        raise VerificationError("gltest.config.yaml has no studionet network")
    plugin = PluginConfig()
    plugin.network_name = "studionet"
    plugin.rpc_url = network.url or RPC_URL
    general.plugin_config = plugin
    raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    raw_network = (raw_config.get("networks") or {}).get("studionet") or {}
    explicit_accounts = raw_network.get("accounts")
    configured_primary = bool(os.environ.get(PRIMARY_KEY_ENV)) or bool(raw_network.get("from")) or bool(explicit_accounts)
    if os.environ.get(PRIMARY_KEY_ENV):
        account = create_account(os.environ[PRIMARY_KEY_ENV])
    else:
        account = get_default_account()
    client = create_client(chain=studionet, endpoint=plugin.rpc_url, account=account)
    accounts = get_accounts()
    stable_accounts = explicit_accounts is not None
    if os.environ.get(CHILD_KEY_ENV):
        accounts.append(create_account(os.environ[CHILD_KEY_ENV]))
        stable_accounts = True
    stable_primary = configured_primary
    stable_child = stable_accounts and any(a.address.lower() != account.address.lower() for a in accounts)
    if require_stable_signers and (not stable_primary or not stable_child):
        missing = []
        if not stable_primary:
            missing.append(f"configure {PRIMARY_KEY_ENV} locally or set networks.studionet.from in gltest.config.yaml")
        if not stable_child:
            missing.append(f"configure a second stable signer in networks.studionet.accounts or {CHILD_KEY_ENV}")
        raise VerificationError("live resumable writes require stable local signers; " + "; ".join(missing))
    return account, client, plugin.rpc_url, accounts, stable_primary, stable_child


def inspect_existing(verifier: StudionetVerifier) -> dict[str, Any]:
    tx = verifier.tx_record(KNOWN_PROPOSAL_TX)
    action = _as_json(verifier.read("get_action", [KNOWN_PROPOSAL_ID]))
    receipt = _as_json(verifier.read("get_receipt", [KNOWN_PROPOSAL_ID]))
    if not isinstance(action, dict):
        raise VerificationError("known 64-character action ID did not return an action record")
    now = int(datetime.now(timezone.utc).timestamp())
    observed = {
        "known_transaction": tx,
        "known_action_id": KNOWN_PROPOSAL_ID,
        "incorrectly_recorded_action_id": INCORRECT_RECORDED_ID,
        "incorrect_recorded_id_length": len(INCORRECT_RECORDED_ID),
        "action_state": action.get("state"),
        "action_nonce": action.get("nonce"),
        "submitted_at": action.get("submitted_at"),
        "proposal_expires_at": action.get("proposal_expires_at"),
        "expired_at_observation": now >= int(action.get("proposal_expires_at", 0)),
        "receipt_present": bool(receipt),
        "observed_at": _now(),
    }
    verifier.checkpoint.data["observations"]["existing_disposable_proposal"] = observed
    verifier.checkpoint.data["last_action_nonce"] = max(
        int(verifier.checkpoint.data.get("last_action_nonce") or 0), int(action.get("nonce") or 0)
    )
    verifier.checkpoint.save()
    verifier.emit("existing_instance_inspected", **observed)
    return action


def action_digest(action: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(action)).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", default=DEFAULT_CONTRACT)
    parser.add_argument("--rpc-url", default=None, help="RPC endpoint from official compatible tooling; defaults to configured Studionet RPC")
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--inspect-existing", action="store_true", help="read-only inspect the known finalized proposal")
    parser.add_argument("--run-live-suite", action="store_true", help="explicitly permit live writes; never deploys")
    parser.add_argument("--resume-step", help="reconcile a previously checkpointed write step without sending any new transaction")
    parser.add_argument("--max-polls", type=int, default=30)
    options = parser.parse_args(argv)
    if options.resume_step and options.run_live_suite:
        raise VerificationError("--resume-step is read/reconcile-only and cannot be combined with --run-live-suite")

    account, client, rpc_url, accounts, stable_primary, stable_child = initialize_runtime(
        require_stable_signers=options.run_live_suite
    )
    rpc_url = options.rpc_url or rpc_url
    if urlparse(rpc_url).scheme != "https" or not urlparse(rpc_url).netloc:
        raise VerificationError("RPC URL must be a valid HTTPS endpoint")
    verifier = None
    checkpoint = Checkpoint(
        options.checkpoint,
        options.contract,
        account.address,
        hashlib.sha256(Path("contracts/boundary_os.py").read_bytes()).hexdigest(),
        bind_signer=stable_primary,
    )
    try:
        verifier = StudionetVerifier(options.contract, checkpoint, account, client)
        verifier.rpc_url = rpc_url
        actual_chain = int(verifier.rpc("eth_chainId", []), 16)
        if actual_chain != CHAIN_ID:
            raise VerificationError(f"RPC returned chain ID {actual_chain}, expected {CHAIN_ID}")
        verifier.checkpoint.data["chain_id_observed"] = actual_chain
        verifier.checkpoint.data["signer_nonce_latest"] = int(verifier.rpc("eth_getTransactionCount", [account.address, "latest"]), 16)
        verifier.checkpoint.data["signer_nonce_pending"] = int(verifier.rpc("eth_getTransactionCount", [account.address, "pending"]), 16)
        verifier.checkpoint.save()
        verifier.emit("preflight", chain_id=actual_chain, contract=options.contract, signer=account.address, live_writes_enabled=options.run_live_suite)
        if options.resume_step:
            result = verifier.reconcile(options.resume_step, max_polls=options.max_polls)
            if result is None:
                raise VerificationError(f"no checkpointed write intent for step {options.resume_step}")
            verifier.emit("resume_step_complete", step=options.resume_step, tx_id=result.get("tx_id"), status=result.get("status"), classification=result.get("classification"))
        elif options.inspect_existing or options.contract.lower() == DEFAULT_CONTRACT.lower():
            inspect_existing(verifier)
        elif not options.run_live_suite:
            raise VerificationError("no inspection target selected; pass the disposable contract address")
        if options.run_live_suite:
            run_live_suite(verifier, account, accounts, max_polls=options.max_polls)
        return 0
    finally:
        checkpoint.close()


def run_live_suite(
    verifier: StudionetVerifier,
    account: Any,
    accounts: list[Any],
    max_polls: int = 30,
) -> None:
    """Run resumable diagnostic flows on the specified instance; never deploys."""
    signer_address = account.address
    agent = _as_json(verifier.read("get_agent", [signer_address]))
    if not isinstance(agent, dict):
        raise VerificationError("get_agent returned malformed state")
    if not agent.get("registered"):
        verifier.write_once(
            "setup.register_agent",
            "register_agent",
            [signer_address],
            max_polls=max_polls,
        )
        agent = _as_json(verifier.read("get_agent", [signer_address]))
        if not agent.get("registered"):
            raise VerificationError("agent registration transaction finalized but finalized state is absent")

    policy_id = verifier.checkpoint.data.get("diagnostic_policy_id")
    assigned_policy = agent.get("policy_id")
    if assigned_policy:
        if policy_id and assigned_policy != policy_id:
            raise VerificationError(
                f"configured signer is already assigned to policy {assigned_policy}; checkpoint expects {policy_id}"
            )
        policy_id = assigned_policy
    if not policy_id:
        policy_id = "resume-" + hashlib.sha256(
            f"{verifier.contract.lower()}|{signer_address.lower()}".encode()
        ).hexdigest()[:12]
        verifier.checkpoint.data["diagnostic_policy_id"] = policy_id
        verifier.checkpoint.save()

    policy_record = _as_json(verifier.read("get_policy", [policy_id, 1]))
    policy = {
        "action_types": ["purchase"],
        "hard_denies": ["cash_withdrawal"],
        "max_amount": 500,
        "aggregate_cap": 1000,
        "unit": "USD_CENTS",
        "window_seconds": 2_592_000,
        "valid_from": 0,
        "valid_until": 4_000_000_000,
        "purpose": "buy plain A4 printer paper and ink toner for company office use",
        "evidence_required": True,
        "evidence_mode": "CLAIM_ONLY",
    }
    policy_json = json.dumps(policy, sort_keys=True, separators=(",", ":"))
    if not policy_record:
        if assigned_policy:
            raise VerificationError(f"assigned policy {assigned_policy} could not be read")
        verifier.write_once(
            "setup.create_policy",
            "create_policy",
            [policy_id, signer_address, policy_json],
            max_polls=max_polls,
        )
        policy_record = _as_json(verifier.read("get_policy", [policy_id, 1]))
        if not isinstance(policy_record, dict):
            raise VerificationError("policy creation finalized but finalized policy state is absent")
    else:
        # Do not repurpose a pre-existing account policy with unknown terms.
        if policy_id != verifier.checkpoint.data.get("diagnostic_policy_id"):
            raise VerificationError("signer policy exists without this checkpoint; use a fresh configured signer")
        expected = hashlib.sha256(_canonical(policy)).hexdigest()
        actual = hashlib.sha256(_canonical(policy_record)).hexdigest()
        if expected != actual:
            raise VerificationError("checkpoint policy definition differs from finalized on-chain policy")

    verifier.write_once(
        "setup.authorize_consumer",
        "authorize_consumer",
        [policy_id, signer_address],
        max_polls=max_polls,
    )

    def propose_and_evaluate(
        label: str,
        amount: int,
        purpose: str,
        action_type: str = "purchase",
        expected_decision: str = "ALLOW",
        expected_fit: str = "MATCH",
        consume: bool = False,
        frozen: bool = False,
    ) -> tuple[str, dict[str, Any]]:
        scenarios = verifier.checkpoint.data.setdefault("scenarios", {})
        action = {
            "action_type": action_type,
            "amount": amount,
            "unit": "USD_CENTS",
            "purpose": purpose,
            "evidence_claim": f"Caller asserts test evidence for {label}",
        }
        action_json = json.dumps(action, sort_keys=True, separators=(",", ":"))
        action_hash = hashlib.sha256(action_json.encode()).hexdigest()
        record = scenarios.get(label)
        if record and record.get("action_json_sha256") != action_hash:
            raise VerificationError(f"scenario {label} arguments changed since checkpoint creation")

        if not record:
            nonce = int(verifier.checkpoint.data.get("last_action_nonce") or 0) + 1
            aid = verifier.read("preview_action_id", [policy_id, signer_address, nonce, action_json])
            if not isinstance(aid, str) or len(aid) != 64:
                raise VerificationError("preview_action_id did not return a 64-character digest")
            record = {
                "nonce": nonce,
                "action_id": aid,
                "action_json_sha256": action_hash,
                "expected_decision": expected_decision,
                "expected_semantic_fit": expected_fit,
                "created_at": _now(),
            }
            scenarios[label] = record
            verifier.checkpoint.save()

        aid = record["action_id"]
        action_state = _as_json(verifier.read("get_action", [aid]))
        receipt_value = _as_json(verifier.read("get_receipt", [aid]))
        if not action_state:
            verifier.write_once(
                f"{label}.submit",
                "submit_action",
                [policy_id, int(record["nonce"]), action_json],
                max_polls=max_polls,
            )
            action_state = _as_json(verifier.read("get_action", [aid]))
            if not isinstance(action_state, dict):
                raise VerificationError(f"{label}: finalized submit did not produce action state")
            verifier.checkpoint.data["last_action_nonce"] = max(
                int(verifier.checkpoint.data.get("last_action_nonce") or 0), int(record["nonce"])
            )
            verifier.checkpoint.save()
        elif action_state.get("nonce") != record["nonce"]:
            raise VerificationError(f"{label}: action ID read back with a different nonce")

        if receipt_value:
            decision = receipt_value
        else:
            if action_state.get("state") != "PENDING":
                raise VerificationError(f"{label}: action is {action_state.get('state')} but has no receipt")
            expired_at = int(action_state.get("proposal_expires_at", 0))
            if int(time.time()) >= expired_at:
                # The expired proposal is never evaluated. Advance the agent nonce and
                # bind a new stable scenario attempt to the next nonce.
                record["expired_action_id"] = aid
                record["expired_at"] = expired_at
                record["nonce"] = int(verifier.checkpoint.data.get("last_action_nonce") or record["nonce"]) + 1
                record["action_id"] = verifier.read(
                    "preview_action_id", [policy_id, signer_address, record["nonce"], action_json]
                )
                record["created_at"] = _now()
                verifier.checkpoint.save()
                aid = record["action_id"]
                if _as_json(verifier.read("get_action", [aid])):
                    raise VerificationError(f"{label}: fresh nonce already has an on-chain action; refusing reuse")
                verifier.write_once(
                    f"{label}.submit.nonce-{record['nonce']}",
                    "submit_action",
                    [policy_id, int(record["nonce"]), action_json],
                    max_polls=max_polls,
                )
                action_state = _as_json(verifier.read("get_action", [aid]))
                if not isinstance(action_state, dict):
                    raise VerificationError(f"{label}: fresh proposal was not readable after finality")
                verifier.checkpoint.data["last_action_nonce"] = int(record["nonce"])
                verifier.checkpoint.save()
            if frozen:
                agent_state = _as_json(verifier.read("get_agent", [signer_address]))
                if not agent_state.get("frozen"):
                    verifier.write_once(
                        f"{label}.freeze",
                        "freeze_agent",
                        [signer_address, True],
                        max_polls=max_polls,
                    )
            verifier.write_once(
                f"{label}.evaluate",
                "evaluate_action",
                [aid],
                rotations=5,
                max_polls=max_polls,
            )
            receipt_value = _as_json(verifier.read("get_receipt", [aid]))
            if not isinstance(receipt_value, dict):
                raise VerificationError(f"{label}: finalized evaluation did not produce a receipt")

        if receipt_value.get("decision") != expected_decision:
            raise VerificationError(
                f"{label}: expected {expected_decision}, observed {receipt_value.get('decision')}"
            )
        if receipt_value.get("semantic_fit") != expected_fit:
            raise VerificationError(
                f"{label}: expected semantic fit {expected_fit}, observed {receipt_value.get('semantic_fit')}"
            )
        result = {
            "action_id": aid,
            "nonce": record["nonce"],
            "action_state": action_state.get("state") if isinstance(action_state, dict) else "EVALUATED",
            "decision": receipt_value.get("decision"),
            "semantic_fit": receipt_value.get("semantic_fit"),
            "evidence_provenance": receipt_value.get("evidence_provenance"),
            "receipt_digest": receipt_value.get("receipt_digest"),
            "receipt_digest_valid": receipt_value.get("receipt_digest") == hashlib.sha256(
                _canonical({k: v for k, v in receipt_value.items() if k != "receipt_digest"})
            ).hexdigest(),
            "observed_at": _now(),
        }
        record["result"] = result
        verifier.checkpoint.save()
        verifier.emit("scenario_result", scenario=label, **result)

        if consume:
            if receipt_value.get("decision") != "ALLOW":
                raise VerificationError(f"{label}: only ALLOW receipts can be consumed")
            fresh = verifier.read("can_consume_authorization", [aid, signer_address])
            if fresh is True:
                verifier.write_once(
                    f"{label}.consume",
                    "consume_authorization",
                    [aid, receipt_value["action_digest"]],
                    max_polls=max_polls,
                )
            consumed = _as_json(verifier.read("get_receipt", [aid]))
            if not isinstance(consumed, dict) or consumed.get("consumed") is not True:
                raise VerificationError(f"{label}: finalized consumption not reflected in receipt state")
            replay_step = f"{label}.replay"
            verifier.write_once(
                replay_step,
                "consume_authorization",
                [aid, receipt_value["action_digest"]],
                max_polls=max_polls,
                expected_execution_error=True,
            )
            result["consumed"] = True
            result["consumed_by"] = consumed.get("consumed_by")
            result["legacy_receipt_digest_valid_after_consumption"] = consumed.get("receipt_digest") == hashlib.sha256(
                _canonical({k: v for k, v in consumed.items() if k != "receipt_digest"})
            ).hexdigest()
            verifier.checkpoint.save()
        if frozen:
            state = _as_json(verifier.read("get_agent", [signer_address]))
            if state.get("frozen"):
                verifier.write_once(
                    f"{label}.unfreeze",
                    "freeze_agent",
                    [signer_address, False],
                    max_polls=max_polls,
                )
        return aid, result

    # An existing signer policy may have been created by a previous invocation;
    # its terms must be byte-equivalent to the checkpoint's intended fixture.
    if not verifier.checkpoint.data.get("diagnostic_policy_id"):
        verifier.checkpoint.data["diagnostic_policy_id"] = policy_id
        verifier.checkpoint.save()

    match_id, _ = propose_and_evaluate(
        "semantic_match", 250, policy["purpose"], consume=True
    )
    propose_and_evaluate(
        "semantic_mismatch",
        100,
        "buy a high-end gaming laptop for personal entertainment",
        expected_decision="DENY_PURPOSE",
        expected_fit="MISMATCH",
    )
    propose_and_evaluate(
        "deterministic_hard_deny",
        1,
        "withdraw cash for unrelated personal spending",
        action_type="cash_withdrawal",
        expected_decision="DENY_HARD_RULE",
        expected_fit="NOT_EVALUATED",
    )

    # Four 250-cent matching actions reach the policy cap exactly; the next
    # one-cent action must be rejected before semantic evaluation.
    quota_fourth_id = ""
    for label in ("quota_match_2", "quota_match_3", "quota_match_4"):
        quota_fourth_id, _ = propose_and_evaluate(label, 250, policy["purpose"])
    propose_and_evaluate(
        "aggregate_quota_denial",
        1,
        policy["purpose"],
        expected_decision="DENY_AGGREGATE_CAP",
        expected_fit="NOT_EVALUATED",
    )

    propose_and_evaluate(
        "agent_freeze",
        250,
        policy["purpose"],
        expected_decision="DENY_FROZEN",
        expected_fit="NOT_EVALUATED",
        frozen=True,
    )

    _verify_delegation_boundary(verifier, policy_id, account, accounts, policy, max_polls)

    # Start a fresh policy version to obtain a recent ALLOW receipt, then update
    # again so staleness, rather than the five-minute expiry, explains rejection.
    verifier.write_once(
        "policy.update_to_version_2",
        "update_policy",
        [policy_id, policy_json],
        max_polls=max_polls,
    )
    version_two = _as_json(verifier.read("get_policy", [policy_id, 2]))
    if not isinstance(version_two, dict):
        raise VerificationError("policy version two was not readable after finalized update")
    stale_action_id, _ = propose_and_evaluate(
        "stale_receipt_source",
        1,
        policy["purpose"],
        expected_decision="ALLOW",
        expected_fit="MATCH",
    )
    if verifier.read("can_consume_authorization", [stale_action_id, signer_address]) is not True:
        raise VerificationError("fresh version-two ALLOW receipt was not consumable before policy update")
    verifier.write_once(
        "policy.update_to_version_3",
        "update_policy",
        [policy_id, policy_json],
        max_polls=max_polls,
    )
    stale_consumable = verifier.read("can_consume_authorization", [stale_action_id, signer_address])
    if stale_consumable is not False:
        raise VerificationError("version-two receipt remained consumable after policy update")

    revoked_action_id = _prepare_action_only(
        verifier, policy_id, signer_address, "post_revoke_action", 1, policy["purpose"], max_polls
    )
    verifier.write_once("policy.revoke", "revoke_policy", [policy_id], max_polls=max_polls)
    verifier.write_once(
        "post_revoke_action.evaluate",
        "evaluate_action",
        [revoked_action_id],
        rotations=3,
        max_polls=max_polls,
    )
    revoked_receipt = _as_json(verifier.read("get_receipt", [revoked_action_id]))
    if not isinstance(revoked_receipt, dict) or revoked_receipt.get("decision") != "DENY_STALE_POLICY":
        raise VerificationError("revoked policy did not deny the pending proposal as stale")
    verifier.checkpoint.data["observations"]["live_suite_complete"] = {
        "status": "completed",
        "match_action_id": match_id,
        "aggregate_quota_source_action_id": quota_fourth_id,
        "revoked_action_id": revoked_action_id,
        "completed_at": _now(),
    }
    verifier.checkpoint.save()
    verifier.emit("live_suite_complete", status="completed", contract=verifier.contract)


def _prepare_action_only(
    verifier: StudionetVerifier,
    policy_id: str,
    signer_address: str,
    label: str,
    amount: int,
    purpose: str,
    max_polls: int = 30,
) -> str:
    """Create or recover a pending action without evaluating it."""
    scenarios = verifier.checkpoint.data.setdefault("scenarios", {})
    action = {
        "action_type": "purchase",
        "amount": amount,
        "unit": "USD_CENTS",
        "purpose": purpose,
        "evidence_claim": f"Caller asserts test evidence for {label}",
    }
    action_json = json.dumps(action, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(action_json.encode()).hexdigest()
    record = scenarios.get(label)
    if record and record.get("action_json_sha256") != digest:
        raise VerificationError(f"scenario {label} arguments changed since checkpoint creation")
    if not record:
        nonce = int(verifier.checkpoint.data.get("last_action_nonce") or 0) + 1
        action_id = verifier.read("preview_action_id", [policy_id, signer_address, nonce, action_json])
        record = {"nonce": nonce, "action_id": action_id, "action_json_sha256": digest, "created_at": _now()}
        scenarios[label] = record
        verifier.checkpoint.save()
    action_id = record["action_id"]
    action_state = _as_json(verifier.read("get_action", [action_id]))
    if not action_state:
        verifier.write_once(
            f"{label}.submit",
            "submit_action",
            [policy_id, int(record["nonce"]), action_json],
            max_polls=max_polls,
        )
        action_state = _as_json(verifier.read("get_action", [action_id]))
    if not isinstance(action_state, dict) or action_state.get("state") != "PENDING":
        raise VerificationError(f"scenario {label} has no pending proposal")
    verifier.checkpoint.data["last_action_nonce"] = max(
        int(verifier.checkpoint.data.get("last_action_nonce") or 0), int(record["nonce"])
    )
    verifier.checkpoint.save()
    return action_id


def _verify_delegation_boundary(
    verifier: StudionetVerifier,
    policy_id: str,
    parent: Any,
    accounts: list[Any],
    policy: dict[str, Any],
    max_polls: int,
) -> None:
    """Register a configured child signer and prove amount-scope widening reverts."""
    child = None
    for candidate in accounts:
        if candidate.address.lower() == parent.address.lower():
            continue
        state = _as_json(verifier.read("get_agent", [candidate.address]))
        if isinstance(state, dict) and not state.get("registered"):
            child = candidate
            break
    if child is None:
        raise VerificationError("no configured, unregistered secondary signer is available for delegation testing")
    child_state = _as_json(verifier.read("get_agent", [child.address]))
    if not child_state.get("registered"):
        verifier.write_once(
            "delegation.register_child",
            "register_agent",
            [parent.address],
            signer=child,
            max_polls=max_polls,
        )
    now = int(time.time())
    expires_at = now + 300
    widened_scope = {
        "action_types": ["purchase"],
        "max_amount": int(policy["max_amount"]) + 1,
        "valid_from": 0,
        "valid_until": expires_at,
        "purpose": policy["purpose"],
    }
    scope_json = json.dumps(widened_scope, sort_keys=True, separators=(",", ":"))
    verifier.write_once(
        "delegation.reject_amount_widening",
        "delegate_authority",
        [policy_id, parent.address, child.address, scope_json, expires_at],
        max_polls=max_polls,
        expected_execution_error=True,
    )
    child_after = _as_json(verifier.read("get_agent", [child.address]))
    if child_after.get("policy_id"):
        raise VerificationError("rejected amount-widening delegation unexpectedly assigned a child policy")
    verifier.checkpoint.data["observations"]["delegation_boundary"] = {
        "child_address": child.address,
        "requested_amount": widened_scope["max_amount"],
        "parent_limit": policy["max_amount"],
        "execution_rejected": True,
        "observed_at": _now(),
    }
    verifier.checkpoint.save()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except VerificationError as exc:
        print(json.dumps({"event": "verification_blocked", "classification": type(exc).__name__, "detail": str(exc)}), file=sys.stderr, flush=True)
        raise SystemExit(2)
