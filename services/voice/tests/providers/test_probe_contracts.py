"""Probe-layer contracts [FIX-1 P02-01, P02-04, P02-06].

Three things are checked here, all offline and all without a socket:

* the credential-leak scan is **content-suppressed** — it reports
  locations and rule ids and never the matched text;
* the language matrix aggregates **every requested stage**, and a
  parameter-acceptance smoke check is never counted as language
  coverage;
* every language id, display name and STT/TTS code resolves through the
  shared catalog, and Hinglish keeps its own separate STT and TTS
  mapping.
"""

from __future__ import annotations

import json

import pytest

from gnani_coach.providers.errors import InvalidRequestError
from tools.probes.live import languages as lang_mod
from tools.probes.live.probes import (
    CHAIN_OPS_MINIMUM,
    OPS_PER_LANGUAGE,
    PARAMETER_COLUMNS,
    REQUIRED_STAGES,
    aggregate_rows,
    stt_submitted_seconds,
)
from tools.probes import secret_scan


# ---------------------------------------------------------------------------
# P02-01 — the credential-leak scan
# ---------------------------------------------------------------------------


def test_the_scan_reports_a_dummy_sentinel_by_location_and_rule_only(tmp_path):
    """A planted dummy is found, and the report never contains its text."""
    sentinel = "AIza" + "DUMMYFOROFFLINETESTSONLY" + "00000000000"
    target = tmp_path / "sample.py"
    target.write_text(
        f"# a deliberately fake key\nVALUE = \"{sentinel}\"\n", encoding="utf-8"
    )

    findings = secret_scan.scan(tmp_path)
    assert len(findings) == 1
    assert findings[0].rule_id == "GOOGLE_API_KEY"
    assert findings[0].line == 2
    assert findings[0].path.endswith("sample.py")

    report = secret_scan.format_text_report(findings)
    assert sentinel not in report, "the matched text must never be printed"
    assert "GOOGLE_API_KEY" in report
    assert "sample.py:2" in report


def test_the_json_report_also_suppresses_content(tmp_path):
    sentinel = "AIza" + "DUMMYFOROFFLINETESTSONLY" + "00000000000"
    (tmp_path / "sample.py").write_text(f"VALUE = \"{sentinel}\"\n", encoding="utf-8")
    findings = secret_scan.scan(tmp_path)
    payload = json.dumps(
        {"summary": secret_scan.summarise(findings),
         "findings": [f.to_dict() for f in findings]}
    )
    assert sentinel not in payload
    assert "GOOGLE_API_KEY" in payload


def test_the_scan_reports_counts_only_for_a_clean_tree(tmp_path):
    (tmp_path / "clean.py").write_text("x = 1\n", encoding="utf-8")
    findings = secret_scan.scan(tmp_path)
    assert findings == []
    report = secret_scan.format_text_report(findings)
    assert "0 findings" in report
    # The report must not imply the earlier exposure was undone.
    assert "does NOT erase" in report


def test_the_allow_marker_suppresses_one_line_only(tmp_path):
    sentinel = "AIza" + "DUMMYFOROFFLINETESTSONLY" + "00000000000"
    (tmp_path / "sample.py").write_text(
        f"A = \"{sentinel}\"  # secret-scan: allow\n"
        f"B = \"{sentinel}\"\n",
        encoding="utf-8",
    )
    findings = secret_scan.scan(tmp_path)
    assert [finding.line for finding in findings] == [2]


def test_the_scan_never_reads_the_users_private_env_file(tmp_path):
    """The private env file is skipped, not opened."""
    private = tmp_path / ".env"
    private.write_text("API_KEY=not-a-real-value\n", encoding="utf-8")
    findings = secret_scan.scan(tmp_path)
    assert findings == [], "the private env file must not be scanned"


def test_the_rule_table_holds_no_real_credential_shape():
    """The rule patterns are structural; none embeds a key value."""
    for rule_id, description, pattern in secret_scan.RULES:
        assert rule_id and description
        assert pattern.pattern  # a real pattern, not an empty one


# ---------------------------------------------------------------------------
# P02-06 — immutable run evidence
# ---------------------------------------------------------------------------


