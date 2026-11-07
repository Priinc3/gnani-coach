"""The browser-visible voice service URL — the one ``NEXT_PUBLIC_`` value.

Phase 03 FIX-1. The rule is small and absolute: the browser may know
**where** the voice service is, and nothing else. A ``NEXT_PUBLIC_``
variable is inlined into the JavaScript bundle, so a secret behind that
prefix would be readable by anyone who opens the page.

The checks below are static checks on the frozen files, because the value
is inlined at build time and cannot be read out of a running bundle here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

#: The one browser-visible variable in this repository.
VOICE_WS_URL_VARIABLE = "NEXT_PUBLIC_VOICE_WS_URL"

#: The development default: the voice service on the developer machine.
VOICE_WS_URL_DEFAULT = "ws://localhost:8000/ws/call"

#: The parts of a variable name that would mean a secret.
SECRET_WORDS = ("KEY", "SECRET", "TOKEN", "PASSWORD", "CREDENTIAL", "PRIVATE")

#: Every ``.env.example`` in the repository.
ENV_EXAMPLES = (
    Path(".env.example"),
    Path("apps/web/.env.example"),
    Path("services/voice/.env.example"),
)

#: The web app's example — the browser-visible variables live here.
WEB_ENV_EXAMPLE = Path("apps/web/.env.example")

#: The service's example — server-side values only.
SERVICE_ENV_EXAMPLE = Path("services/voice/.env.example")


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "packages" / "contracts" / "schemas").is_dir():
            return candidate
    raise RuntimeError("repository root not found")


def public_variables(text: str) -> set[str]:
    """The ``NEXT_PUBLIC_`` variable names mentioned in a text."""
    return set(re.findall(r"\bNEXT_PUBLIC_[A-Z0-9_]+\b", text))


def test_the_voice_url_module_exists_and_is_frozen() -> None:
    module = repo_root() / "apps" / "web" / "src" / "lib" / "voice.ts"
    assert module.is_file(), "the frozen voice-url module is missing"
    source = module.read_text(encoding="utf-8")
    assert VOICE_WS_URL_VARIABLE in source
    assert VOICE_WS_URL_DEFAULT in source
    assert "export const VOICE_WS_URL" in source


def test_the_development_default_is_the_local_voice_service() -> None:
    """The dev default is the documented ``ws://localhost:<port>/ws/call``."""
    assert VOICE_WS_URL_DEFAULT == "ws://localhost:8000/ws/call"
    assert VOICE_WS_URL_DEFAULT.endswith("/ws/call")


@pytest.mark.parametrize("relative", (Path(".env.example"), WEB_ENV_EXAMPLE))
def test_the_env_examples_document_the_voice_url(relative: Path) -> None:
    path = repo_root() / relative
    assert path.is_file(), path
    assert VOICE_WS_URL_VARIABLE in path.read_text(encoding="utf-8")


def test_the_service_env_example_has_no_public_variable() -> None:
    """The service is server-side: a ``NEXT_PUBLIC_`` value has no place there."""
    text = (repo_root() / SERVICE_ENV_EXAMPLE).read_text(encoding="utf-8")
    assert public_variables(text) == set()


def test_the_voice_url_is_the_only_public_variable() -> None:
    """No other ``NEXT_PUBLIC_`` value exists in this repository."""
    found: dict[str, set[str]] = {}
    for relative in ENV_EXAMPLES:
        text = (repo_root() / relative).read_text(encoding="utf-8")
        found[str(relative)] = public_variables(text)
    every = set().union(*found.values()) if found else set()
    assert every == {VOICE_WS_URL_VARIABLE}, found


def test_no_secret_uses_the_public_prefix() -> None:
    """A ``NEXT_PUBLIC_`` name that looks like a secret is a defect."""
    for relative in ENV_EXAMPLES:
        text = (repo_root() / relative).read_text(encoding="utf-8")
        for name in public_variables(text):
            assert not any(word in name for word in SECRET_WORDS), (relative, name)


def test_the_web_app_reads_no_other_environment_variable() -> None:
    """The browser-visible surface stays one variable wide."""
    source_root = repo_root() / "apps" / "web" / "src"
    found: set[str] = set()
    for path in sorted(source_root.rglob("*.ts")):
        if path.name.endswith(".d.ts"):
            continue
        found |= public_variables(path.read_text(encoding="utf-8"))
    assert found == {VOICE_WS_URL_VARIABLE}, found
