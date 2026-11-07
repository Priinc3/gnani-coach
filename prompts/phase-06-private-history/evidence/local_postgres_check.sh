#!/usr/bin/env bash
# Phase 06: apply the Supabase migrations to a LOCAL PostgreSQL, with the
# Supabase-managed objects (the auth schema, the storage schema, pg_cron)
# stubbed, and check what the migrations promise.
#
# This is NOT a Supabase project: it proves the SQL parses and that the
# row-level-security policies and the check constraints behave. The live
# Supabase item stays BLOCKED (no CLI, no Docker).
#
# The roles are the real Supabase role names (``authenticated``,
# ``anon``, ``service_role``), because the policies target them by name.
# A role that does not exist yet is created for the run and dropped again
# at the end; a role that already existed is left alone.
#
# Usage: bash prompts/phase-06-private-history/evidence/local_postgres_check.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
MIGRATIONS="$REPO_ROOT/supabase/migrations"
DB="gnani_phase06_check_$$"
CREATED_ROLES=""

if ! command -v psql >/dev/null 2>&1; then
  echo "BLOCKED: no local psql"
  exit 0
fi

cleanup() {
  psql -d postgres -q -c "drop database if exists \"$DB\";" >/dev/null 2>&1 || true
  for role in $CREATED_ROLES; do
    psql -d postgres -q -c "drop role if exists \"$role\";" >/dev/null 2>&1 || true
  done
}
trap cleanup EXIT

psql -d postgres -q -c "drop database if exists \"$DB\";"
psql -d postgres -q -c "create database \"$DB\";"

for role in authenticated anon service_role; do
  if ! psql -d postgres -tAc "select 1 from pg_roles where rolname = '$role'" | grep -q 1; then
    if [ "$role" = "service_role" ]; then
      psql -d postgres -q -c "create role $role nologin bypassrls;"
    else
      psql -d postgres -q -c "create role $role nologin;"
    fi
    CREATED_ROLES="$CREATED_ROLES $role"
  fi
done

echo "== stubs for the Supabase-managed objects =="
psql -d "$DB" -v ON_ERROR_STOP=1 -q <<'SQL'
create schema auth;
create table auth.users (id uuid primary key);
create or replace function auth.uid() returns uuid language sql stable as
$$ select nullif(current_setting('gnani.test_uid', true), '')::uuid $$;

create schema storage;
create table storage.buckets (
    id text primary key,
    name text not null,
    public boolean not null default false,
    file_size_limit bigint,
    allowed_mime_types text[]
);
create table storage.objects (
    id uuid primary key default gen_random_uuid(),
    bucket_id text not null,
    name text not null
);
-- Supabase enables row-level security on storage.objects; the stub mirrors
-- that, because the storage policies are meaningless without it.
alter table storage.objects enable row level security;
create or replace function storage.foldername(name text) returns text[] language sql immutable as
$$ select string_to_array(name, '/') $$;

grant usage on schema public, auth, storage to authenticated, anon, service_role;
SQL

echo "== applying the migrations =="
for file in \
  "$MIGRATIONS/20261020190000_private_history_tables.sql" \
  "$MIGRATIONS/20261020190100_private_recordings_bucket.sql" \
  "$MIGRATIONS/20261020190200_expired_recording_cleanup.sql"
do
  echo "-- $(basename "$file")"
  psql -d "$DB" -v ON_ERROR_STOP=1 -q -f "$file"
done
echo "-- 20261020190300_expired_recording_schedule.sql SKIPPED (pg_cron is Supabase-managed)"

echo "== the default grants (Supabase grants the roles on the tables; row-level security is the gate) =="
psql -d "$DB" -v ON_ERROR_STOP=1 -q <<'SQL'
grant select, insert, update, delete on all tables in schema public to authenticated, anon, service_role;
grant usage, select on all sequences in schema public to authenticated, anon, service_role;
grant select, insert, update, delete on all tables in schema storage to authenticated, anon, service_role;
SQL

echo "== row-level security is enabled on every table =="
psql -d "$DB" -v ON_ERROR_STOP=1 -c "
select c.relname as table_name, c.relrowsecurity as rls_enabled
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
 where n.nspname = 'public' and c.relkind = 'r'
 order by c.relname;"

echo "== the policies =="
psql -d "$DB" -v ON_ERROR_STOP=1 -c "
select policyname, roles::text as roles, qual, with_check
  from pg_policies
 where schemaname in ('public','storage')
 order by policyname;"

echo "== the bucket is private =="
psql -d "$DB" -v ON_ERROR_STOP=1 -c "select id, name, public from storage.buckets;"

