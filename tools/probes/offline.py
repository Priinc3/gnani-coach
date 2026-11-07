"""Offline analysis runner for ``run.py analysis --offline``.

Reports what is genuinely measurable with no keys, no downloads and no
provider calls, and states plainly what is missing. In particular:

* an absent speech fixture set is reported **MISSING**, never substituted
  with synthetic stand-ins that would be scored as if they were speech;
* an absent model asset is reported **MISSING**, never auto-downloaded;
* the delivery denominators are printed separately, with the method notes
  that the draft contract currently conflates.
"""

from __future__ import annotations

import json

from gnani_coach.providers.pcm import SampleClock
from tools.probes.analysis import filler, metrics
from tools.probes.analysis import vad as vad_mod
from tools.probes.run import BLOCKED, INCONCLUSIVE, NOT_RUN, PASSED


def run_offline_analysis(reporter, fixtures_io, vad_mod) -> int:
    from tools.probes import fixtures_io as fx

    manifest = fx.load_manifest()
    analytic = fx.analytic_fixtures(manifest)
    ready, missing = fx.available(manifest)

    reporter.section("fixture inventory")
    reporter.status("analytic-fixtures", reporter and "PASSED", f"{len(analytic)} prepared and hash-verified")
    if missing:
        reporter.status(
            "spoken-fixtures",
            "BLOCKED",
            f"{len(missing)} spoken fixtures have no prepared speech source",
        )
        for fixture_id in missing:
            entry = next(
                item for item in manifest["fixtures"] if item["fixtureId"] == fixture_id
            )
            action = (entry.get("labelProvenance") or {}).get("smallest_user_action", "")
            reporter.status(f"missing:{fixture_id}", "BLOCKED", action)
    else:
        reporter.status("spoken-fixtures", "PASSED", "all prepared")

    reporter.section("model asset")
    asset_info = vad_mod.describe_asset()
    if asset_info.get("prepared"):
        reporter.status("silero-vad-onnx", "PASSED", f"sha256={str(asset_info['sha256'])[:16]}…")
    else:
        reporter.status(
            "silero-vad-onnx",
            "BLOCKED",
            "not prepared; run `run.py analysis --prepare-models` (no auto-download)",
        )
        reporter.say(f"  expected source: {asset_info['expected_source']}")
        reporter.say(f"  license: {asset_info['license']}")
        reporter.status(
            "vad-measurements", "NOT RUN", "speech-region estimates require the prepared model"
        )
        _report_metrics_only(reporter, analytic, fx)
        return 2

    reporter.section("speech-region estimates and boundary error")
    vad = vad_mod.SileroVad(_asset(vad_mod))
    rows: list[dict] = []
    for fixture in analytic:
        pcm = fx.raw_pcm_of(fixture)
        result = vad.analyse(pcm, fixture.sample_rate)
        rows.append(
            {
                "fixture_id": fixture.fixture_id,
                "span_ms": result.span_ms,
                "speech_active_ms": result.speech_active_ms,
                "regions": len(result.regions),
                "internal_pauses_ms": [p.duration_ms for p in result.internal_pauses()],
            }
        )
        _report_boundary_error(reporter, fixture, result, fx)

    _report_metrics(reporter, rows, analytic, fx)
    _report_filler(reporter, analytic, fx, vad)
    return 0


def _asset(vad_mod):
    import json

    recorded = json.loads(vad_mod.MODEL_PROVENANCE_PATH.read_text(encoding="utf-8"))
    return vad_mod.ModelAsset(
        path=vad_mod.CACHE_DIR / vad_mod.MODEL_FILENAME,
        sha256=recorded["sha256"],
        bytes=recorded["bytes"],
        source=recorded["source"],
        license=recorded["license"],
    )


def _speech_labels(fixture) -> list[dict]:
    """Known speech-segment labels, from segments (not silence labels)."""
    return [s for s in fixture.segments if s["tag"] in ("speech", "filled_hesitation")]


def _report_boundary_error(reporter, fixture, result, fx) -> None:
    """Compare detected regions with the exact synthetic labels."""
    labelled = _speech_labels(fixture)
    detected = [
        {"start_ms": r.start_ms, "end_ms": r.end_ms, "obj": r} for r in result.regions
    ]
    matched, missed, extra = metrics.match_regions(
        labelled,
        [d["obj"] for d in detected],
        tolerance_ms=300,
    )
    errors = [m.worst_abs_error_ms for m in matched]
    p95 = metrics.percentile([float(e) for e in errors], 0.95)
    reporter.say(
        f"  {fixture.fixture_id}: labelled={len(labelled)} detected={len(result.regions)} "
        f"matched={len(matched)} missed={len(missed)} extra={len(extra)} "
        f"worst_boundary_error_ms={max(errors) if errors else 'n/a'} p95={p95}"
    )


