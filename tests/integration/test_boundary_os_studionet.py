"""Read-only by default: reconcile the existing disposable Studionet instance.

Set BOUNDARYOS_RUN_LIVE_SUITE=1 to explicitly run the resumable diagnostic
suite. The suite never deploys and stores transaction checkpoints outside the
pytest artifacts directory so later pytest sessions do not erase them.
"""

import os

from studionet_resume import DEFAULT_CONTRACT, TransportFailure, VerificationError, main


def test_resume_or_inspect_existing_studionet_instance():
    args = ["--contract", DEFAULT_CONTRACT, "--inspect-existing"]
    if os.environ.get("BOUNDARYOS_RUN_LIVE_SUITE") == "1":
        args.append("--run-live-suite")
    try:
        assert main(args) == 0
    except TransportFailure as exc:
        import pytest

        pytest.skip(f"Studionet RPC transport blocked after bounded retries: {exc}")
    except VerificationError as exc:
        if os.environ.get("BOUNDARYOS_RUN_LIVE_SUITE") == "1" and "stable local signers" in str(exc):
            import pytest

            pytest.skip(f"live writes require stable local signer configuration: {exc}")
        raise
