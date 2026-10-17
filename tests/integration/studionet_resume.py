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
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

import requests
from genlayer_py import create_account
from genlayer_py import create_client
from genlayer_py.chains import studionet
from genlayer_py.types import TransactionHashVariant
from gltest.accounts import get_default_account
from gltest.accounts import get_accounts
from gltest_cli.config.general import get_general_config
from gltest_cli.config.types import PluginConfig
from gltest_cli.config.user import load_user_config
from hexbytes import HexBytes
from web3._utils.events import event_abi_to_log_topic, get_event_data
import yaml
from eth_utils import to_checksum_address


CHAIN_ID = 61999
RPC_URL = "https://studio.genlayer.com/api"
REQUIRED_GENLAYER_CLI_VERSION = "0.39.1"
EXPLORER_TX_URL = "https://explorer-studio.genlayer.com/txs?search="
DEFAULT_CONTRACT = "0xe5bcECDE0F002E78fa6A9271519d42e81D643d94"
KNOWN_PROPOSAL_TX = "0x64fe023e2f90c845a5e04054eabe2b3620f08b1b8cbd1f5afb57518ce807ecda"
KNOWN_PROPOSAL_ID = "08e59188033480e0ea2e0d0cec8c1eaab43a916644ecf39770db92efe38b73ce"
INCORRECT_RECORDED_ID = "8e591880333480e0ea2e0d0cec8c1e6aab43a916644ecf39770db92efe38b73ce"
DEFAULT_CHECKPOINT = Path(".boundaryos/studionet-checkpoint.json")
DEFAULT_DEPLOYMENT_CHECKPOINT = Path(".boundaryos/studionet-deployment-checkpoint.json")
DEPLOYMENT_CHECKPOINT_BINDING = "deployment-pending"
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


class ConsensusFailure(VerificationError):
    """A transaction finalized without a successful consensus decision."""


class UnresolvedBroadcast(VerificationError):
    """A transaction may have been broadcast, but its ID was not persisted."""


@dataclass(frozen=True)
class CliAccount:
    """Public identity for an account whose signing stays inside GenLayer CLI."""

    name: str
    address: str
    unlocked: bool = True