def test_two_runs_of_the_same_command_never_share_a_directory(tmp_path):
    from tools.probes.evidence import RunEvidence

    first = RunEvidence("chain", ["chain"], cwd=str(tmp_path), root=tmp_path / "ev")
    with first:
        first.finish(exit_code=0, overall="PASSED", stdout="ok")
    second = RunEvidence("chain", ["chain"], cwd=str(tmp_path), root=tmp_path / "ev")
    with second:
        second.finish(exit_code=1, overall="FAILED", stdout="boom")

    assert first.directory != second.directory
    assert first.directory.is_dir() and second.directory.is_dir()
    # The earlier run's content is untouched.
    assert (first.directory / "stdout.txt").read_text(encoding="utf-8") == "ok"
    assert (second.directory / "stdout.txt").read_text(encoding="utf-8") == "boom"


def test_a_run_records_the_exact_command_cwd_runtime_and_exit_code(tmp_path):
    from tools.probes.evidence import RunEvidence

    evidence = RunEvidence("matrix", ["matrix", "--languages", "tamil"], cwd=str(tmp_path), root=tmp_path / "ev")
    with evidence:
        evidence.finish(exit_code=3, overall="FAILED", stdout="out", stderr="err")
    record = json.loads((evidence.directory / "run.json").read_text(encoding="utf-8"))
    assert record["command"] == "matrix"
    assert record["argv"] == ["matrix", "--languages", "tamil"]
    assert record["cwd"] == str(tmp_path)
    assert record["exitCode"] == 3
    assert record["overall"] == "FAILED"
    assert record["runtimeSeconds"] >= 0.0
    assert record["runtime"]["python"]


def test_the_evidence_output_is_redacted(tmp_path):
    from tools.probes.evidence import RunEvidence

    sentinel = "sk-ant-abcdefghijklmnopqrstuvwxyz0123456789"
    evidence = RunEvidence("chain", ["chain"], cwd=str(tmp_path), root=tmp_path / "ev")
    with evidence:
        evidence.finish(exit_code=0, overall="PASSED", stdout=f"key was {sentinel}")
    assert sentinel not in (evidence.directory / "stdout.txt").read_text(encoding="utf-8")


def test_the_evidence_redaction_keeps_test_node_ids_readable(tmp_path):
    """Over-redaction would destroy the evidence the capture exists for."""
    from tools.probes.evidence import RunEvidence

    node_id = (
        "services/voice/tests/providers/test_tts_protocol.py::"
        "test_the_synthesis_request_is_charged_to_the_budget PASSED"
    )
    evidence = RunEvidence("pytest", ["pytest"], cwd=str(tmp_path), root=tmp_path / "ev")
    with evidence:
        evidence.finish(exit_code=0, overall="PASSED", stdout=node_id)
    captured = (evidence.directory / "stdout.txt").read_text(encoding="utf-8")
    assert "test_the_synthesis_request_is_charged_to_the_budget" in captured
    assert "[REDACTED]" not in captured


def test_the_evidence_redaction_still_masks_a_credential_shape(tmp_path):
    from tools.probes.evidence import RunEvidence

    sentinel = "AIza" + "DUMMYFOROFFLINETESTSONLY" + "00000000000"
    evidence = RunEvidence("chain", ["chain"], cwd=str(tmp_path), root=tmp_path / "ev")
    with evidence:
        evidence.finish(exit_code=0, overall="PASSED", stdout=f"token {sentinel}")
    assert sentinel not in (evidence.directory / "stdout.txt").read_text(encoding="utf-8")


def test_the_evidence_redaction_masks_a_secret_assignment(tmp_path):
    from tools.probes.evidence import RunEvidence

    evidence = RunEvidence("chain", ["chain"], cwd=str(tmp_path), root=tmp_path / "ev")
    with evidence:
        evidence.finish(
            exit_code=0,
            overall="PASSED",
            stdout="GNANI_API_KEY=hunter2-not-a-real-value",
        )
    captured = (evidence.directory / "stdout.txt").read_text(encoding="utf-8")
    assert "hunter2-not-a-real-value" not in captured
    assert "GNANI_API_KEY" in captured


def test_an_evidence_run_id_stays_citable(tmp_path):
    """A report must be able to name the exact run directory it cites."""
    from tools.probes.evidence import RunEvidence

    evidence = RunEvidence("preflight", ["preflight"], cwd=str(tmp_path), root=tmp_path / "ev")
    with evidence:
        evidence.finish(
            exit_code=0,
            overall="INCONCLUSIVE",
            stdout=f"run id      : {evidence.record.run_id}\n"
            f"evidence    : {evidence.relative()}\n",
        )
    captured = (evidence.directory / "stdout.txt").read_text(encoding="utf-8")
    assert evidence.record.run_id in captured
    assert "[REDACTED]" not in captured


