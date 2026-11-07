"""The static proof of the Supabase migrations.

**Phase 06 owns this file.** The SQL is checked here, without a project
and without a network, for the four things that make the privacy
promises true:

* row-level security is enabled on **every** table;
* every policy targets the ``authenticated`` role and names
  ``auth.uid()`` — there is no policy for ``anon``, and no policy uses
  ``using (true)``;
* nothing is granted to ``anon`` or to ``public``;
* the recordings bucket is **private**.

The live check (the migrations applied to a real project) is a separate
item and is recorded as ``BLOCKED`` in the report; the script that proves
the SQL against a local PostgreSQL is
``prompts/phase-06-private-history/evidence/local_postgres_check.sh``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

#: The migrations, in the order they are applied.
#: persistence -> tests -> voice -> services -> <repo root>
MIGRATIONS_DIR = Path(__file__).resolve().parents[4] / "supabase" / "migrations"


def migration_files() -> list[Path]:
    """Every migration file, in order."""
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def statements(text: str) -> list[str]:
    """The SQL statements of a file, without the comments."""
    without_comments = "\n".join(
        line for line in text.splitlines() if not line.strip().startswith("--")
    )
    return [part.strip() for part in without_comments.split(";") if part.strip()]


@pytest.fixture(scope="module")
def all_statements() -> list[str]:
    """Every statement of every migration."""
    collected: list[str] = []
    for path in migration_files():
        collected.extend(statements(path.read_text(encoding="utf-8")))
    return collected


def test_the_migrations_exist() -> None:
    files = migration_files()
    assert files, "the migrations must be in the tree"
    names = [path.name for path in files]
    assert any("private_history_tables" in name for name in names)
    assert any("recordings_bucket" in name for name in names)
    assert any("cleanup" in name for name in names)


def test_row_level_security_is_enabled_on_every_table(all_statements) -> None:
    created = [
        statement for statement in all_statements if _is_create_table(statement)
    ]
    assert created, "the migrations must create tables"
    for statement in created:
        name = _table_name(statement)
        enabling = [
            other
            for other in all_statements
            if other.lower().startswith("alter table")
            and name in other
            and "enable row level security" in other.lower()
        ]
        assert enabling, f"row-level security is not enabled on {name}"


def test_no_policy_is_for_the_guest_role(all_statements) -> None:
    for statement in all_statements:
        if not _is_create_policy(statement):
            continue
        lowered = statement.lower()
        assert "to authenticated" in lowered, statement
        assert "to anon" not in lowered, statement
        assert "to public" not in lowered, statement


def test_no_policy_uses_using_true(all_statements) -> None:
    for statement in all_statements:
        if not _is_create_policy(statement):
            continue
        collapsed = re.sub(r"\s+", "", statement.lower())
        assert "using(true)" not in collapsed, statement
        assert "withcheck(true)" not in collapsed, statement


def test_every_policy_names_the_owner(all_statements) -> None:
    policies = [statement for statement in all_statements if _is_create_policy(statement)]
    assert policies, "the migrations must create policies"
    for statement in policies:
        assert "auth.uid()" in statement, statement


def test_nothing_is_granted_to_the_guest_role_or_to_public(all_statements) -> None:
    for statement in all_statements:
        lowered = statement.lower()
        if not lowered.startswith("grant"):
            continue
        assert " to anon" not in lowered, statement
        assert " to public" not in lowered, statement


def test_the_recordings_bucket_is_private() -> None:
    text = (MIGRATIONS_DIR / "20261020190100_private_recordings_bucket.sql").read_text(
        encoding="utf-8"
    )
    assert "public = false" in text or "public false" in text
    assert "public true" not in text.replace(" ", " ").lower()


def test_the_bucket_policies_are_owner_scoped() -> None:
    text = (MIGRATIONS_DIR / "20261020190100_private_recordings_bucket.sql").read_text(
        encoding="utf-8"
    )
    assert "storage.foldername(name)" in text
    assert "auth.uid()::text" in text


def test_the_content_keys_are_refused_by_a_constraint() -> None:
    text = (MIGRATIONS_DIR / "20261020190000_private_history_tables.sql").read_text(
        encoding="utf-8"
    )
    for key in (
        "transcript",
        "quotedMistakes",
        "modelText",
        "audioUrl",
        "embedding",
        "customTopic",
    ):
        assert f"'$.{key}'" in text, key
    assert "jsonb_path_exists" in text


def test_the_expiry_cleanup_is_defined_and_scheduled() -> None:
    cleanup = MIGRATIONS_DIR / "20261020190200_expired_recording_cleanup.sql"
    schedule = MIGRATIONS_DIR / "20261020190300_expired_recording_schedule.sql"
    assert cleanup.is_file() and schedule.is_file()
    cleanup_text = cleanup.read_text(encoding="utf-8")
    schedule_text = schedule.read_text(encoding="utf-8")
    assert "purge_expired_recordings" in cleanup_text
    assert "expires_at" in cleanup_text
    assert "cron.schedule" in schedule_text
    assert "purge-expired-recordings" in schedule_text
    # The schedule is a daily job, and the README says when it runs.
    assert re.search(r"cron\.schedule\(\s*'purge-expired-recordings'", schedule_text)
    readme = (MIGRATIONS_DIR.parent / "README.md").read_text(encoding="utf-8")
    assert "03:17 UTC" in readme
    assert "pg_cron" in readme


def test_the_readme_documents_the_environment_names() -> None:
    readme = (MIGRATIONS_DIR.parent / "README.md").read_text(encoding="utf-8")
    assert "SUPABASE_URL" in readme
    assert "SUPABASE_SERVICE_ROLE_KEY" in readme
    assert "SUPABASE_PUBLISHABLE_KEY" in readme
    # The provider-side retention sentence has to be in the copy.
    assert "billing records" in readme
    assert "raw transcript" in readme


def _is_create_table(statement: str) -> bool:
    return statement.lower().startswith("create table")


def _is_create_policy(statement: str) -> bool:
    return statement.lower().startswith("create policy")


def _table_name(statement: str) -> str:
    """The table a ``create table`` statement names."""
    match = re.search(
        r"create\s+table\s+(?:if\s+not\s+exists\s+)?([a-zA-Z0-9_.\"]+)",
        statement,
        re.IGNORECASE,
    )
    assert match, statement
    return match.group(1).strip('"')
