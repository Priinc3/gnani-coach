"""The VAD asset: hash-verified, cached, and never downloaded on request.

The rules:

* the model file is pinned by sha256, and a file that does not match the
  pin is **never used**;
* the cache lives inside the package's tree and is git-ignored;
* a request never downloads anything: with the asset absent the analysis
  reports ``unavailable``, and the download helper is never called;
* the one-line prepare command is the only way to fetch the asset.
"""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
from pathlib import Path

import pytest

from gnani_coach.analysis import service as analysis_service
from gnani_coach.analysis import vad
from gnani_coach.analysis.vad import (
    MODEL_SHA256,
    ModelAssetMissing,
    asset_present,
    cache_dir,
    describe_asset,
    model_path,
    prepare_model,
    provenance_path,
)


class _FakeUrllib:
    """Stands in for the ``urllib`` module, so no test touches the network."""

    def __init__(self, payload: bytes) -> None:
        self.request = self
        self._payload = payload
        self.calls: list[tuple[str, float | None]] = []

    def urlopen(self, url: str, timeout: float | None = None) -> io.BytesIO:
        self.calls.append((url, timeout))
        return io.BytesIO(self._payload)


class _ExplodingUrllib:
    """Any network attempt fails the test."""

    def __init__(self) -> None:
        self.request = self

    def urlopen(self, url: str, timeout: float | None = None) -> io.BytesIO:
        raise AssertionError(f"the request path must not download anything: {url}")


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "packages" / "contracts" / "schemas").is_dir():
            return candidate
    raise RuntimeError("repository root not found")


def test_the_cache_lives_inside_the_package_and_is_git_ignored() -> None:
    """The cache is inside this package's tree, and it is untracked."""
    package = Path(vad.__file__).resolve().parent
    assert cache_dir().is_relative_to(package)
    assert cache_dir().name == "models"
    assert cache_dir().parent.name == ".cache"

    root = _repo_root()
    ignore = (root / ".gitignore").read_text(encoding="utf-8")
    assert ".cache" in ignore, "the model cache must be git-ignored"
    result = subprocess.run(
        ["git", "check-ignore", "-q", str(cache_dir() / "silero_vad.onnx")],
        cwd=root,
        capture_output=True,
    )
    assert result.returncode == 0, "the cache file must be ignored by git"


def test_the_asset_is_verified_by_its_sha256(tmp_path: Path) -> None:
    """A file that does not match the pin is not an asset."""
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(vad, "CACHE_DIR", tmp_path / "models")
        assert not asset_present()
        (tmp_path / "models").mkdir(parents=True, exist_ok=True)
        (tmp_path / "models" / vad.MODEL_FILENAME).write_bytes(b"not the model")
        assert not asset_present(), "a corrupted file is never an asset"
    finally:
        monkeypatch.undo()


def test_an_unverified_download_is_never_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A download whose hash does not match the pin is not written."""
    monkeypatch.setattr(vad, "CACHE_DIR", tmp_path / "models")
    monkeypatch.setattr(vad, "urllib", _FakeUrllib(b"the wrong bytes"))
    with pytest.raises(ModelAssetMissing):
        prepare_model()
    assert not model_path().exists()
    assert not provenance_path().exists()


def test_a_verified_download_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A download that matches the pin is written, with its provenance."""
    if not asset_present():
        pytest.skip("the pinned asset is not prepared in this environment")
    payload = model_path().read_bytes()
    assert hashlib.sha256(payload).hexdigest() == MODEL_SHA256

    monkeypatch.setattr(vad, "CACHE_DIR", tmp_path / "models")
    fake = _FakeUrllib(payload)
    monkeypatch.setattr(vad, "urllib", fake)
    asset = prepare_model()
    assert asset.sha256 == MODEL_SHA256
    assert model_path().is_file()
    provenance = json.loads(provenance_path().read_text(encoding="utf-8"))
    assert provenance["sha256"] == MODEL_SHA256
    assert "silero-vad" in provenance["license"]
    assert fake.calls, "the asset was fetched once, explicitly"


def test_the_request_path_never_downloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the asset absent, the analysis says so and fetches nothing."""
    monkeypatch.setattr(vad, "CACHE_DIR", tmp_path / "models")
    monkeypatch.setattr(vad, "urllib", _ExplodingUrllib())
    monkeypatch.setattr(analysis_service, "model_path", lambda: tmp_path / "missing.onnx")

    engine = analysis_service._VadEngine()  # the real engine
    assert engine.analyse(b"\x00\x00" * 512, 16000) is None
    assert engine.available is False


def test_the_prepared_asset_is_described_without_its_content() -> None:
    """The description carries the identity of the asset, not its bytes."""
    described = describe_asset()
    assert "silero_vad.onnx" in described.get("filename", "") or "silero_vad.onnx" in (
        described.get("expected_source", "")
    )
    assert "MIT" in described["license"]
    if described["prepared"]:
        assert described["sha256"] == MODEL_SHA256
        assert described["runtime"] == "onnxruntime CPU"
    else:
        assert "gnani_coach.analysis.prepare" in described["reason"]