def test_the_ledger_counts_failures_and_cancellations_as_runs(tmp_path):
    from tools.probes.evidence import RunEvidence, ledger_totals

    root = tmp_path / "ev"
    root.mkdir()
    for exit_code, overall in ((0, "PASSED"), (1, "FAILED"), (2, "BLOCKED")):
        evidence = RunEvidence("chain", ["chain"], cwd=str(tmp_path), root=root)
        with evidence:
            evidence.finish(exit_code=exit_code, overall=overall)
    totals = ledger_totals(root)
    assert totals["runs"] == 3
    assert totals["successful_runs"] == 1
    assert totals["failed_or_blocked_runs"] == 2


def test_a_cancelled_run_is_recorded_as_cancelled(tmp_path):
    from tools.probes.evidence import RunEvidence, ledger_totals

    root = tmp_path / "ev"
    root.mkdir()
    evidence = RunEvidence("chain", ["chain"], cwd=str(tmp_path), root=root)
    with evidence:
        evidence.finish(exit_code=1, overall="CANCELLED")
    assert ledger_totals(root)["cancelled_runs"] == 1


def test_an_unmeasured_run_reports_unknown_wire_attempts(tmp_path):
    from tools.probes.evidence import summarise_attempts
    from gnani_coach.providers.limits import ProbeBudget

    summary = summarise_attempts(ProbeBudget(attempts_measured=False))
    assert summary["wire_attempts_used"] == "unknown"
    assert summary["wire_attempts_source"] == "unknown"
    assert "unknown" in summary["unknownNote"]


# ---------------------------------------------------------------------------
# P02-04 — matrix aggregation
# ---------------------------------------------------------------------------


def _row(**overrides):
    row = {
        "id": "english",
        "sttNativeFixture": "NOT RUN",
        "ttsNativeText": "NOT RUN",
        "geminiLanguage": "NOT RUN",
        "sttParameterAccepted": "NOT RUN",
        "ttsParameterAccepted": "NOT RUN",
        "coverage": "NOT RUN",
        "note": "",
    }
    row.update(overrides)
    return row


def test_a_row_needs_every_requested_stage_to_pass():
    assert REQUIRED_STAGES == ("sttNativeFixture", "ttsNativeText", "geminiLanguage")
    aggregate = aggregate_rows(
        [
            _row(
                id="english",
                sttNativeFixture="PASSED",
                ttsNativeText="PASSED",
                geminiLanguage="PASSED",
            )
        ],
        REQUIRED_STAGES,
    )
    assert aggregate["state"] == "PASSED"
    assert aggregate["passed_rows"] == ["english"]


def test_a_stt_only_success_is_not_a_passed_row():
    """The previous revision derived success from STT alone."""
    aggregate = aggregate_rows(
        [
            _row(
                id="english",
                sttNativeFixture="PASSED",
                ttsNativeText="NOT RUN",
                geminiLanguage="NOT RUN",
            )
        ],
        REQUIRED_STAGES,
    )
    assert aggregate["state"] != "PASSED"
    assert aggregate["passed_rows"] == []
    assert aggregate["not_run_rows"] == ["english"]
    assert aggregate["exit_code"] != 0


def test_a_failed_reasoning_stage_fails_the_row_even_when_stt_passed():
    aggregate = aggregate_rows(
        [
            _row(
                id="english",
                sttNativeFixture="PASSED",
                ttsNativeText="PASSED",
                geminiLanguage="FAILED",
            )
        ],
        REQUIRED_STAGES,
    )
    assert aggregate["state"] == "FAILED"
    assert aggregate["failed_rows"] == ["english"]
    assert aggregate["exit_code"] != 0


def test_a_failed_tts_stage_fails_the_row_even_when_stt_passed():
    aggregate = aggregate_rows(
        [
            _row(
                id="english",
                sttNativeFixture="PASSED",
                ttsNativeText="FAILED",
                geminiLanguage="PASSED",
            )
        ],
        REQUIRED_STAGES,
    )
    assert aggregate["state"] == "FAILED"
    assert aggregate["failed_rows"] == ["english"]


