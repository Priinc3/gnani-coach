"""Prepare the Silero VAD model asset.

The asset is downloaded **once, explicitly**, by a human. Nothing in the
request path ever downloads anything: when the asset is absent, the
analysis reports ``speech_analysis_unavailable`` and every
VAD-dependent observation is ``unavailable`` with a null value.

One-line prepare command
------------------------

.. code-block:: console

    uv run --project services/voice python -m gnani_coach.analysis.prepare

The asset lands in ``gnani_coach/analysis/.cache/models/``, which is
git-ignored. The downloaded file is checked against the pinned sha256 and
is deleted rather than used when it does not match.
"""

from __future__ import annotations

import json
import sys

from gnani_coach.analysis.vad import (
    ModelAssetMissing,
    describe_asset,
    prepare_model,
)


def main(argv: list[str] | None = None) -> int:
    """Prepare the asset and print a content-free description."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    force = "--force" in arguments
    try:
        asset = prepare_model(force=force)
    except ModelAssetMissing as exc:
        print(json.dumps({"prepared": False, "reason": str(exc)}, indent=2))
        return 1
    print(json.dumps(asset.to_dict(), indent=2))
    print(json.dumps(describe_asset(), indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - the CLI entry point
    raise SystemExit(main())
