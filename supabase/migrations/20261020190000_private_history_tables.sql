-- Phase 06 (G1): the private-history tables.
--
-- What this migration creates
-- ----------------------------
-- * ``session_metrics`` — the durable, metrics-only record of a practice
--   session: numbers and controlled identifiers, never content.
-- * ``recordings``     — the metadata of an opted-in recording. The audio
--   itself lives in the private storage bucket; this table holds the
--   facts about it, including the expiry and the deletion.
-- * ``consent``        — the current recording-retention consent of a
--   user.
-- * ``consent_events`` — an append-only record of every consent write,
--   with the version and the time of the write.
--
-- The rules this migration encodes
-- --------------------------------
-- * Row-level security is **enabled on every table**, and every policy
--   is scoped to the signed-in owner with ``auth.uid()``.
-- * There is **no policy for the ``anon`` role**: a guest has no history
--   and no retained audio, so the guest role reaches nothing.
-- * No policy uses ``using (true)``: a policy always names the owner.
-- * A durable record may not carry a content key. The check constraint
--   refuses the forbidden keys by name, so a row cannot hold a
--   transcript, a quoted mistake, model text, an audio URL, an embedding
--   or a custom topic even if a writer is wrong.
-- * A recording row keeps the fact that a recording existed and when it
--   was deleted: the deletion is a **state**, not an erasure of the fact.
--
-- The tables are also protected by the service's own owner-scoped
-- queries: the Python service holds the service-role key, which bypasses
-- row-level security, so ownership is enforced in the query as well. The
-- policies here protect the direct-from-the-browser path.

create table if not exists public.session_metrics (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    session_id text not null,
    recorded_at timestamptz not null,
    practice_language_id text not null,
    scenario_id text not null,
    recording_id text null,
    turn_count integer not null default 0 check (turn_count >= 0),
    speaking_time_ms integer not null default 0 check (speaking_time_ms >= 0),
    metrics_version text not null default '0.1',
    document jsonb not null,
    created_at timestamptz not null default now(),
    constraint session_metrics_owner_session unique (user_id, session_id),
    constraint session_metrics_no_content check (
        not jsonb_path_exists(document, '$.transcript')
        and not jsonb_path_exists(document, '$.quotedMistakes')
        and not jsonb_path_exists(document, '$.modelText')
        and not jsonb_path_exists(document, '$.audioUrl')
        and not jsonb_path_exists(document, '$.embedding')
        and not jsonb_path_exists(document, '$.customTopic')
        and not jsonb_path_exists(document, '$.publicUrl')
        and not jsonb_path_exists(document, '$.signedUrl')
        and not jsonb_path_exists(document, '$.url')
        and not jsonb_path_exists(document, '$.objectKey')
    )
);

alter table public.session_metrics enable row level security;

create policy "session_metrics_owner_all"
    on public.session_metrics
    for all
    to authenticated
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

create table if not exists public.recordings (
    id uuid primary key default gen_random_uuid(),
    recording_id text not null unique,
    user_id uuid not null references auth.users (id) on delete cascade,
    session_id text not null,
    owner_ref text not null,
    created_at timestamptz not null default now(),
    duration_ms integer not null check (duration_ms >= 0),
    size_bytes integer not null check (size_bytes >= 0),
    content_type text not null default 'audio/wav',
    format jsonb not null default '{"container":"wav","codec":"pcm_s16le","sampleRateHz":16000,"channels":1}'::jsonb,
    consent_version text not null,
    consent_granted_at timestamptz not null,
    state text not null default 'retained' check (state in ('retained', 'deleted')),
    expires_at timestamptz not null,
    deleted_at timestamptz null,
    constraint recordings_deleted_has_timestamp check (
        (state = 'deleted' and deleted_at is not null)
        or (state = 'retained' and deleted_at is null)
    )
);

alter table public.recordings enable row level security;

create policy "recordings_owner_all"
    on public.recordings
    for all
    to authenticated
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

create table if not exists public.consent (
    user_id uuid primary key references auth.users (id) on delete cascade,
    consent_version text not null,
    recording_retention_granted boolean not null default false,
    recording_retention_granted_at timestamptz null,
    recording_retention_withdrawn_at timestamptz null,
    updated_at timestamptz not null default now()
);

alter table public.consent enable row level security;

create policy "consent_owner_all"
    on public.consent
    for all
    to authenticated
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

create table if not exists public.consent_events (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    consent_version text not null,
    recording_retention_granted boolean not null,
    created_at timestamptz not null default now()
);

alter table public.consent_events enable row level security;

create policy "consent_events_owner_insert"
    on public.consent_events
    for insert
    to authenticated
    with check (auth.uid() = user_id);

create policy "consent_events_owner_select"
    on public.consent_events
    for select
    to authenticated
    using (auth.uid() = user_id);

-- The tables hold user-linked data. User-linked is **not** anonymous:
-- a row belongs to one account, and the row-level-security policies are
-- what keep it that way.