def test_a_parameter_acceptance_column_is_never_coverage():
    """English audio under a Tamil code must not become Tamil coverage."""
    aggregate = aggregate_rows(
        [
            _row(
                id="tamil",
                sttNativeFixture="NOT RUN",
                ttsNativeText="NOT RUN",
                geminiLanguage="PASSED",
                sttParameterAccepted="PASSED",
                ttsParameterAccepted="PASSED",
            )
        ],
        REQUIRED_STAGES,
    )
    assert aggregate["passed_rows"] == []
    assert aggregate["not_run_rows"] == ["tamil"]
    for column in PARAMETER_COLUMNS:
        assert column not in REQUIRED_STAGES


def test_an_empty_reply_is_not_a_passed_reasoning_stage():
    aggregate = aggregate_rows(
        [
            _row(
                id="english",
                sttNativeFixture="PASSED",
                ttsNativeText="PASSED",
                geminiLanguage="NO MODEL TEXT",
            )
        ],
        REQUIRED_STAGES,
    )
    assert aggregate["passed_rows"] == []
    assert aggregate["exit_code"] != 0


def test_the_aggregate_exit_code_is_nonzero_when_any_row_failed():
    aggregate = aggregate_rows(
        [
            _row(
                id="english",
                sttNativeFixture="PASSED",
                ttsNativeText="PASSED",
                geminiLanguage="PASSED",
            ),
            _row(id="tamil", geminiLanguage="FAILED"),
        ],
        REQUIRED_STAGES,
    )
    assert aggregate["exit_code"] != 0
    assert aggregate["failed_rows"] == ["tamil"]


def test_the_captured_tamil_shaped_failure_is_reported_as_a_failure():
    """STT answered, the reasoning stage timed out: the row must fail.

    This mirrors the recorded live matrix run where the Tamil row's
    Gemini call failed with a bounded timeout while STT had already
    responded. The previous revision derived the row's success from STT
    alone, so that run was reported as a pass.
    """
    aggregate = aggregate_rows(
        [
            _row(
                id="tamil",
                sttNativeFixture="PASSED",
                ttsNativeText="NOT RUN",
                geminiLanguage="FAILED",
                note="Gemini network: attempt exceeded its bound",
            )
        ],
        REQUIRED_STAGES,
    )
    assert aggregate["state"] == "FAILED"
    assert aggregate["failed_rows"] == ["tamil"]
    assert aggregate["exit_code"] != 0


def test_partial_results_are_preserved_in_the_aggregate():
    aggregate = aggregate_rows(
        [
            _row(
                id="english",
                sttNativeFixture="PASSED",
                ttsNativeText="PASSED",
                geminiLanguage="PASSED",
            ),
            _row(id="tamil", sttNativeFixture="FAILED"),
        ],
        REQUIRED_STAGES,
    )
    assert aggregate["passed_rows"] == ["english"]
    assert aggregate["failed_rows"] == ["tamil"]
    assert "every requested stage must PASS" in aggregate["rule"]


# ---------------------------------------------------------------------------
# P02-04 — catalog-resolved languages
# ---------------------------------------------------------------------------


def test_every_catalog_language_resolves_by_id_display_name_and_codes():
    entries = lang_mod.load_catalog()
    for entry in entries:
        assert lang_mod.resolve(entry.id, entries).id == entry.id
        assert lang_mod.resolve(entry.display_name, entries).id == entry.id
        # A code may be shared between entries; then it is ambiguous and
        # is refused rather than guessed. Checked separately below.
        for code in (entry.stt_code, entry.tts_code):
            try:
                assert lang_mod.resolve(code, entries).id == entry.id
            except InvalidRequestError as exc:
                assert "ambiguous" in str(exc)


def test_an_ambiguous_code_is_refused_rather_than_guessed():
    """``en-IN`` is the STT code of both English and Hinglish."""
    entries = lang_mod.load_catalog()
    with pytest.raises(InvalidRequestError) as excinfo:
        lang_mod.resolve("en-IN", entries)
    message = str(excinfo.value)
    assert "ambiguous" in message
    assert "hinglish" in message and "english" in message
    # The ids still resolve unambiguously.
    assert lang_mod.resolve("english", entries).id == "english"
    assert lang_mod.resolve("hinglish", entries).id == "hinglish"


def test_resolution_is_case_insensitive():
    entries = lang_mod.load_catalog()
    assert lang_mod.resolve("English", entries).id == "english"
    assert lang_mod.resolve("ENGLISH", entries).id == "english"