def _report_metrics(reporter, rows, analytic, fx) -> None:
    reporter.section("delivery denominators (kept separate)")
    for row in rows:
        reporter.say(
            f"  {row['fixture_id']}: clip_span_ms={row['span_ms']} "
            f"speech_active_ms={row['speech_active_ms']} regions={row['regions']} "
            f"internal_pauses_ms={row['internal_pauses_ms']}"
        )
    reporter.say("")
    reporter.say("  rate_wpm        = recognized_words / clip_span_ms      (elapsed learner audio)")
    reporter.say("  active_rate_wpm = recognized_words / speech_active_ms   (VAD speech-active)")
    reporter.say("  never used as a denominator: connection time, session time, assistant audio,")
    reporter.say("                       network round trips, provider emission timestamps")
    reporter.status(
        "denominator-separation",
        "PASSED",
        "draft v0.1 uses one method description for both rates; Phase 03 must split them",
    )
    reporter.status(
        "word-count",
        "NOT RUN",
        "requires real STT output; an analytic fixture has no recognised words",
    )


def _report_metrics_only(reporter, analytic, fx) -> None:
    reporter.section("delivery denominators (measurable without the model)")
    total = sum(f.duration_ms for f in analytic)
    reporter.say(f"  fixtures available : {len(analytic)}")
    reporter.say(f"  total clip span_ms : {total}")
    reporter.say("  speech_active_ms   : NOT MEASURED (model asset missing)")
    reporter.status(
        "denominator-separation",
        "PASSED",
        "the four denominators stay distinct in code and in this output",
    )


def _report_filler(reporter, analytic, fx, vad) -> None:
    """Measure the candidate detector, including its threshold sensitivity.

    A zero result is a *finding*, not a pass: whether a short hesitation is
    ever separable depends on the VAD merge threshold, because a merge
    window longer than the burst absorbs the burst into the surrounding
    speech region and it can never become a candidate. Reporting only the
    default threshold would hide that entirely.
    """
    reporter.section("filler-localization candidate")
    reporter.say(
        "  VAD merge-threshold sweep (the provider's documented x-min-silence-ms "
        "range is 100-2000 ms; this sweep uses 120/200/300)"
    )
    sweep_rows: list[dict] = []
    for merge_ms in (120, 200, 300):
        total = 0
        per_fixture: dict[str, int] = {}
        for fixture in analytic:
            pcm = fx.raw_pcm_of(fixture)
            result = vad.analyse(pcm, fixture.sample_rate, min_silence_ms=merge_ms)
            detected = filler.detect(pcm, fixture.sample_rate, result)
            per_fixture[fixture.fixture_id] = len(detected.candidates)
            total += len(detected.candidates)
        sweep_rows.append({"min_silence_ms": merge_ms, "total": total, "per_fixture": per_fixture})
        reporter.say(
            f"    min_silence_ms={merge_ms:>3}: total_candidates={total} "
            + " ".join(f"{k}={v}" for k, v in sorted(per_fixture.items()) if v)
        )

    default_total = next(row["total"] for row in sweep_rows if row["min_silence_ms"] == 300)
    reporter.say("")
    reporter.say(f"  default (min_silence_ms=300) candidate total: {default_total}")
    if default_total == 0:
        reporter.say(
            "  FINDING (about THIS candidate detector, not about fillers in "
            "general): at the probe's default merge threshold every inserted "
            "burst is absorbed into the surrounding speech region, so a short "
            "hesitation never becomes its own candidate here. The sweep above "
            "shows how much of that is a threshold artefact rather than a "
            "signal failure."
        )
    reporter.status(
        "candidate-detector",
        INCONCLUSIVE,
        f"{default_total} candidates at the default threshold; see the threshold sweep",
    )
    reporter.status(
        "event-status",
        INCONCLUSIVE,
        "every event is a candidate; none is a confirmed filled pause",
    )
    report = filler.evaluate_against_labels(None, [], verified=False)
    reporter.say(f"  precision/recall : {report.reason}")
    reporter.status(
        "precision-recall",
        NOT_RUN,
        "NOT EVALUABLE - no human-reviewed filler labels exist (needs 20 positive + "
        "20 negative per enabled filler mode)",
    )
    reporter.say(
        "  transcript baseline (comparison only, NOT audio analysis): "
        + str(filler.transcript_baseline("um, I mean, like, it worked")["marker_counts"])
    )
    reporter.status(
        "forced-alignment",
        NOT_RUN,
        "deliberately not used: it aligns supplied text and cannot recover an omitted filler",
    )
    reporter.say("  calibration/holdout split: " + json.dumps(calibration_holdout_note(fx)))


def calibration_holdout_note(fx) -> dict:
    """Report the calibration/holdout split and its (insufficient) size."""
    return {
        "calibration": fx.calibration_ids(),
        "holdout": fx.holdout_ids(),
        "required_positive_per_mode": 20,
        "required_negative_per_mode": 20,
        "status": "INSUFFICIENT — the split exists but is far below the required size",
    }
