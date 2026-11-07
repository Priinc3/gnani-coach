"""Redaction policy for provider diagnostics.

The default operational log must be **content-free**: no API keys, no
``x-api-key-id`` header values, no raw exception dumps, no learner or
model prose, no audio bytes.

This module is the single place that decides what a diagnostic string is
allowed to contain. Adapters and the probe CLI route every operator-visible
string through :func:`redact` before printing.

Two separate channels exist, per BUILD.md:

* **Default logs** — content-free. Counters, byte totals, durations,
  status categories, model/voice identifiers, hashes.
* **Synthetic payload captures** — separate directory, opt-in, and only
  ever containing synthetic fixture material. They are never interleaved
  into the default stream.

A redaction failure is always visible: :func:`redact` substitutes a marker
rather than passing a suspicious value through.
"""

from __future__ import annotations

import re
from typing import Final

REDACTED: Final[str] = "[REDACTED]"

# Credential-bearing environment variable names. Matched on the *name* so a
# value can never be printed by echoing a config dump.
_SECRET_NAME_RE: Final = re.compile(
    r"(?i)\b(gnani_api_key|gemini_api_key|supabase_service_role_key|"
    r"api[_-]?key|apikey|authorization|bearer|x-api-key-id|"
    r"x-goog-api-key|secret|token|password)\b"
)

# Long opaque strings are treated as credential-shaped even without a label.
_OPAQUE_RE: Final = re.compile(r"\b[A-Za-z0-9_\-]{32,}\b")

# A credential *assignment*: NAME := value. The whole pair is replaced, so
# the value cannot survive just because only the label was rewritten.
_ASSIGNMENT_RE: Final = re.compile(
    r"(?i)\b(gnani_api_key|gemini_api_key|supabase_service_role_key|"
    r"api[_-]?key|apikey|authorization|bearer|x-api-key-id|"
    r"x-goog-api-key|secret|token|password)\b(\s*[:=]{1,2}\s*)(\S+)"
)

# A bare credential label with no assignment (a header name on its own, for
# example) is still marked, so a reader can see the field existed.
_SECRET_NAME_RE: Final = re.compile(
    r"(?i)\b(gnani_api_key|gemini_api_key|supabase_service_role_key|"
    r"api[_-]?key|apikey|authorization|bearer|x-api-key-id|"
    r"x-goog-api-key|secret|token|password)\b"
)


def is_hex_digest(value: str) -> bool:
    """True for an even-length hex string of 32+ chars (a content hash)."""
    if len(value) < 32 or len(value) % 2 != 0:
        return False
    return all(c in "0123456789abcdefABCDEF" for c in value)