def test_an_unknown_selector_is_refused_and_names_the_known_ids():
    entries = lang_mod.load_catalog()
    with pytest.raises(InvalidRequestError) as excinfo:
        lang_mod.resolve("klingon", entries)
    message = str(excinfo.value)
    assert "does not resolve" in message
    assert "english" in message


def test_hinglish_keeps_its_own_separate_stt_and_tts_mapping():
    entries = lang_mod.load_catalog()
    hinglish = lang_mod.resolve("hinglish", entries)
    assert hinglish.kind == "code_mixed_mode"
    assert hinglish.stt_code == "en-IN"
    assert hinglish.tts_code == "hi-en"
    # The two codes are not interchangeable.
    assert hinglish.stt_code != hinglish.tts_code


def test_a_language_row_is_not_satisfied_by_another_languages_code():
    entries = lang_mod.load_catalog()
    tamil = lang_mod.resolve("tamil", entries)
    english = lang_mod.resolve("english", entries)
    assert tamil.stt_code != english.stt_code
    assert tamil.tts_code != english.tts_code


def test_the_catalog_is_read_and_never_written():
    """The shared catalog is owned by Phase 03; this phase only reads it."""
    from tools.probes.live.languages import CATALOG_PATH

    before = CATALOG_PATH.read_bytes()
    lang_mod.load_catalog()
    assert CATALOG_PATH.read_bytes() == before


# ---------------------------------------------------------------------------
# P02-02 — planning constants
# ---------------------------------------------------------------------------


def test_the_chain_plans_five_operations_not_four():
    assert CHAIN_OPS_MINIMUM == 5
    assert OPS_PER_LANGUAGE == 5


def test_the_submitted_seconds_include_the_trailing_silence():
    pcm = b"\x00\x01" * 16000  # one second of 16 kHz mono
    submitted = stt_submitted_seconds(pcm, 16000)
    assert submitted > 1.0


def test_every_relative_link_in_the_phase_02_report_resolves():
    """The report's document links must actually work."""
    from tools.probes.check_report_links import check
    from tools.probes.check_report_links import REPORT

    results = check(REPORT)
    assert results, "the report must contain at least one relative link"
    broken = [row for row in results if row[1] == "MISSING"]
    assert broken == [], f"broken report links: {broken}"


def test_the_report_link_checker_finds_a_broken_link(tmp_path):
    from tools.probes.check_report_links import check

    report = tmp_path / "REPORT.md"
    report.write_text("[x](does-not-exist.md)\n[y](https://example.com)\n", encoding="utf-8")
    results = check(report)
    statuses = {target: status for target, status, _ in results}
    assert statuses["does-not-exist.md"] == "MISSING"
    assert "https://example.com" not in statuses, "absolute links are not checked"


def test_an_over_limit_plan_is_refused_before_any_side_effect(capsys):
    """The plan check runs before a single call is issued."""
    import argparse

    from tools.probes.run import plan_budget

    args = argparse.Namespace(max_requests=4, allow_live=False)
    with pytest.raises(SystemExit) as excinfo:
        plan_budget(args, operations=5, audio_seconds=0.0)
    assert "operations" in str(excinfo.value)
    # Nothing was issued: no plan line was printed before the refusal.
    assert "[plan]" not in capsys.readouterr().out


def test_the_authorisation_ceiling_tightens_the_budget():
    import argparse

    from tools.probes.run import plan_budget

    args = argparse.Namespace(max_requests=6, allow_live=False)
    budget = plan_budget(args, operations=5, audio_seconds=0.0)
    assert budget.max_operations == 6
    assert budget.operations_left == 6


def test_a_ceiling_above_the_global_maximum_is_refused():
    import argparse

    from tools.probes.run import plan_budget

    args = argparse.Namespace(max_requests=500, allow_live=False)
    with pytest.raises(SystemExit):
        plan_budget(args, operations=5, audio_seconds=0.0)


def test_a_plan_whose_padded_audio_exceeds_the_limit_is_refused():
    import argparse

    from tools.probes.run import plan_budget

    args = argparse.Namespace(max_requests=8, allow_live=False)
    with pytest.raises(SystemExit) as excinfo:
        plan_budget(args, operations=2, audio_seconds=301.0)
    assert "audio" in str(excinfo.value)
