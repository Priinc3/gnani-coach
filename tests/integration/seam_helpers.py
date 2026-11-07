"""Helpers for the integration smoke test.

Kept out of ``conftest.py`` so the test module can import them without
reaching into pytest's own fixture machinery.
"""

from __future__ import annotations

from typing import Any

#: The frozen error code a not-yet-implemented seam answers with.
NOT_AVAILABLE_CODE = "not_available"


def assert_error_shape(
    document: dict[str, Any],
    *,
    code: str = NOT_AVAILABLE_CODE,
    category: str = "not_available",
    retryable: bool = False,
) -> None:
    """Assert the document is the frozen error shape.

    The fields are asserted, not merely the presence of a shape: a caller
    names the code, category and retryable flag it expects, so a wrong
    answer cannot pass because it happens to be JSON.
    """
    assert document["errorVersion"] == "0.1"
    assert document["code"] == code
    assert document["category"] == category
    assert document["retryable"] is retryable
    assert 1 <= len(document["message"]) <= 300
    assert document["correlationId"].startswith("cor_")
    assert document["occurredAt"].endswith("Z")