def redact(text: str, *, max_length: int = 400) -> str:
    """Return a content-free rendering of ``text``.

    Masks anything that looks like a credential or an opaque secret, then
    truncates. Truncation is a size bound, not privacy: redaction happens
    first, always.
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = repr(type(text).__name__)

    def _mask_match(match: re.Match[str]) -> str:
        value = match.group(0)
        if is_hex_digest(value):
            return value
        return REDACTED

    # Order matters: opaque blobs first, then whole assignments (label and
    # value together), then any bare label that survived.
    masked = _OPAQUE_RE.sub(_mask_match, text)
    masked = _ASSIGNMENT_RE.sub(lambda m: f"{m.group(1)}={REDACTED}", masked)
    masked = _SECRET_NAME_RE.sub(lambda m: f"{m.group(0)}={REDACTED}", masked)

    if len(masked) > max_length:
        masked = masked[:max_length] + f"...[{len(text) - max_length} chars truncated]"
    return masked


#: Credential *shapes*. A value that matches one of these is masked
#: wherever it appears. These are structural, never a real value.
_CREDENTIAL_SHAPE_RE: Final = re.compile(
    r"AIza[0-9A-Za-z\-_]{35}"
    r"|\bgsk_[0-9A-Za-z]{20,}"
    r"|\bnvapi-[0-9A-Za-z\-_]{20,}"
    r"|\bsk-[A-Za-z0-9\-_]{20,}"
    r"|(?i:\bbearer)\s+[0-9A-Za-z\-_\.]{20,}"
    r"|(?i:\bx-api-key-id)\s*[:=]\s*[\"']?[0-9A-Za-z\-_]{12,}"
    r"|\beyJ[0-9A-Za-z\-_]{8,}\.[0-9A-Za-z\-_]{8,}\.[0-9A-Za-z\-_]{8,}"
)

#: A secret-ish name with an assignment. The value is dropped; the name
#: is kept, so a reader can still see that a credential was present.
_EVIDENCE_ASSIGNMENT_RE: Final = re.compile(
    r"(?i)\b(gnani_api_key|gemini_api_key|supabase_service_role_key|"
    r"api[_-]?key|apikey|authorization|x-goog-api-key|"
    r"access[_-]?token|refresh[_-]?token|secret|password|passwd)\b"
    r"(\s*[:=]{1,2}\s*)(\"[^\"]*\"|'[^']*'|\S+)"
)


#: Opaque blobs, excluding a long token that is part of a test node id
#: (immediately preceded by ``::``). A negative lookbehind is used rather
#: than an index check, so the rule cannot be shifted by an earlier
#: substitution in the same string.
_OPAQUE_EVIDENCE_RE: Final = re.compile(r"(?<!::)\b[A-Za-z0-9_\-]{32,}\b")

#: An evidence run id is a **locator**, not a secret: it must stay
#: readable so a report can cite the exact run directory it refers to.
_EVIDENCE_RUN_ID_RE: Final = re.compile(
    r"^\d{8}T\d{6}Z-[A-Za-z0-9\-]+-[0-9a-f]{10}-[0-9a-f]{6}$"
)


def redact_evidence(text: str, *, max_length: int = 4_000_000) -> str:
    """Redact a captured stdout/stderr for storage as evidence.

    This is a **different, less blunt policy** than :func:`redact`, and
    the difference is deliberate.

    ``redact()`` is the *operator-log* policy: it masks any bare
    credential-shaped word and any long opaque token. That is right for a
    log line and wrong for an evidence capture, because a captured test
    run is full of long identifiers — a pytest node id such as
    ``test_the_synthesis_request_is_charged_to_the_budget`` — and masking
    every one of them destroys the very thing the evidence exists to
    show.

    This policy therefore keeps three layers of protection:

    1. every value matching a known **credential shape** is masked;
    2. every **assignment** of a secret-ish name has its value masked;
    3. every **opaque blob** is masked, *except* a long token that is
       part of a test node id (immediately preceded by ``::``), which is
       an identifier, not a secret.

    A captured credential of an unknown shape is still caught by layer 3.
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = repr(type(text).__name__)

    masked = _CREDENTIAL_SHAPE_RE.sub(REDACTED, text)
    masked = _EVIDENCE_ASSIGNMENT_RE.sub(
        lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", masked
    )

    def _mask_opaque(match: re.Match[str]) -> str:
        value = match.group(0)
        if is_hex_digest(value):
            return value
        if _EVIDENCE_RUN_ID_RE.match(value):
            # An evidence run id is a locator, not a secret.
            return value
        return REDACTED

    masked = _OPAQUE_EVIDENCE_RE.sub(_mask_opaque, masked)

    if len(masked) > max_length:
        masked = masked[:max_length] + f"...[{len(text) - max_length} chars truncated]"
    return masked


def describe_headers(headers: dict[str, str]) -> dict[str, str]:
    """Safe rendering of provider headers.

    Credential header *names* are preserved (they are non-secret and are
    what a reviewer needs to see); every value is dropped except the
    documented non-secret negotiation parameters.
    """
    non_secret = {
        "lang_code",
        "x-sample-rate",
        "x-format",
        "x-vad-threshold",
        "x-min-silence-ms",
        "x-min-speech-ms",
        "x-min-segment-ms",
        "x-max-speech-s",
        "x-enable-substitution",
        "itn_native_numerals",
        "content-type",
        # Word boosting is a *recognition setting*, not a credential: the
        # list is a handful of words the caller wants the recogniser to
        # prefer. A probe must be able to record which words and which
        # score it used, and a reviewer must be able to check it.
        "x-bias-list",
        "x-bias-score",
    }
    out: dict[str, str] = {}
    for name, value in headers.items():
        key = name.lower()
        if key in non_secret:
            out[key] = redact(value, max_length=64)
        else:
            out[key] = REDACTED
    return out