echo "== the two accounts =="
psql -d "$DB" -v ON_ERROR_STOP=1 -q <<'SQL'
insert into auth.users (id) values ('11111111-1111-4111-8111-111111111111');
insert into auth.users (id) values ('22222222-2222-4222-8222-222222222222');
SQL

echo "== a durable record may not carry a content key =="
psql -d "$DB" -v ON_ERROR_STOP=1 -c "
insert into public.session_metrics (user_id, session_id, recorded_at, practice_language_id, scenario_id, document)
values ('11111111-1111-4111-8111-111111111111', 'ses_abc123', now(), 'english', 'job-interview',
        \$\${\"metricsVersion\":\"0.1\",\"transcript\":\"the learners own words\"}\$\$);" \
  && echo "UNEXPECTED: the content key was accepted" \
  || echo "OK: the check constraint refused the content key"

echo "== a durable record without content is accepted =="
psql -d "$DB" -v ON_ERROR_STOP=1 -q <<'SQL'
insert into public.session_metrics (user_id, session_id, recorded_at, practice_language_id, scenario_id, document)
values ('11111111-1111-4111-8111-111111111111', 'ses_ok12345', now(), 'english', 'job-interview',
        '{"metricsVersion":"0.1","sessionId":"ses_ok12345","recordedAt":"2026-10-20T10:00:00Z","practiceLanguageId":"english","scenarioId":"job-interview","recordingId":null,"turns":[],"totals":{"turnCount":0,"speakingTimeMs":0}}');
SQL
echo "OK: the metrics-only record was accepted"

echo "== owner isolation: user B cannot read, update or delete user A's row =="
echo "-- user A reads its own row:"
psql -d "$DB" -v ON_ERROR_STOP=1 -c "
begin; set local role authenticated; set local gnani.test_uid = '11111111-1111-4111-8111-111111111111';
select count(*) as rows_visible_to_a from public.session_metrics; commit;"
echo "-- user B reads the same table:"
psql -d "$DB" -v ON_ERROR_STOP=1 -c "
begin; set local role authenticated; set local gnani.test_uid = '22222222-2222-4222-8222-222222222222';
select count(*) as rows_visible_to_b from public.session_metrics; commit;"
echo "-- user B tries to delete user A's row:"
psql -d "$DB" -v ON_ERROR_STOP=1 -c "
begin; set local role authenticated; set local gnani.test_uid = '22222222-2222-4222-8222-222222222222';
delete from public.session_metrics where session_id = 'ses_abc123'; commit;"
echo "-- the row is still there (the delete was refused):"
psql -d "$DB" -v ON_ERROR_STOP=1 -c "select count(*) as rows_left from public.session_metrics;"
echo "-- the guest role sees nothing:"
psql -d "$DB" -v ON_ERROR_STOP=1 -c "
begin; set local role anon; select count(*) as rows_visible_to_anon from public.session_metrics; commit;"

echo "== the storage policies are owner-scoped =="
psql -d "$DB" -v ON_ERROR_STOP=1 -q <<'SQL'
insert into storage.objects (bucket_id, name) values ('recordings', '11111111-1111-4111-8111-111111111111/rec_abc123');
SQL
psql -d "$DB" -v ON_ERROR_STOP=1 -c "
begin; set local role authenticated; set local gnani.test_uid = '11111111-1111-4111-8111-111111111111';
select count(*) as objects_visible_to_a from storage.objects; commit;"
psql -d "$DB" -v ON_ERROR_STOP=1 -c "
begin; set local role authenticated; set local gnani.test_uid = '22222222-2222-4222-8222-222222222222';
select count(*) as objects_visible_to_b from storage.objects; commit;"

echo "== the expiry sweep marks the expired recording as deleted =="
psql -d "$DB" -v ON_ERROR_STOP=1 -q <<'SQL'
insert into public.recordings (recording_id, user_id, session_id, owner_ref, duration_ms, size_bytes, consent_version, consent_granted_at, expires_at)
values ('rec_abc123', '11111111-1111-4111-8111-111111111111', 'ses_abc123', 'usr_11111111111141118111111111111111',
        1000, 32000, '0.1', now(), now() - interval '1 day');
SQL
psql -d "$DB" -v ON_ERROR_STOP=1 -c "select public.purge_expired_recordings();"
psql -d "$DB" -v ON_ERROR_STOP=1 -c "select recording_id, state, deleted_at is not null as has_deleted_at, expires_at <= now() as expired from public.recordings;"
psql -d "$DB" -v ON_ERROR_STOP=1 -c "select count(*) as objects_left from storage.objects;"

echo "== the service role bypasses row-level security (why the service scopes its own queries) =="
psql -d "$DB" -v ON_ERROR_STOP=1 -c "
begin; set local role service_role; select count(*) as rows_visible_to_the_service_role from public.session_metrics; commit;"

echo "== done =="
