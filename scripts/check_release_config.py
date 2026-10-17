"""Fail-closed consistency checks for BoundaryOS release configuration."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    pins = {line.split("==", 1)[0]: line.split("==", 1)[1] for line in requirements if "==" in line}
    expected = {
        "genlayer-test": "0.29.2",
        "genlayer-py": "0.16.3",
        "genvm-linter": "0.11.0",
    }
    for package, version in expected.items():
        if pins.get(package) != version:
            raise SystemExit(f"requirements.txt must pin {package}=={version}")

    config = yaml.safe_load((ROOT / "gltest.config.yaml").read_text(encoding="utf-8"))
    if config.get("networks", {}).get("default") != "studionet":
        raise SystemExit("default GenLayer network must be studionet")
    if config.get("networks", {}).get("studionet", {}).get("url") != "https://studio.genlayer.com/api":
        raise SystemExit("Studionet RPC must be https://studio.genlayer.com/api")

    harness = ast.parse((ROOT / "tests/integration/studionet_resume.py").read_text(encoding="utf-8"))
    constants = {}
    for node in harness.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                constants[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                pass
    if constants.get("CHAIN_ID") != 61999 or constants.get("RPC_URL") != "https://studio.genlayer.com/api":
        raise SystemExit("harness chain/RPC constants do not match Studionet 61999")

    # Historical deployment evidence must remain bound to its frozen source,
    # even after a correction makes the current tree intentionally differ.
    evidence = json.loads((ROOT / "docs/evidence/studionet-canonical-release.json").read_text(encoding="utf-8"))
    source_identity = evidence.get("source_identity", {})
    frozen_commit = source_identity.get("source_commit")
    source_path = source_identity.get("contract_path")
    if not isinstance(frozen_commit, str) or not isinstance(source_path, str):
        raise SystemExit("canonical evidence is missing its frozen source identity")
    frozen_source = __import__("subprocess").check_output(
        ["git", "show", f"{frozen_commit}:{source_path}"], cwd=ROOT
    )
    import hashlib

    frozen_hash = hashlib.sha256(frozen_source).hexdigest()
    if frozen_hash != source_identity.get("committed_file_sha256"):
        raise SystemExit("historical canonical deployment hash no longer matches its frozen commit")

    release_path = ROOT / "docs/evidence/studionet-accessible-signer-release.json"
    if release_path.is_file():
        release = json.loads(release_path.read_text(encoding="utf-8"))
        release_source = release.get("source_identity", {})
        release_commit = release_source.get("source_commit")
        release_contract_path = release_source.get("source_path")
        if not isinstance(release_commit, str) or not isinstance(release_contract_path, str):
            raise SystemExit("current Studionet release evidence is missing its frozen source identity")
        release_source_bytes = __import__("subprocess").check_output(
            ["git", "show", f"{release_commit}:{release_contract_path}"], cwd=ROOT
        )
        release_hash = hashlib.sha256(release_source_bytes).hexdigest()
        if release_source.get("sha256") != release_hash:
            raise SystemExit("current Studionet release evidence does not match its frozen Git source")
        deployment = release.get("deployment", {})
        if deployment.get("status") != "FINALIZED" or deployment.get("execution") != "SUCCESS":
            raise SystemExit("current Studionet release deployment is not recorded as finalized successfully")
        transactions = release.get("verification", {}).get("transactions", {})
        if not transactions or any(item.get("status") != "FINALIZED" for item in transactions.values()):
            raise SystemExit("current Studionet release evidence has missing or non-finalized transaction records")
    print("release configuration and historical source identity are consistent")


if __name__ == "__main__":
    main()
