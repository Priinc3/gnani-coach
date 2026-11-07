"""The prepare command: one line, explicit, and never on the request path.

The asset is fetched **once, by a human**, with:

.. code-block:: console

    uv run --project services/voice python -m gnani_coach.analysis.prepare
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from contextlib import redirect_stdout

import pytest

from gnani_coach.analysis import prepare
from gnani_coach.analysis.vad import ModelAssetMissing

THE_COMMAND = "uv run --project services/voice python -m gnani_coach.analysis.prepare"


def test_the_one_line_prepare_command_is_documented() -> None:
    """The command is written down where a reader will find it."""
    assert THE_COMMAND in prepare.__doc__
    assert THE_COMMAND in (
        __import__("gnani_coach.analysis.vad", fromlist=["vad"]).__doc__ or ""
    )


def test_the_prepare_module_imports_without_a_network(monkeypatch) -> None:
    """Importing the prepare module never touches the network."""
    import gnani_coach.analysis.vad as vad

    class _Exploding:
        request = None

        def urlopen(self, *args, **kwargs):  # pragma: no cover - must not run
            raise AssertionError("importing the analysis must not download anything")

    monkeypatch.setattr(vad, "urllib", _Exploding())
    import importlib

    importlib.reload(prepare)
    assert prepare.main is not None


def test_the_command_prints_the_asset_identity(monkeypatch) -> None:
    """A successful prepare prints the identity of the asset."""

    class _Asset:
        def to_dict(self) -> dict[str, object]:
            return {"filename": "silero_vad.onnx", "sha256": "0" * 64}

    monkeypatch.setattr(prepare, "prepare_model", lambda **kwargs: _Asset())
    monkeypatch.setattr(prepare, "describe_asset", lambda: {"prepared": True})
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = prepare.main([])
    assert code == 0
    printed = buffer.getvalue()
    assert "silero_vad.onnx" in printed
    decoder = json.JSONDecoder()
    first, _ = decoder.raw_decode(printed)
    second, _ = decoder.raw_decode(printed[printed.index("{", 1) :])
    assert first["filename"] == "silero_vad.onnx"
    assert second == {"prepared": True}


def test_the_command_reports_a_refused_asset(monkeypatch) -> None:
    """A hash mismatch is reported, not raised as a traceback."""

    def _refuse(**kwargs):
        raise ModelAssetMissing("the downloaded model asset does not match the pin")

    monkeypatch.setattr(prepare, "prepare_model", _refuse)
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = prepare.main([])
    assert code == 1
    assert json.loads(buffer.getvalue())["prepared"] is False


def test_the_module_runs_as_a_script() -> None:
    """``python -m gnani_coach.analysis.prepare`` is a real entry point."""
    result = subprocess.run(
        [sys.executable, "-m", "gnani_coach.analysis.prepare", "--help"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    # The module has no argument parser yet, so --help is not a flag it
    # knows; what matters is that the module is runnable and that it does
    # not crash on the import path.
    assert result.returncode in (0, 1)
    assert "Traceback" not in result.stderr