def _resolve_cli_entry() -> Path:
    """Resolve the one supported CLI package and reject incompatible entries."""
    configured_entry = os.environ.get("BOUNDARYOS_GENLAYER_CLI_ENTRY")
    cli_shim = shutil.which("genlayer") if not configured_entry else None
    if configured_entry:
        entry = Path(configured_entry).resolve()
    elif cli_shim:
        entry = (Path(cli_shim).parent / "node_modules" / "genlayer" / "dist" / "index.js").resolve()
    else:
        raise VerificationError("GenLayer CLI executable must be available on PATH")
    if not entry.is_file():
        raise VerificationError("could not locate the GenLayer CLI entry point invoked by the harness")
    package = next((parent / "package.json" for parent in entry.parents if (parent / "package.json").is_file()), None)
    if package is None:
        raise VerificationError("could not identify the GenLayer CLI package version")
    try:
        metadata = json.loads(package.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError("could not read GenLayer CLI package metadata") from exc
    if metadata.get("name") != "genlayer" or metadata.get("version") != REQUIRED_GENLAYER_CLI_VERSION:
        raise VerificationError(
            f"harness requires genlayer@{REQUIRED_GENLAYER_CLI_VERSION}; resolved package is "
            f"{metadata.get('name')}@{metadata.get('version')} at {entry}"
        )
    return entry


def _genlayer_command(*args: str) -> list[str]:
    """Build a direct Node invocation of the pinned CLI (never a shell command)."""
    node = shutil.which("node")
    if not node:
        raise VerificationError("Node.js must be available on PATH")
    entry = _resolve_cli_entry()
    return [node, str(entry), *args]


def verify_legacy_cli_encoding() -> dict[str, str]:
    """Check the pinned CLI bundle uses the legacy addTransaction ABI."""
    entry = _resolve_cli_entry()
    source = entry.read_text(encoding="utf-8", errors="replace")
    legacy_abi = "ADD_TRANSACTION_ABI_V5"
    if legacy_abi not in source or "type: \"function\"" not in source or "ADD_TRANSACTION_ABI_WITH_FEES" in source:
        raise VerificationError("resolved GenLayer CLI does not expose the expected legacy transaction encoder")
    try:
        studio_start = source.index("var studionet = defineChain(")
        studio_end = source.index("var VALIDATOR_WALLET_ABI", studio_start)
        studio_definition = source[studio_start:studio_end]
        abi_start = source.index("var CONSENSUS_MAIN_CONTRACT2 =")
        abi_end = source.index("var CONSENSUS_DATA_CONTRACT2", abi_start)
        consensus_abi = source[abi_start:abi_end]
        function_position = consensus_abi.index('name: "addTransaction"')
        inputs_position = consensus_abi.rfind("inputs:", 0, function_position)
        inputs_open = consensus_abi.index("[", inputs_position, function_position)
        inputs_close = consensus_abi.index("]", inputs_open, function_position)
        if "consensusMainContract: CONSENSUS_MAIN_CONTRACT2" not in studio_definition or inputs_position < 0:
            raise ValueError("Studionet ABI binding is not identifiable")
        input_count = len(re.findall(r"\btype:\s*\"", consensus_abi[inputs_open:inputs_close]))
    except (ValueError, IndexError) as exc:
        raise VerificationError("could not inspect the CLI's Studionet transaction ABI") from exc
    if input_count != 5:
        raise VerificationError(f"CLI Studionet addTransaction has {input_count} inputs; expected legacy five-input ABI")
    return {
        "version": REQUIRED_GENLAYER_CLI_VERSION,
        "entry": str(entry),
        "transaction_abi": legacy_abi,
        "transaction_selector": "0x27241a99",
        "studionet_add_transaction_inputs": str(input_count),
    }


def verify_cli_network(rpc_url: str) -> dict[str, str]:
    """Require the configured executable to report the specified Studionet."""
    if rpc_url != RPC_URL:
        raise VerificationError(f"only Studionet RPC {RPC_URL} is supported")
    version = _cli_run("--version").stdout.strip()
    if REQUIRED_GENLAYER_CLI_VERSION not in version:
        raise VerificationError(f"CLI --version returned {version!r}; expected {REQUIRED_GENLAYER_CLI_VERSION}")
    network = _cli_run("network", "info").stdout
    normalized = network.lower()
    if "studionet" not in normalized or RPC_URL.lower() not in normalized or "61999" not in normalized:
        raise VerificationError("GenLayer CLI network info does not confirm Studionet RPC and chain 61999")
    encoding = verify_legacy_cli_encoding()
    return {"version": version, "network": "studionet", "rpc_url": RPC_URL, **encoding}


def _cli_run(*args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    """Run a read-only/account-selection CLI command without returning raw output in errors."""
    try:
        result = subprocess.run(
            _genlayer_command(*args),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VerificationError(f"GenLayer CLI invocation failed ({type(exc).__name__})") from exc
    if result.returncode != 0:
        raise VerificationError(f"GenLayer CLI command failed with exit code {result.returncode}")
    return result


def parse_cli_accounts(output: str) -> tuple[dict[str, CliAccount], str]:
    """Extract only account names, public addresses, unlocked state, and active alias."""
    accounts: dict[str, CliAccount] = {}
    active = ""
    for raw_line in output.splitlines():
        line = raw_line.strip()
        match = re.match(r"^(\*\s*)?(.+?)\s+(0x[a-fA-F0-9]{40})(?:\s+(.*))?$", line)
        if not match:
            continue
        marker, name, address, flags = match.groups()
        name = name.strip()
        flags = flags or ""
        accounts[name] = CliAccount(name=name, address=address, unlocked="unlocked" in flags)
        if marker or "(active)" in flags:
            active = name
    return accounts, active


def encode_cli_write_intent(
    contract: str,
    method: str,
    args: list[Any],
    rotations: int,
    target_contract: str | None = None,
) -> str:
    """Serialize typed SDK arguments for the isolated CLI deploy-script adapter."""
    return json.dumps(
        {
            "contract": target_contract or contract,
            "method": method,
            "args": args,
            "rotations": rotations,
        },
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def derive_action_id(
    policy_id: str,
    agent_address: str,
    nonce: int,
    action_json: str,
    policy_instance: int = 1,
) -> str:
    """Mirror preview_action_id for nodes whose preview view RPC is broken."""
    raw = json.loads(action_json)
    action_digest = hashlib.sha256(_canonical(raw)).hexdigest()
    normalized_address = to_checksum_address(agent_address)
    preimage = f"{policy_id}|{int(policy_instance)}|{normalized_address}|{int(nonce)}|{action_digest}"
    return hashlib.sha256(preimage.encode("utf-8")).hexdigest()


def scenario_step(label: str, operation: str, nonce: int) -> str:
    """Keep recovered writes distinct when an expired scenario gets a fresh nonce."""
    suffix = "" if nonce == 1 else f".nonce-{nonce}"
    return f"{label}.{operation}{suffix}"


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


def _consensus_outcome(tx: dict[str, Any]) -> str | None:
    """Normalize the current transaction-result field without conflating it with status."""
    value = tx.get("result_name") or tx.get("consensus_result") or tx.get("consensus_outcome")
    if isinstance(value, str):
        return value.upper()
    value = tx.get("result")
    if isinstance(value, int):
        return {
            0: "IDLE",
            1: "MAJORITY_AGREE",
            2: "MAJORITY_DISAGREE",
            3: "MAJORITY_TIMEOUT",
            4: "DETERMINISTIC_VIOLATION",
            5: "NO_MAJORITY",
        }.get(value)
    return None


def _finalized_no_majority_without_execution(tx: dict[str, Any]) -> bool:
    """Only finalized consensus failure with no VM result is eligible for a fresh intent."""
    return (
        tx.get("status") == "FINALIZED"
        and _consensus_outcome(tx) == "NO_MAJORITY"
        and tx.get("execution_result") is None
    )


def _finalized_contract_execution_error(tx: dict[str, Any]) -> bool:
    """Recognize a finalized VM failure that made no application-state change."""
    return (
        isinstance(tx, dict)
        and tx.get("status") == "FINALIZED"
        and tx.get("consensus_outcome") in ("MAJORITY_AGREE", "MAJORITY_DISAGREE")
        and tx.get("execution_result") == "ERROR"
        and tx.get("classification") == "contract_execution_failure"
    )


def _record_action_nonce(checkpoint: "Checkpoint", nonce: int) -> None:
    """Keep the application nonce high-water mark aligned with finalized state."""
    checkpoint.data["last_action_nonce"] = max(
        int(checkpoint.data.get("last_action_nonce") or 0), int(nonce)
    )


def is_transient_sdk_read_error(error: str) -> bool:
    """Return true only for recognized transport/service failures, not bad calls."""
    lowered = error.lower()
    return any(
        marker in lowered
        for marker in (
            "unknownrpcerror",
            "badgateway",
            "serviceunavailable",
            "too many requests",
            "http 502",
            "502 bad gateway",
            "status code 502",
            "status code 503",
            "status code 504",
            "econnreset",
            "etimedout",
            "0xc0000409",
            "3221226505",
            "timed out",
            "connection reset",
        )
    )


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


def guard_cross_checkpoint_nonce_intents(
    checkpoint: Checkpoint,
    signer_address: str,
    latest_nonce: int,
    target_contract: str | None = None,
) -> list[dict[str, Any]]:
    """Block writes when another checkpoint has an unresolved intent for this signer.

    A same-nonce FINALIZED record in another checkpoint proves that a
    hashless intent was not the transaction accepted by the chain. The prior
    broadcast-versus-drop history remains unknown and is preserved in the
    checkpoint; the occupied nonce itself is safe to move past.
    """
    root = Path(".boundaryos")
    current_path = checkpoint.path.resolve()
    if not root.exists():
        return []

    finalized_by_nonce: dict[int, tuple[str, dict[str, Any]]] = {}
    files: list[tuple[Path, dict[str, Any]]] = []
    for path in root.rglob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            continue
        files.append((path, data))
        txs = data.get("transactions", {})
        if not isinstance(txs, dict):
            continue
        for tx_id, tx in txs.items():
            if not isinstance(tx, dict) or tx.get("status") != "FINALIZED":
                continue
            if str(tx.get("sender", "")).lower() != signer_address.lower():
                continue
            nonce = tx.get("nonce")
            if nonce is None:
                continue
            try:
                nonce_value = int(nonce)
            except (TypeError, ValueError):
                continue
            prior = finalized_by_nonce.get(nonce_value)
            if prior and prior[0].lower() != str(tx_id).lower():
                raise UnresolvedBroadcast(
                    f"checkpoints contain conflicting FINALIZED transaction hashes for signer nonce {nonce_value}"
                )
            finalized_by_nonce[nonce_value] = (str(tx_id), tx)

    reconciled: list[dict[str, Any]] = []
    unresolved_phases = {
        "intent_saved", "broadcast_unknown", "outer_broadcast", "broadcast",
        "broadcast_recovered", "nonce_conflict",
    }
    for path, data in files:
        if path.resolve() == current_path:
            continue
        if str(data.get("signer_address", "")).lower() != signer_address.lower():
            continue
        changed = False
        steps = data.get("steps", {})
        if not isinstance(steps, dict):
            continue
        for step_name, item in steps.items():
            if not isinstance(item, dict) or item.get("phase") not in unresolved_phases:
                continue
            if str(item.get("signer_address", data.get("signer_address", ""))).lower() != signer_address.lower():
                continue
            nonce = item.get("reserved_nonce")
            try:
                nonce = int(nonce)
            except (TypeError, ValueError):
                raise UnresolvedBroadcast(
                    f"checkpoint {path.name} has unresolved step {step_name} without a valid reserved nonce"
                )
            matching = finalized_by_nonce.get(nonce)
            if matching is None and latest_nonce > nonce and target_contract:
                prior_contract = str(item.get("contract_address", data.get("contract_address", "")))
                if prior_contract and prior_contract.lower() != target_contract.lower():
                    # The signer nonce has advanced and this older intent is
                    # bound to a different contract. Preserve its uncertain
                    # history while allowing isolated verification on the
                    # requested target.
                    continue
            if matching is None or latest_nonce <= nonce:
                raise UnresolvedBroadcast(
                    f"checkpoint {path.name} has unresolved step {step_name} at signer nonce {nonce}; "
                    "no different finalized transaction proves that nonce was consumed; refusing a write"
                )
            tx_id, tx = matching
            prior_tx_id = item.get("tx_id") or item.get("outer_tx_hash")
            if prior_tx_id and str(prior_tx_id).lower() != tx_id.lower():
                raise UnresolvedBroadcast(
                    f"checkpoint {path.name} has transaction identity {prior_tx_id} for nonce {nonce}; "
                    f"a different hash {tx_id} finalized at that nonce; reconcile the saved transaction first"
                )
            if prior_tx_id and str(prior_tx_id).lower() == tx_id.lower():
                item.update({
                    "phase": "reconciled_finalized",
                    "tx_id": tx_id,
                    "status": "FINALIZED",
                    "consensus_outcome": tx.get("consensus_outcome"),
                    "execution_result": tx.get("execution_result"),
                    "reconciled_at": _now(),
                })
            else:
                item.update({
                    "phase": "nonce_consumed_by_different_finalized_tx",
                    "broadcast_disposition": "unknown; original transaction was not finalized under its missing identity",
                    "superseded_by_tx_id": tx_id,
                    "superseded_by_status": "FINALIZED",
                    "reconciled_at": _now(),
                })
            changed = True
            relative_path = path.resolve().relative_to(Path.cwd().resolve()).as_posix()
            reconciled.append({"checkpoint": relative_path, "step": step_name, "nonce": nonce, "tx_id": tx_id})
        if changed:
            payload = json.dumps(data, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
            handle, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
            try:
                with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as temp:
                    temp.write(payload)
                    temp.flush()
                    os.fsync(temp.fileno())
                os.replace(temp_name, path)
            finally:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)
    return reconciled


class StudionetVerifier:
    def __init__(
        self,
        contract: str,
        checkpoint: Checkpoint,
        account: Any,
        client: Any,
        cli_signing: bool = False,
        cli_active_account: str = "",
    ):
        self.contract = contract
        self.checkpoint = checkpoint
        self.account = account
        self.client = client
        self.cli_signing = cli_signing
        self.cli_active_account = cli_active_account
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

    def read(
        self, method: str, args: list[Any] | None = None, contract_address: str | None = None
    ) -> Any:
        """Read finalized contract state through the official typed Python SDK.

        The CLI parser coerces address-shaped strings to ``CalldataAddress`` and
        cannot faithfully represent BoundaryOS views whose ABI parameter is a
        string containing an address. The SDK accepts typed Python strings and
        decodes the result without the legacy hand-built RPC/RLP path.
        """
        read_args = args or []
        delay = 1.0
        for attempt in range(RETRY_LIMIT):
            try:
                return self.client.read_contract(
                    address=contract_address or self.contract,
                    function_name=method,
                    args=read_args,
                    transaction_hash_variant=TransactionHashVariant.LATEST_FINAL,
                )
            except Exception as exc:
                transient = is_transient_sdk_read_error(f"{type(exc).__name__} {exc}")
                if transient and attempt + 1 < RETRY_LIMIT:
                    self.emit(
                        "read_transport_retry",
                        method=method,
                        attempt=attempt + 1,
                        limit=RETRY_LIMIT,
                        error_class=type(exc).__name__,
                    )
                    time.sleep(delay)
                    delay = min(delay * 2, 8.0)
                    continue
                if transient:
                    raise TransportFailure(
                        f"GenLayer SDK read {method} failed after {RETRY_LIMIT} bounded attempts "
                        f"({type(exc).__name__})"
                    ) from exc
                raise RpcFailure(
                    f"GenLayer SDK finalized read {method} failed ({type(exc).__name__})"
                ) from exc
        raise TransportFailure(f"GenLayer SDK read {method} exhausted bounded retries")

    def tx_record(self, tx_id: str) -> dict[str, Any]:
        status = self.rpc("gen_getTransactionStatus", [tx_id])
        tx = self.rpc("eth_getTransactionByHash", [tx_id])
        if not isinstance(tx, dict):
            tx = {}
        consensus = tx.get("consensus_data") or {}
        votes = consensus.get("votes") or {}
        leader = consensus.get("leader_receipt") or [{}]
        leader = leader[0] if leader else {}
        last_round = tx.get("last_round") or {}
        round_votes = last_round.get("validator_votes_name") or last_round.get("validator_votes") or []
        return {
            "tx_id": tx_id,
            "status": status,
            "sender": tx.get("from_address"),
            "nonce": tx.get("nonce"),
            "raw_consensus_result": tx.get("result"),
            "consensus_outcome": _consensus_outcome(tx),
            "validator_votes": votes or round_votes,
            "validator_count": last_round.get("validators_count"),
            "consensus_round": last_round.get("round"),
            "rounds_observed": tx.get("num_of_rounds"),
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
                if record["status"] == "FINALIZED":
                    for saved_step in self.checkpoint.data.get("steps", {}).values():
                        if saved_step.get("tx_id") == tx_id:
                            saved_step["phase"] = "finalized"
                            saved_step["finalized_at"] = record.get("observed_at", _now())
                elif record["status"] in ("CANCELED", "CANCELLED", "REVERTED"):
                    for saved_step in self.checkpoint.data.get("steps", {}).values():
                        if saved_step.get("tx_id") == tx_id:
                            saved_step["phase"] = "terminal_failure"
                            saved_step["finalized_at"] = record.get("observed_at", _now())
                self.checkpoint.save()
                self.emit("transaction_status", **record, poll=poll + 1)
                if record["status"] == "FINALIZED":
                    if record.get("consensus_outcome") in {
                        "NO_MAJORITY",
                        "MAJORITY_DISAGREE",
                        "MAJORITY_TIMEOUT",
                        "DETERMINISTIC_VIOLATION",
                    }:
                        current["classification"] = "consensus_failure"
                        self.checkpoint.save()
                        raise ConsensusFailure(
                            f"transaction finalized with consensus outcome {record['consensus_outcome']} "
                            f"(rounds={record.get('rounds_observed')}, votes={record.get('validator_votes')})"
                        )
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
            tx_id = HexBytes(decoded_event["args"]["txId"]).to_0x_hex()
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
        contract_address: str | None = None,
    ) -> dict[str, Any]:
        signer = signer or self.account
        saved = self.checkpoint.data.get("steps", {}).get(step)
        expected_contract = contract_address or self.contract
        expected_args_digest = hashlib.sha256(_canonical(args)).hexdigest()
        if saved and (
            saved.get("method") != method
            or saved.get("contract_address", self.contract).lower() != expected_contract.lower()
            or saved.get("signer_address", signer.address).lower() != signer.address.lower()
            or saved.get("args_sha256") != expected_args_digest
        ):
            raise VerificationError(f"checkpointed step {step} is bound to different write arguments")
        existing = self.reconcile(step, max_polls=max_polls)
        if existing:
            return existing
        latest = int(self.rpc("eth_getTransactionCount", [signer.address, "latest"]), 16)
        pending = int(self.rpc("eth_getTransactionCount", [signer.address, "pending"]), 16)
        if latest != pending:
            raise UnresolvedBroadcast(f"signer has pending transactions (latest={latest}, pending={pending}); refusing a new write")
        reconciled_intents = guard_cross_checkpoint_nonce_intents(
            self.checkpoint, signer.address, latest, target_contract=expected_contract
        )
        if reconciled_intents:
            self.checkpoint.data.setdefault("cross_checkpoint_nonce_reconciliations", []).extend(
                reconciled_intents
            )
            self.checkpoint.save()
            self.emit("cross_checkpoint_nonce_reconciled", intents=reconciled_intents)
        intent = {
            "phase": "intent_saved",
            "method": method,
            "contract_address": contract_address or self.contract,
            "signer_address": signer.address,
            "reserved_nonce": pending,
            "args_sha256": expected_args_digest,
            "expected_execution_error": expected_execution_error,
            "created_at": _now(),
        }
        self.checkpoint.data.setdefault("steps", {})[step] = intent
        self.checkpoint.save()
        self.emit("write_intent_saved", step=step, method=method, reserved_nonce=pending)
        try:
            if self.cli_signing:
                tx_id = self._cli_write_once(
                    step, method, args, rotations, signer, intent, pending, max_polls,
                    contract_address=contract_address,
                )
            else:
                provider = self.client.provider
                original_make_request = provider.make_request

                def record_outer_hash(rpc_method: str, rpc_params: list[Any]) -> Any:
                    response = original_make_request(rpc_method, rpc_params)
                    if rpc_method == "eth_sendRawTransaction" and isinstance(response, dict) and response.get("result"):
                        intent.update({"phase": "outer_broadcast", "outer_tx_hash": response["result"], "outer_broadcast_at": _now()})
                        self.checkpoint.save()
                        self.emit("outer_transaction_broadcast", step=step, method=method, outer_tx_hash=response["result"], reserved_nonce=pending)
                    return response

                provider.make_request = record_outer_hash
                try:
                    tx_id = self.client.write_contract(
                        address=contract_address or self.contract,
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

    def _cli_write_once(
        self,
        step: str,
        method: str,
        args: list[Any],
        rotations: int,
        signer: Any,
        intent: dict[str, Any],
        reserved_nonce: int,
        max_polls: int,
        contract_address: str | None = None,
    ) -> str:
        """Sign with the selected CLI keystore account and checkpoint its broadcast hash."""
        account_name = getattr(signer, "name", "")
        if not account_name:
            raise VerificationError("CLI-backed writes require a named CLI account")
        selected = False
        process = None
        tx_id = ""
        workflow_dir: Path | None = None
        try:
            _cli_run("account", "use", account_name)
            selected = True
            # The CLI's generic --args parser guesses address/JSON types and cannot
            # preserve BoundaryOS's JSON-valued string arguments. Its documented
            # deploy-script route hands a real GenLayer client to a local JS module;
            # the SDK then receives the exact typed strings and selected keystore.
            workflow_root = Path(".boundaryos") / "cli-workflows"
            workflow_root.mkdir(parents=True, exist_ok=True)
            workflow_dir = Path(tempfile.mkdtemp(prefix="write-", dir=workflow_root))
            (workflow_dir / "package.json").write_text('{"type":"module"}\n', encoding="utf-8")
            deploy_dir = workflow_dir / "deploy"
            deploy_dir.mkdir()
            script = """export default async function (client) {
  const payload = JSON.parse(process.env.BOUNDARYOS_CLI_WRITE_INTENT || "null");
  if (!payload || !Array.isArray(payload.args)) throw new Error("missing write intent");
  const hash = await client.writeContract({
    address: payload.contract,
    functionName: payload.method,
    args: payload.args,
    value: 0n,
    consensusMaxRotations: payload.rotations,
  });
  console.log("BoundaryOS transaction hash:", hash);
}
"""
            (deploy_dir / "01_boundaryos_write.js").write_text(script, encoding="utf-8")
            process_env = os.environ.copy()
            process_env["BOUNDARYOS_CLI_WRITE_INTENT"] = encode_cli_write_intent(
                self.contract, method, args, rotations, target_contract=contract_address
            )
            command = _genlayer_command("deploy")
            process = subprocess.Popen(
                command,
                cwd=workflow_dir,
                env=process_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            wait_for_hash = False
            hash_pattern = re.compile(r"0x[a-fA-F0-9]{64}")
            ansi_pattern = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
            assert process.stdout is not None
            for line in process.stdout:
                clean = ansi_pattern.sub("", line)
                if "BoundaryOS transaction hash:" in clean:
                    wait_for_hash = True
                if not wait_for_hash:
                    continue
                match = hash_pattern.search(clean)
                if not match:
                    continue
                outer_hash = match.group(0)
                intent.update({
                    "phase": "outer_broadcast",
                    "outer_tx_hash": outer_hash,
                    "outer_broadcast_at": _now(),
                    "broadcast_adapter": "genlayer-cli-keystore",
                    "cli_account_name": account_name,
                })
                self.checkpoint.save()
                self.emit(
                    "outer_transaction_broadcast",
                    step=step,
                    method=method,
                    outer_tx_hash=outer_hash,
                    reserved_nonce=reserved_nonce,
                    adapter="genlayer-cli-keystore",
                )
                wait_for_hash = False
                try:
                    tx_id = self._recover_genlayer_tx_id(step, intent, max_polls=1)
                except (TransportFailure, RpcFailure):
                    # The durable outer hash is enough to recover after a process or
                    # RPC interruption. Keep polling the CLI's own bounded wait.
                    pass
            process.wait(timeout=900)
        except subprocess.TimeoutExpired:
            if process is not None:
                process.kill()
                process.wait(timeout=30)
            if not intent.get("outer_tx_hash"):
                intent["phase"] = "broadcast_unknown"
            self.checkpoint.save()
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=30)
            if selected and self.cli_active_account:
                try:
                    _cli_run("account", "use", self.cli_active_account)
                except VerificationError as exc:
                    intent["active_account_restore_failed"] = True
                    intent["active_account_restore_error_class"] = type(exc).__name__
                    self.checkpoint.save()
            if workflow_dir is not None:
                shutil.rmtree(workflow_dir, ignore_errors=True)

        if intent.get("active_account_restore_failed"):
            raise VerificationError("CLI active account could not be restored; stop before any subsequent write")
        if not intent.get("outer_tx_hash"):
            intent.update({"phase": "broadcast_unknown", "cli_exit_code": process.returncode if process else None})
            self.checkpoint.save()
            raise UnresolvedBroadcast(
                "GenLayer CLI exited without a captured write transaction hash; automatic resend is disabled"
            )
        if not tx_id:
            tx_id = self._recover_genlayer_tx_id(step, intent, max_polls=max_polls)
        # CLI's decided/finalized output is deliberately ignored. The harness
        # independently checks consensus status and finality using the captured ID.
        return tx_id

    def deploy_once(
        self,
        source_path: Path,
        max_polls: int = 50,
        constructor_args: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Explicitly deploy source once via the official CLI script client, then reconcile."""
        if not self.cli_signing:
            raise VerificationError("checkpointed deployment requires the CLI keystore signer backend")
        source_path = source_path.resolve()
        if not source_path.is_file():
            raise VerificationError("deployment source file does not exist")
        source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
        args = constructor_args or []
        args_hash = hashlib.sha256(_canonical(args)).hexdigest()
        step = "deployment.deploy"
        item = self.checkpoint.data.setdefault("steps", {}).get(step)
        if item:
            if item.get("source_sha256") != source_hash or item.get("constructor_args_sha256") != args_hash:
                raise VerificationError("deployment checkpoint is bound to different source bytes or constructor arguments")
            if item.get("contract_address"):
                return item
            existing = self.reconcile(step, max_polls=max_polls)
            if existing is None:
                raise VerificationError("deployment step has no reconciliable broadcast")
            item = self.checkpoint.data["steps"][step]
            if not item.get("contract_address"):
                self._recover_deployment_address(step, item, max_polls)
            return self.checkpoint.data["steps"][step]

        latest = int(self.rpc("eth_getTransactionCount", [self.account.address, "latest"]), 16)
        pending = int(self.rpc("eth_getTransactionCount", [self.account.address, "pending"]), 16)
        if latest != pending:
            raise UnresolvedBroadcast(
                f"deployment signer has pending transactions (latest={latest}, pending={pending}); refusing to deploy"
            )
        reconciled_intents = guard_cross_checkpoint_nonce_intents(
            self.checkpoint, self.account.address, latest
        )
        if reconciled_intents:
            self.checkpoint.data.setdefault("cross_checkpoint_nonce_reconciliations", []).extend(
                reconciled_intents
            )
            self.checkpoint.save()
            self.emit("cross_checkpoint_nonce_reconciled", intents=reconciled_intents)
        item = {
            "phase": "intent_saved",
            "method": "deployContract",
            "signer_address": self.account.address,
            "reserved_nonce": pending,
            "source_sha256": source_hash,
            "constructor_args_sha256": args_hash,
            "constructor_args": args,
            "created_at": _now(),
            "broadcast_adapter": "genlayer-cli-deploy-script",
        }
        self.checkpoint.data["steps"][step] = item
        self.checkpoint.save()
        self.emit("deployment_intent_saved", source_sha256=source_hash, reserved_nonce=pending)

        _cli_run("account", "use", getattr(self.account, "name", ""))
        workflow_root = Path(".boundaryos") / "cli-workflows"
        workflow_root.mkdir(parents=True, exist_ok=True)
        workflow_dir = Path(tempfile.mkdtemp(prefix="deploy-", dir=workflow_root))
        deployed_address = ""
        process = None
        active_restore_failed = False
        try:
            (workflow_dir / "package.json").write_text('{"type":"module"}\n', encoding="utf-8")
            deploy_dir = workflow_dir / "deploy"
            deploy_dir.mkdir()
            script = """import { readFile } from "node:fs/promises";
export default async function (client) {
  const payload = JSON.parse(process.env.BOUNDARYOS_CLI_DEPLOY_INTENT || "null");
  if (!payload) throw new Error("missing deployment intent");
  let hash = payload.transaction_hash;
  if (!hash) {
    const code = await readFile(payload.source_path, "utf8");
    hash = await client.deployContract({ code, args: payload.constructor_args || [], leaderOnly: false });
    console.log("BoundaryOS deployment transaction hash:", hash);
  }
  const receipt = await client.waitForTransactionReceipt({
    hash,
    waitUntil: "decided",
    retries: 100,
    interval: 5000,
    fullTransaction: true,
  });
  const address = receipt?.data?.contract_address ?? receipt?.txDataDecoded?.contractAddress;
  if (address) console.log("BoundaryOS deployed contract address:", address);
}
"""
            (deploy_dir / "01_boundaryos_deploy.js").write_text(script, encoding="utf-8")
            process_env = os.environ.copy()
            process_env["BOUNDARYOS_CLI_DEPLOY_INTENT"] = json.dumps(
                {"source_path": str(source_path), "constructor_args": args},
                separators=(",", ":"), ensure_ascii=True
            )
            process = subprocess.Popen(
                _genlayer_command("deploy"),
                cwd=workflow_dir,
                env=process_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            wait_for_hash = False
            hash_pattern = re.compile(r"0x[a-fA-F0-9]{64}")
            address_pattern = re.compile(r"0x[a-fA-F0-9]{40}")
            ansi_pattern = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
            assert process.stdout is not None
            for line in process.stdout:
                clean = ansi_pattern.sub("", line)
                if "BoundaryOS deployment transaction hash:" in clean:
                    wait_for_hash = True
                if wait_for_hash:
                    match = hash_pattern.search(clean)
                    if match:
                        outer_hash = match.group(0)
                        item.update({"phase": "outer_broadcast", "outer_tx_hash": outer_hash, "outer_broadcast_at": _now()})
                        self.checkpoint.save()
                        self.emit("deployment_outer_transaction_broadcast", outer_tx_hash=outer_hash, reserved_nonce=pending)
                        wait_for_hash = False
                        try:
                            self._recover_genlayer_tx_id(step, item, max_polls=1)
                        except (TransportFailure, RpcFailure):
                            pass
                if "BoundaryOS deployed contract address:" in clean:
                    match = address_pattern.search(clean)
                    if match:
                        deployed_address = match.group(0)
                        item["contract_address"] = deployed_address
                        item["address_observed_at"] = _now()
                        self.checkpoint.save()
            process.wait(timeout=900)
        except subprocess.TimeoutExpired:
            if process is not None:
                process.kill()
                process.wait(timeout=30)
            if not item.get("outer_tx_hash"):
                item["phase"] = "broadcast_unknown"
            self.checkpoint.save()
        except Exception as exc:
            item.update({
                "phase": "outer_broadcast" if item.get("outer_tx_hash") else "broadcast_unknown",
                "error_class": type(exc).__name__,
                "updated_at": _now(),
            })
            self.checkpoint.save()
            raise UnresolvedBroadcast(
                "deployment CLI run stopped; saved intent and any captured outer transaction hash were retained"
            ) from exc
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=30)
            try:
                _cli_run("account", "use", self.cli_active_account)
            except VerificationError:
                active_restore_failed = True
            shutil.rmtree(workflow_dir, ignore_errors=True)

        if active_restore_failed:
            item["active_account_restore_failed"] = True
            self.checkpoint.save()
            raise VerificationError("CLI active account could not be restored after deployment attempt")
        if not item.get("outer_tx_hash"):
            item.update({"phase": "broadcast_unknown", "cli_exit_code": process.returncode if process else None})
            self.checkpoint.save()
            raise UnresolvedBroadcast("deployment CLI exited without a captured transaction hash; refusing to redeploy")
        tx_id = item.get("tx_id") or self._recover_genlayer_tx_id(step, item, max_polls=max_polls)
        intent = self.checkpoint.data["steps"].get(step, {})
        if intent.get("tx_id") != tx_id:
            intent.update({"phase": "broadcast", "tx_id": tx_id, "broadcast_at": _now()})
            self.checkpoint.save()
        record = self.poll_finalized(tx_id, max_polls=max_polls)
        item.update({
            "status": record.get("status"),
            "consensus_outcome": record.get("consensus_outcome"),
            "execution_result": record.get("execution_result"),
            "finalized_at": _now(),
        })
        self.checkpoint.save()
        if not item.get("contract_address"):
            self._recover_deployment_address(step, item, max_polls)
        return self.checkpoint.data["steps"][step]

    def _recover_deployment_address(self, step: str, item: dict[str, Any], max_polls: int) -> None:
        """Recover a deployment address from an existing transaction; never deploy again."""
        tx_id = item.get("tx_id")
        if not tx_id:
            raise UnresolvedBroadcast("deployment has no recovered transaction ID; refusing to redeploy")
        workflow_root = Path(".boundaryos") / "cli-workflows"
        workflow_root.mkdir(parents=True, exist_ok=True)
        workflow_dir = Path(tempfile.mkdtemp(prefix="receipt-", dir=workflow_root))
        process = None
        try:
            (workflow_dir / "package.json").write_text('{"type":"module"}\n', encoding="utf-8")
            deploy_dir = workflow_dir / "deploy"
            deploy_dir.mkdir()
            script = """export default async function (client) {
  const payload = JSON.parse(process.env.BOUNDARYOS_CLI_DEPLOY_INTENT || "null");
  const receipt = await client.waitForTransactionReceipt({
    hash: payload.transaction_hash,
    waitUntil: "finalized",
    retries: 100,
    interval: 5000,
    fullTransaction: true,
  });
  const address = receipt?.data?.contract_address ?? receipt?.txDataDecoded?.contractAddress;
  if (address) console.log("BoundaryOS deployed contract address:", address);
}
"""
            (deploy_dir / "01_boundaryos_receipt.js").write_text(script, encoding="utf-8")
            process_env = os.environ.copy()
            process_env["BOUNDARYOS_CLI_DEPLOY_INTENT"] = json.dumps(
                {"transaction_hash": tx_id}, separators=(",", ":"), ensure_ascii=True
            )
            process = subprocess.Popen(
                _genlayer_command("deploy"),
                cwd=workflow_dir,
                env=process_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            address_pattern = re.compile(r"0x[a-fA-F0-9]{40}")
            ansi_pattern = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
            assert process.stdout is not None
            for line in process.stdout:
                clean = ansi_pattern.sub("", line)
                if "BoundaryOS deployed contract address:" in clean:
                    match = address_pattern.search(clean)
                    if match:
                        item["contract_address"] = match.group(0)
                        item["address_observed_at"] = _now()
                        self.checkpoint.save()
            process.wait(timeout=900)
        except subprocess.TimeoutExpired:
            if process is not None:
                process.kill()
                process.wait(timeout=30)
            raise TransportFailure("receipt-only deployment address recovery timed out")
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=30)
            shutil.rmtree(workflow_dir, ignore_errors=True)
        if not item.get("contract_address"):
            raise RpcFailure("finalized deployment receipt did not include a contract address")


def _as_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return value
    return value


def initialize_runtime(
    require_stable_signers: bool = False,
    signer_backend: str = "sdk",
    cli_primary: str = "my-studionet-wallet",
    cli_child: str = "bradbury-e2e",
) -> tuple[Any, Any, str, list[Any], bool, bool, str]:
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
    if plugin.rpc_url != RPC_URL:
        raise VerificationError(f"configured Studionet RPC must be exactly {RPC_URL}")
    general.plugin_config = plugin
    if signer_backend == "cli":
        account_result = _cli_run("account", "list")
        cli_accounts, active_account = parse_cli_accounts(account_result.stdout)
        primary = cli_accounts.get(cli_primary)
        child = cli_accounts.get(cli_child)
        if primary is None or not primary.unlocked:
            raise VerificationError(f"named primary CLI account {cli_primary!r} is missing or locked")
        if child is None or not child.unlocked:
            raise VerificationError(f"named child CLI account {cli_child!r} is missing or locked")
        if primary.address.lower() == child.address.lower():
            raise VerificationError("primary and child CLI accounts must have different public addresses")
        if active_account != cli_primary:
            raise VerificationError(
                f"CLI active account is {active_account!r}; select configured primary {cli_primary!r} before live verification"
            )
        # The SDK requires a local account object to populate ``from`` even for
        # read-only calls. This ephemeral in-memory identity is never used to
        # sign writes or persisted; all writes continue through the selected
        # named CLI wallet below.
        read_account = create_account()
        client = create_client(chain=studionet, endpoint=plugin.rpc_url, account=read_account)
        return primary, client, plugin.rpc_url, [primary, child], True, True, active_account

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
    return account, client, plugin.rpc_url, accounts, stable_primary, stable_child, ""


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


def reconcile_checkpoint_before_writes(verifier: StudionetVerifier, max_polls: int) -> None:
    """Reconcile every saved broadcast before the suite may create a new one."""
    for step, item in list(verifier.checkpoint.data.get("steps", {}).items()):
        phase = item.get("phase")
        if phase in ("finalized", "outer_reverted", "terminal_failure"):
            continue
        if item.get("tx_id") or item.get("outer_tx_hash") or phase in (
            "intent_saved", "broadcast_unknown", "nonce_conflict"
        ):
            try:
                verifier.reconcile(step, max_polls=max_polls)
            except ContractExecutionFailure:
                # A finalized VM error is a known terminal outcome, not an
                # ambiguous broadcast. Keep its evidence and allow scenario
                # logic to decide whether a fresh application nonce is safe.
                tx_id = item.get("tx_id")
                tx = verifier.checkpoint.data.get("transactions", {}).get(tx_id, {})
                if not _finalized_contract_execution_error(tx):
                    raise
            refreshed = verifier.checkpoint.data.get("steps", {}).get(step, {})
            if not refreshed.get("tx_id"):
                raise UnresolvedBroadcast(f"checkpoint step {step} remains unresolved; refusing new writes")


def verify_existing_contract_read(verifier: StudionetVerifier, signer_address: str) -> dict[str, Any]:
    """Prove the official typed SDK can read a deployed contract with string args."""
    result = _as_json(verifier.read("get_agent", [signer_address]))
    if not isinstance(result, dict) or result.get("agent", "").lower() != signer_address.lower():
        raise VerificationError("typed SDK finalized read did not return the requested agent identity")
    if not isinstance(result.get("registered"), bool) or not isinstance(result.get("frozen"), bool):
        raise VerificationError("typed SDK finalized read returned an unexpected agent schema")
    return result


def action_digest(action: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(action)).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", default=DEFAULT_CONTRACT)
    parser.add_argument("--rpc-url", default=None, help="RPC endpoint from official compatible tooling; defaults to configured Studionet RPC")
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--deploy-source", type=Path, help="explicitly deploy this source once and checkpoint its transaction")
    parser.add_argument(
        "--deploy-args-json", default="[]",
        help="JSON array of public constructor arguments for --deploy-source",
    )
    parser.add_argument("--deployment-checkpoint", type=Path, default=DEFAULT_DEPLOYMENT_CHECKPOINT)
    parser.add_argument("--inspect-existing", action="store_true", help="read-only inspect the known finalized proposal")
    parser.add_argument("--preflight-only", action="store_true", help="verify the pinned CLI, signer access, network, RPC, chain ID, and typed SDK reads without writing")
    parser.add_argument("--run-live-suite", action="store_true", help="explicitly permit live writes; never deploys")
    parser.add_argument(
        "--consumer-contract",
        help="deployed test-only BoundaryConsumer address; enables the two-stage message smoke test",
    )
    parser.add_argument("--resume-step", help="reconcile a previously checkpointed write step without sending any new transaction")
    parser.add_argument("--max-polls", type=int, default=30)
    parser.add_argument(
        "--signer-backend",
        choices=("sdk", "cli"),
        default=os.environ.get("BOUNDARYOS_SIGNER_BACKEND", "cli"),
        help="use SDK-configured keys or the installed GenLayer CLI's active keystore account",
    )
    parser.add_argument("--cli-primary", default=os.environ.get("BOUNDARYOS_CLI_PRIMARY", "my-studionet-wallet"))
    parser.add_argument("--cli-child", default=os.environ.get("BOUNDARYOS_CLI_CHILD", "bradbury-e2e"))
    options = parser.parse_args(argv)
    try:
        deployment_args = json.loads(options.deploy_args_json)
    except json.JSONDecodeError as exc:
        raise VerificationError("--deploy-args-json must be a JSON array") from exc
    if not isinstance(deployment_args, list):
        raise VerificationError("--deploy-args-json must be a JSON array")
    if not options.deploy_source and deployment_args:
        raise VerificationError("--deploy-args-json requires --deploy-source")
    if options.deploy_source and (options.run_live_suite or options.inspect_existing or options.resume_step or options.preflight_only):
        raise VerificationError("deployment is an explicit separate command; do not combine with inspection or suite writes")
    if options.deploy_source and options.signer_backend != "cli":
        raise VerificationError("checkpointed deployment requires --signer-backend cli")
    if options.run_live_suite and options.signer_backend != "cli":
        raise VerificationError("live verification writes require the pinned CLI-backed named-wallet signer")
    if options.resume_step and options.run_live_suite:
        raise VerificationError("--resume-step is read/reconcile-only and cannot be combined with --run-live-suite")
    if options.consumer_contract and not options.run_live_suite:
        raise VerificationError("--consumer-contract requires --run-live-suite")

    if options.rpc_url is not None and options.rpc_url != RPC_URL:
        raise VerificationError(f"only Studionet RPC {RPC_URL} is supported")
    account, client, rpc_url, accounts, stable_primary, stable_child, cli_active_account = initialize_runtime(
        require_stable_signers=options.run_live_suite or options.deploy_source is not None,
        signer_backend=options.signer_backend,
        cli_primary=options.cli_primary,
        cli_child=options.cli_child,
    )
    rpc_url = options.rpc_url or rpc_url
    if urlparse(rpc_url).scheme != "https" or not urlparse(rpc_url).netloc:
        raise VerificationError("RPC URL must be a valid HTTPS endpoint")
    verifier = None
    if options.deploy_source:
        deployment_source = options.deploy_source.resolve()
        if not deployment_source.is_file():
            raise VerificationError("deployment source file does not exist")
        checkpoint_path = options.deployment_checkpoint
        checkpoint_contract = DEPLOYMENT_CHECKPOINT_BINDING
        source_fingerprint = hashlib.sha256(
            deployment_source.read_bytes() + _canonical(deployment_args)
        ).hexdigest()
    else:
        deployment_source = None
        checkpoint_path = options.checkpoint
        checkpoint_contract = options.contract
        source_fingerprint = hashlib.sha256(Path("contracts/boundary_os.py").read_bytes()).hexdigest()
    checkpoint = Checkpoint(
        checkpoint_path,
        checkpoint_contract,
        account.address,
        source_fingerprint,
        bind_signer=stable_primary,
    )
    try:
        cli_details = verify_cli_network(rpc_url) if options.signer_backend == "cli" else None
        verifier = StudionetVerifier(
            options.contract,
            checkpoint,
            account,
            client,
            cli_signing=options.signer_backend == "cli",
            cli_active_account=cli_active_account,
        )
        verifier.rpc_url = rpc_url
        actual_chain = int(verifier.rpc("eth_chainId", []), 16)
        if actual_chain != CHAIN_ID:
            raise VerificationError(f"RPC returned chain ID {actual_chain}, expected {CHAIN_ID}")
        # Deployment does not depend on the selected signer being registered
        # in the inspection target. Keep this application-state preflight for
        # inspections and live suites, but do not block a permissionless
        # fixture deployment because its deployer is unrelated to that target.
        typed_read = (
            {"skipped": "deployment-only command; no existing application state is required"}
            if deployment_source is not None
            else verify_existing_contract_read(verifier, account.address)
        )
        verifier.checkpoint.data["chain_id_observed"] = actual_chain
        verifier.checkpoint.data["signer_nonce_latest"] = int(verifier.rpc("eth_getTransactionCount", [account.address, "latest"]), 16)
        verifier.checkpoint.data["signer_nonce_pending"] = int(verifier.rpc("eth_getTransactionCount", [account.address, "pending"]), 16)
        verifier.checkpoint.save()
        verifier.emit(
            "preflight", chain_id=actual_chain, rpc_url=rpc_url,
            contract=options.contract, signer=account.address,
            live_writes_enabled=options.run_live_suite,
            cli=cli_details,
            signer_accounts=[{"name": getattr(item, "name", ""), "address": item.address} for item in accounts]
            if options.signer_backend == "cli" else [],
            existing_contract_read=typed_read,
        )
        if options.preflight_only:
            return 0
        if deployment_source is not None:
            reconcile_checkpoint_before_writes(verifier, max_polls=options.max_polls)
            result = verifier.deploy_once(
                deployment_source,
                max_polls=options.max_polls,
                constructor_args=deployment_args,
            )
            verifier.emit(
                "deployment_complete",
                source_sha256=result.get("source_sha256"),
                tx_id=result.get("tx_id"),
                status=result.get("status"),
                consensus_outcome=result.get("consensus_outcome"),
                execution_result=result.get("execution_result"),
                contract_address=result.get("contract_address"),
            )
            return 0
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
            reconcile_checkpoint_before_writes(verifier, max_polls=options.max_polls)
            run_live_suite(
                verifier,
                account,
                accounts,
                max_polls=options.max_polls,
                consumer_contract_address=options.consumer_contract,
            )
        return 0
    finally:
        checkpoint.close()


def run_live_suite(
    verifier: StudionetVerifier,
    account: Any,
    accounts: list[Any],
    max_polls: int = 30,
    consumer_contract_address: str | None = None,
) -> None:
    """Run resumable diagnostic flows on the specified instance; never deploys."""
    signer_address = account.address
    if verifier.read("is_principal_admitted", [signer_address]) is not True:
        verifier.write_once(
            "setup.admit_principal",
            "admit_principal",
            [signer_address],
            max_polls=max_polls,
        )
        if verifier.read("is_principal_admitted", [signer_address]) is not True:
            raise VerificationError("principal admission finalized but finalized state is absent")
    agent = _as_json(verifier.read("get_agent", [signer_address]))
    if not isinstance(agent, dict):
        raise VerificationError("get_agent returned malformed state")
    if not agent.get("registered"):
        verifier.write_once(
            "setup.approve_root_agent",
            "approve_agent_registration",
            [signer_address],
            signer=account,
            max_polls=max_polls,
        )
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

    policy_instance = int(verifier.read("get_policy_instance", [policy_id]))
    if policy_instance <= 0:
        raise VerificationError("finalized policy instance generation is missing")

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
            aid = derive_action_id(policy_id, signer_address, nonce, action_json, policy_instance)
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
        if (
            consume
            and isinstance(receipt_value, dict)
            and receipt_value.get("decision") == "ALLOW"
            and not receipt_value.get("consumed")
            and int(receipt_value.get("expires_at", 0)) <= int(time.time())
        ):
            record.setdefault("expired_receipt_attempts", []).append(
                {
                    "action_id": aid,
                    "nonce": record["nonce"],
                    "expires_at": receipt_value.get("expires_at"),
                    "decision": receipt_value.get("decision"),
                    "receipt_digest": receipt_value.get("receipt_digest"),
                }
            )
            next_nonce = max(
                int(verifier.checkpoint.data.get("last_action_nonce") or 0), int(record["nonce"])
            ) + 1
            aid = derive_action_id(policy_id, signer_address, next_nonce, action_json, policy_instance)
            if _as_json(verifier.read("get_action", [aid])) or _as_json(verifier.read("get_receipt", [aid])):
                raise VerificationError(f"{label}: fresh nonce {next_nonce} already exists on chain; refusing reuse")
            record.update({"nonce": next_nonce, "action_id": aid, "created_at": _now()})
            record.pop("result", None)
            verifier.checkpoint.save()
            action_state = None
            receipt_value = None
        if not action_state:
            submit_step = scenario_step(label, "submit", int(record["nonce"]))
            prior_submit = verifier.checkpoint.data.get("steps", {}).get(submit_step, {})
            prior_tx_id = prior_submit.get("tx_id")
            prior_tx = verifier.checkpoint.data.get("transactions", {}).get(prior_tx_id, {})
            if prior_tx_id and _finalized_no_majority_without_execution(prior_tx):
                # A finalized NO_MAJORITY transaction has no contract execution.
                # Confirm the deterministic action ID is absent at finalized
                # state before moving to a fresh application nonce and proposal.
                if _as_json(verifier.read("get_action", [aid])):
                    raise VerificationError(
                        f"{label}: NO_MAJORITY submit has an unexpected finalized action; refusing retry"
                    )
                record.setdefault("no_majority_submit_attempts", []).append(
                    {"action_id": aid, "nonce": record["nonce"], "tx_id": prior_tx_id}
                )
                next_nonce = max(
                    int(verifier.checkpoint.data.get("last_action_nonce") or 0),
                    int(record["nonce"]),
                ) + 1
                aid = derive_action_id(policy_id, signer_address, next_nonce, action_json, policy_instance)
                if _as_json(verifier.read("get_action", [aid])):
                    raise VerificationError(
                        f"{label}: retry nonce {next_nonce} already exists on chain; refusing reuse"
                    )
                record.update({"nonce": next_nonce, "action_id": aid, "created_at": _now()})
                record.pop("result", None)
                verifier.checkpoint.save()
                submit_step = scenario_step(label, "submit", next_nonce)
            elif (
                prior_tx_id
                and _finalized_contract_execution_error(prior_tx)
                and int(record["nonce"]) <= int(verifier.checkpoint.data.get("last_action_nonce") or 0)
            ):
                # Preserve a finalized failed attempt whose application nonce
                # is behind finalized action state, then derive a fresh ID.
                if _as_json(verifier.read("get_action", [aid])) or _as_json(verifier.read("get_receipt", [aid])):
                    raise VerificationError(
                        f"{label}: failed submit unexpectedly has finalized action or receipt state"
                    )
                record.setdefault("failed_submit_attempts", []).append(
                    {"action_id": aid, "nonce": record["nonce"], "tx_id": prior_tx_id}
                )
                next_nonce = max(
                    int(verifier.checkpoint.data.get("last_action_nonce") or 0),
                    int(record["nonce"]),
                ) + 1
                aid = derive_action_id(policy_id, signer_address, next_nonce, action_json, policy_instance)
                if _as_json(verifier.read("get_action", [aid])) or _as_json(verifier.read("get_receipt", [aid])):
                    raise VerificationError(
                        f"{label}: retry nonce {next_nonce} already has action or receipt state; refusing reuse"
                    )
                record.update({"nonce": next_nonce, "action_id": aid, "created_at": _now()})
                record.pop("result", None)
                verifier.checkpoint.save()
                submit_step = scenario_step(label, "submit", next_nonce)
            verifier.write_once(
                submit_step,
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
        else:
            # A resumed checkpoint may have persisted an action but not its
            # application nonce high-water mark before interruption.
            _record_action_nonce(verifier.checkpoint, int(record["nonce"]))
            verifier.checkpoint.save()

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
                record["action_id"] = derive_action_id(
                    policy_id, signer_address, record["nonce"], action_json, policy_instance
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
                        scenario_step(label, "freeze", int(record["nonce"])),
                        "freeze_agent",
                        [signer_address, True],
                        max_polls=max_polls,
                    )
            verifier.write_once(
                scenario_step(label, "evaluate", int(record["nonce"])),
                "evaluate_action",
                [aid],
                rotations=5,
                max_polls=max_polls,
            )
            receipt_value = _as_json(verifier.read("get_receipt", [aid]))
            if not isinstance(receipt_value, dict):
                raise VerificationError(f"{label}: finalized evaluation did not produce a receipt")

        action_state = _as_json(verifier.read("get_action", [aid]))
        if not isinstance(action_state, dict) or action_state.get("state") != "EVALUATED":
            raise VerificationError(f"{label}: finalized receipt is not backed by EVALUATED action state")

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
                    scenario_step(label, "consume", int(record["nonce"])),
                    "consume_authorization",
                    [aid, receipt_value["action_digest"]],
                    max_polls=max_polls,
                )
            consumed = _as_json(verifier.read("get_receipt", [aid]))
            if not isinstance(consumed, dict) or consumed.get("consumed") is not True:
                raise VerificationError(f"{label}: finalized consumption not reflected in receipt state")
            replay_step = scenario_step(label, "replay", int(record["nonce"]))
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
                    scenario_step(label, "unfreeze", int(record["nonce"])),
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

    _verify_delegation_boundary(
        verifier, policy_id, account, accounts, policy, max_polls,
        child_contract_address=consumer_contract_address,
    )
    if consumer_contract_address:
        _verify_consumer_composability(
            verifier, policy_id, account, consumer_contract_address, policy, max_polls
        )

    # The delegated child reserves one cent; the principal then uses the
    # remaining allowance. A further cent must be rejected before semantics.
    quota_fourth_id = ""
    consumer_allowance = 1 if consumer_contract_address else 0
    delegated_allowance = 1
    final_allowance = 250 - consumer_allowance - delegated_allowance
    for label, amount in (
        ("quota_match_2", 250),
        ("quota_match_3", 250),
        ("quota_match_4", final_allowance),
    ):
        quota_fourth_id, _ = propose_and_evaluate(label, amount, policy["purpose"])
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
    verifier.checkpoint.data.setdefault("observations", {})["stale_receipt_invalidated"] = {
        "action_id": stale_action_id,
        "policy_version": 3,
        "can_consume_after_update": stale_consumable,
        "observed_at": _now(),
    }
    verifier.checkpoint.save()

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
    verifier.checkpoint.data.setdefault("observations", {})["revocation_readback"] = {
        "action_id": revoked_action_id,
        "decision": revoked_receipt.get("decision"),
        "receipt_digest_valid": revoked_receipt.get("receipt_digest") == hashlib.sha256(
            _canonical({k: v for k, v in revoked_receipt.items() if k != "receipt_digest"})
        ).hexdigest(),
        "observed_at": _now(),
    }
    verifier.checkpoint.save()
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
    policy_instance = int(verifier.read("get_policy_instance", [policy_id]))
    if policy_instance <= 0:
        raise VerificationError("cannot prepare an action for an unknown policy instance")
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
        action_id = derive_action_id(policy_id, signer_address, nonce, action_json, policy_instance)
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


def _triggered_child_id(
    verifier: StudionetVerifier, step: str, parent_tx_id: str
) -> str:
    children: list[Any] = []
    delay = 0.5
    for attempt in range(RETRY_LIMIT):
        try:
            children = verifier.client.get_triggered_transaction_ids(parent_tx_id)
        except Exception as exc:
            if attempt + 1 == RETRY_LIMIT:
                raise RpcFailure(
                    f"could not retrieve child transaction IDs for {step} ({type(exc).__name__})"
                ) from exc
        if children:
            break
        if attempt + 1 < RETRY_LIMIT:
            time.sleep(delay)
            delay = min(delay * 2, 4.0)
    if len(children) != 1:
        raise VerificationError(f"{step} emitted {len(children)} child transactions; expected exactly one")
    child_id = str(children[0])
    verifier.checkpoint.data.setdefault("observations", {}).setdefault(
        "consumer_child_transactions", {}
    )[step] = {"parent_tx_id": parent_tx_id, "child_tx_id": child_id, "observed_at": _now()}
    verifier.checkpoint.save()
    return child_id


def _verify_consumer_composability(
    verifier: StudionetVerifier,
    policy_id: str,
    parent: Any,
    consumer_contract: str,
    policy: dict[str, Any],
    max_polls: int,
) -> None:
    """Exercise a real failing child, bounded retry, completion, and duplicate rejection."""
    policy_instance = int(verifier.read("get_policy_instance", [policy_id]))
    if policy_instance <= 0:
        raise VerificationError("consumer fixture cannot bind to an unknown policy instance")
    consumer_contract = to_checksum_address(consumer_contract)
    verifier.write_once(
        "consumer_fixture.authorize",
        "authorize_consumer",
        [policy_id, consumer_contract],
        signer=parent,
        max_polls=max_polls,
    )
    nonce = int(verifier.checkpoint.data.get("last_action_nonce") or 0) + 1
    action = {
        "action_type": "purchase",
        "amount": 1,
        "unit": policy["unit"],
        "purpose": policy["purpose"],
        "evidence_claim": "Caller asserts test evidence for two-stage consumer flow",
    }
    action_json = json.dumps(action, sort_keys=True, separators=(",", ":"))
    action_hash = hashlib.sha256(_canonical(action)).hexdigest()
    action_id = derive_action_id(policy_id, parent.address, nonce, action_json, policy_instance)
    saved = verifier.checkpoint.data.setdefault("scenarios", {}).get("consumer_fixture_action")
    if saved and (saved.get("action_id") != action_id or saved.get("nonce") != nonce):
        raise VerificationError("consumer fixture action differs from its persisted checkpoint")
    if not saved:
        saved = {"action_id": action_id, "nonce": nonce, "created_at": _now()}
        verifier.checkpoint.data["scenarios"]["consumer_fixture_action"] = saved
        verifier.checkpoint.save()

    action_state = _as_json(verifier.read("get_action", [action_id]))
    if not action_state:
        verifier.write_once(
            "consumer_fixture.submit_action",
            "submit_action",
            [policy_id, nonce, action_json],
            signer=parent,
            max_polls=max_polls,
        )
        action_state = _as_json(verifier.read("get_action", [action_id]))
    if not isinstance(action_state, dict):
        raise VerificationError("consumer fixture proposal did not read back after finality")
    verifier.checkpoint.data["last_action_nonce"] = max(
        int(verifier.checkpoint.data.get("last_action_nonce") or 0), nonce
    )
    verifier.checkpoint.save()
    if action_state.get("state") == "PENDING":
        verifier.write_once(
            "consumer_fixture.evaluate_action",
            "evaluate_action",
            [action_id],
            signer=parent,
            max_polls=max_polls,
        )
    receipt = _as_json(verifier.read("get_receipt", [action_id]))
    if (
        not isinstance(receipt, dict)
        or receipt.get("decision") != "ALLOW"
        or receipt.get("semantic_fit") != "MATCH"
        or receipt.get("action_digest") != action_hash
    ):
        raise VerificationError("consumer fixture source action lacks a finalized semantic ALLOW receipt")
    if verifier.read("can_consume_authorization", [action_id, consumer_contract]) is not True:
        raise VerificationError("consumer contract was not authorized to consume the source receipt")

    request_tx = verifier.write_once(
        "consumer_fixture.request_with_test_child_error",
        "request_protected_operation_with_test_child_error",
        [action_id, action_hash],
        signer=parent,
        max_polls=max_polls,
        contract_address=consumer_contract,
    )
    failed_child_id = _triggered_child_id(verifier, "intentional_child_error", request_tx["tx_id"])
    failed_child = verifier.poll_finalized(failed_child_id, max_polls=max_polls, expected_execution_error=True)
    if failed_child.get("execution_result") != "ERROR":
        raise VerificationError("test child transaction did not finalize with its expected contract error")
    if verifier.read("can_consume_authorization", [action_id, consumer_contract]) is not True:
        raise VerificationError("failed child transaction changed BoundaryOS authorization state")

    retry_tx = verifier.write_once(
        "consumer_fixture.retry_after_finalized_child_error",
        "retry_pending_consumption",
        [action_id],
        signer=parent,
        max_polls=max_polls,
        contract_address=consumer_contract,
    )
    retry_child_id = _triggered_child_id(verifier, "recovered_child", retry_tx["tx_id"])
    if retry_child_id == failed_child_id:
        raise VerificationError("retry unexpectedly reused the prior child transaction ID")
    recovered_child = verifier.poll_finalized(retry_child_id, max_polls=max_polls)
    if recovered_child.get("execution_result") != "SUCCESS":
        raise VerificationError("recovered consume child transaction did not finalize successfully")

    verifier.write_once(
        "consumer_fixture.complete_operation",
        "complete_protected_operation",
        [action_id],
        signer=parent,
        max_polls=max_polls,
        contract_address=consumer_contract,
    )
    if verifier.read("operation_completed", [action_id], contract_address=consumer_contract) is not True:
        raise VerificationError("consumer did not record completion after finalized child consumption")

    verifier.write_once(
        "consumer_fixture.reject_repeated_completion",
        "complete_protected_operation",
        [action_id],
        signer=parent,
        max_polls=max_polls,
        expected_execution_error=True,
        contract_address=consumer_contract,
    )
    if verifier.read("operation_completed", [action_id], contract_address=consumer_contract) is not True:
        raise VerificationError("repeated completion changed or removed the completed operation")
    verifier.checkpoint.data.setdefault("observations", {})["consumer_fixture_composability"] = {
        "consumer_contract": consumer_contract,
        "action_id": action_id,
        "initial_child_tx_id": failed_child_id,
        "initial_child_status": failed_child.get("status"),
        "initial_child_execution_result": failed_child.get("execution_result"),
        "recovery_child_tx_id": retry_child_id,
        "recovery_child_execution_result": recovered_child.get("execution_result"),
        "completion_readback": True,
        "repeated_completion_rejected": True,
        "observed_at": _now(),
    }
    verifier.checkpoint.save()


def _verify_delegation_boundary(
    verifier: StudionetVerifier,
    policy_id: str,
    parent: Any,
    accounts: list[Any],
    policy: dict[str, Any],
    max_polls: int,
    child_contract_address: str | None = None,
) -> None:
    """Prove a widening request fails, then run delegated authorization end to end."""
    policy_instance = int(verifier.read("get_policy_instance", [policy_id]))
    if policy_instance <= 0:
        raise VerificationError("delegation test cannot bind to an unknown policy instance")
    child = None
    if child_contract_address:
        child_address = to_checksum_address(child_contract_address)
    else:
        for candidate in accounts:
            if candidate.address.lower() == parent.address.lower():
                continue
            state = _as_json(verifier.read("get_agent", [candidate.address]))
            if isinstance(state, dict) and not state.get("registered"):
                child = candidate
                break
        if child is None:
            raise VerificationError("no configured, unregistered secondary signer is available for delegation testing")
        child_address = child.address
    child_state = _as_json(verifier.read("get_agent", [child_address]))
    if not child_state.get("registered"):
        verifier.write_once(
            "delegation.approve_child_registration",
            "approve_agent_registration",
            [child_address],
            max_polls=max_polls,
            signer=parent,
        )
        if child is None:
            register_tx = verifier.write_once(
                "delegation.register_child",
                "register_as_agent",
                [parent.address],
                signer=parent,
                max_polls=max_polls,
                contract_address=child_address,
            )
            registration_child_id = _triggered_child_id(
                verifier, "delegation.register_child", register_tx["tx_id"]
            )
            registration_child = verifier.poll_finalized(
                registration_child_id, max_polls=max_polls
            )
            if registration_child.get("execution_result") != "SUCCESS":
                raise VerificationError("consumer contract's agent registration child did not succeed")
        else:
            verifier.write_once(
                "delegation.register_child",
                "register_agent",
                [parent.address],
                signer=child,
                max_polls=max_polls,
            )
        child_state = _as_json(verifier.read("get_agent", [child_address]))
    if child_state.get("policy_id") not in (None, "", policy_id):
        raise VerificationError("delegated child is already assigned to a different policy")
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
    delegation_state = _as_json(verifier.read("get_delegation", [child_address]))
    delegation_is_current = (
        isinstance(delegation_state, dict)
        and delegation_state.get("revoked") is not True
        and delegation_state.get("parent", "").lower() == parent.address.lower()
        and int(delegation_state.get("expires_at", 0)) > now
    )
    if not delegation_is_current:
        verifier.write_once(
            "delegation.reject_amount_widening",
            "delegate_authority",
            [policy_id, parent.address, child_address, scope_json, expires_at],
            max_polls=max_polls,
            expected_execution_error=True,
        )
        child_after = _as_json(verifier.read("get_agent", [child_address]))
        if child_after.get("policy_id"):
            raise VerificationError("rejected amount-widening delegation unexpectedly assigned a child policy")
        verifier.checkpoint.data["observations"]["delegation_boundary"] = {
            "child_address": child_address,
            "requested_amount": widened_scope["max_amount"],
            "parent_limit": policy["max_amount"],
            "execution_rejected": True,
            "observed_at": _now(),
        }

    scope_cap = min(int(policy["max_amount"]), 100)
    scope_expires_at = now + 3600
    child_scope = {
        "action_types": ["purchase"],
        "max_amount": scope_cap,
        "valid_from": 0,
        "valid_until": scope_expires_at,
        "purpose": policy["purpose"],
    }
    child_scope_json = json.dumps(child_scope, sort_keys=True, separators=(",", ":"))
    delegation_state = _as_json(verifier.read("get_delegation", [child_address]))
    if not isinstance(delegation_state, dict) or delegation_state.get("parent", "").lower() != parent.address.lower():
        verifier.write_once(
            "delegation.accept_bounded_child",
            "delegate_authority",
            [policy_id, parent.address, child_address, child_scope_json, scope_expires_at],
            max_polls=max_polls,
            signer=parent,
        )
        delegation_state = _as_json(verifier.read("get_delegation", [child_address]))
    if (
        not isinstance(delegation_state, dict)
        or delegation_state.get("revoked") is True
        or int(delegation_state.get("scope", {}).get("max_amount", 0)) != scope_cap
    ):
        raise VerificationError("bounded child delegation did not read back at finalized state")

    verifier.write_once(
        "delegation.authorize_child_consumer",
        "authorize_consumer",
        [policy_id, child_address],
        max_polls=max_polls,
        signer=parent,
    )
    child_action = {
        "action_type": "purchase",
        "amount": 1,
        "unit": policy["unit"],
        "purpose": policy["purpose"],
        "evidence_claim": "Caller asserts test evidence for delegated child lifecycle",
    }
    child_action_json = json.dumps(child_action, sort_keys=True, separators=(",", ":"))
    child_action_digest = hashlib.sha256(child_action_json.encode("utf-8")).hexdigest()
    child_action_id = derive_action_id(
        policy_id, child_address, 1, child_action_json, policy_instance
    )
    child_record = verifier.checkpoint.data.setdefault("scenarios", {}).get("delegation_child_lifecycle")
    if child_record and (
        child_record.get("action_id") != child_action_id
        or child_record.get("action_json_sha256") != child_action_digest
    ):
        raise VerificationError("delegated child lifecycle differs from its saved checkpoint")
    if not child_record:
        child_record = {
            "nonce": 1,
            "action_id": child_action_id,
            "action_json_sha256": child_action_digest,
            "created_at": _now(),
        }
        verifier.checkpoint.data["scenarios"]["delegation_child_lifecycle"] = child_record
        verifier.checkpoint.save()
    child_action_state = _as_json(verifier.read("get_action", [child_action_id]))
    if not child_action_state:
        if child is None:
            child_submit_tx = verifier.write_once(
                "delegation.child_submit",
                "submit_delegated_action",
                [policy_id, 1, child_action_id, child_action_json],
                signer=parent,
                max_polls=max_polls,
                contract_address=child_address,
            )
            submit_child_id = _triggered_child_id(
                verifier, "delegation.child_submit", child_submit_tx["tx_id"]
            )
            submit_child = verifier.poll_finalized(submit_child_id, max_polls=max_polls)
            if submit_child.get("execution_result") != "SUCCESS":
                raise VerificationError("delegated consumer child action submission did not succeed")
        else:
            verifier.write_once(
                "delegation.child_submit",
                "submit_action",
                [policy_id, 1, child_action_json],
                signer=child,
                max_polls=max_polls,
            )
        child_action_state = _as_json(verifier.read("get_action", [child_action_id]))
    if not isinstance(child_action_state, dict):
        raise VerificationError("delegated child action was not present at finalized state")
    if child_action_state.get("state") == "PENDING":
        if child is None:
            evaluate_tx = verifier.write_once(
                "delegation.child_evaluate",
                "evaluate_delegated_action",
                [child_action_id],
                signer=parent,
                max_polls=max_polls,
                contract_address=child_address,
            )
            evaluate_child_id = _triggered_child_id(
                verifier, "delegation.child_evaluate", evaluate_tx["tx_id"]
            )
            evaluate_child = verifier.poll_finalized(evaluate_child_id, max_polls=max_polls)
            if evaluate_child.get("execution_result") != "SUCCESS":
                raise VerificationError("delegated consumer child evaluation did not succeed")
        else:
            verifier.write_once(
                "delegation.child_evaluate",
                "evaluate_action",
                [child_action_id],
                signer=child,
                max_polls=max_polls,
            )
    child_receipt = _as_json(verifier.read("get_receipt", [child_action_id]))
    if (
        not isinstance(child_receipt, dict)
        or child_receipt.get("decision") != "ALLOW"
        or child_receipt.get("semantic_fit") != "MATCH"
        or child_receipt.get("action_digest") != hashlib.sha256(_canonical(child_action)).hexdigest()
    ):
        raise VerificationError("delegated child did not receive a matching finalized ALLOW receipt")
    if verifier.read("can_consume_authorization", [child_action_id, child_address]) is not True:
        raise VerificationError("delegated child receipt was not consumable before the consume transaction")
    if child is None:
        consume_parent_tx = verifier.write_once(
            "delegation.child_consume",
            "request_protected_operation",
            [child_action_id, child_receipt["action_digest"]],
            signer=parent,
            max_polls=max_polls,
            contract_address=child_address,
        )
        consume_child_id = _triggered_child_id(
            verifier, "delegation.child_consume", consume_parent_tx["tx_id"]
        )
        consume_child = verifier.poll_finalized(consume_child_id, max_polls=max_polls)
        if consume_child.get("execution_result") != "SUCCESS":
            raise VerificationError("delegated consumer receipt-consumption child did not succeed")
        verifier.write_once(
            "delegation.child_complete",
            "complete_protected_operation",
            [child_action_id],
            signer=parent,
            max_polls=max_polls,
            contract_address=child_address,
        )
    else:
        verifier.write_once(
            "delegation.child_consume",
            "consume_authorization",
            [child_action_id, child_receipt["action_digest"]],
            signer=child,
            max_polls=max_polls,
        )
    consumed_child_receipt = _as_json(verifier.read("get_receipt", [child_action_id]))
    if (
        not isinstance(consumed_child_receipt, dict)
        or consumed_child_receipt.get("consumed") is not True
        or consumed_child_receipt.get("consumed_by", "").lower() != child_address.lower()
        or consumed_child_receipt.get("receipt_digest")
        != hashlib.sha256(
            _canonical({key: value for key, value in consumed_child_receipt.items() if key != "receipt_digest"})
        ).hexdigest()
        or verifier.read("can_consume_authorization", [child_action_id, child_address]) is not False
    ):
        raise VerificationError("delegated child consumption did not read back as finalized and one-time")
    if child is None and verifier.read("operation_completed", [child_action_id], contract_address=child_address) is not True:
        raise VerificationError("delegated consumer did not complete after finalized receipt consumption")
    verifier.checkpoint.data["observations"]["delegation_happy_path"] = {
        "child_address": child_address,
        "child_type": "test_consumer_contract" if child is None else "eoa",
        "action_id": child_action_id,
        "decision": child_receipt.get("decision"),
        "semantic_fit": child_receipt.get("semantic_fit"),
        "receipt_consumed": consumed_child_receipt.get("consumed"),
        "receipt_digest_valid_after_consumption": True,
        "observed_at": _now(),
    }
    verifier.checkpoint.save()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except VerificationError as exc:
        print(json.dumps({"event": "verification_blocked", "classification": type(exc).__name__, "detail": str(exc)}), file=sys.stderr, flush=True)
        raise SystemExit(2)
