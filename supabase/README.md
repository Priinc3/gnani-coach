# Supabase assets — private history and recordings

**Phase 06 owns this tree.** These are the database and storage assets
behind the private-history routes. **No Supabase project is provisioned
by this repository**: the migrations are here to be applied to a project
the owner creates, and the service fails closed until they are.

## The environment variables

| Variable | Read by | What it is | Secret? |
|---|---|---|---|
| `SUPABASE_URL` | the Python service (`settings.supabase.url`) and the web app, **server-side** | the project URL | no |
| `SUPABASE_SERVICE_ROLE_KEY` | the Python service only (`settings.supabase.service_role_key`) | the service-role key: it bypasses row-level security | **yes** |
| `SUPABASE_PUBLISHABLE_KEY` | the Python service (the `apikey` header of the Auth `/user` check) and the web app, **server-side** | the publishable key | treat it as a secret anyway |

Rules that hold:

* the **service-role key never reaches the web app** and never reaches a
  browser bundle. It lives in the Python environment and nowhere else;
* the web app reads `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` on the
  server and passes them to the browser client as props, so neither is
  inlined into the JavaScript bundle;
* no `NEXT_PUBLIC_` variable is added: `NEXT_PUBLIC_VOICE_WS_URL` stays
  the only public one (see `docs/contracts/seams.md` §6.1).

`.env*` files stay ignored by git. There is no `.env.example` entry for
these three names in this phase: `.env.example` is Phase 03's file, so
the request for an entry is a `HELP:` item in the report, not a silent
edit.

## The migrations

| File | What it does |
|---|---|
| `migrations/20261020190000_private_history_tables.sql` | the `session_metrics`, `recordings`, `consent` and `consent_events` tables, row-level security and the owner policies |
| `migrations/20261020190100_private_recordings_bucket.sql` | the **private** `recordings` bucket and the owner-scoped storage policies |
| `migrations/20261020190200_expired_recording_cleanup.sql` | `public.purge_expired_recordings()`, the sweep of the expired recordings |
| `migrations/20261020190300_expired_recording_schedule.sql` | the `pg_cron` job that runs the sweep |

Apply them with the Supabase CLI:

```bash
supabase link --project-ref <your-project-ref>
supabase db push
```

or with `psql`:

```bash
for file in supabase/migrations/*.sql; do
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$file"
done
```

The last file needs `pg_cron`, which Supabase provides in every project.
It is the only file that cannot be applied to a plain PostgreSQL server.

## How the privacy is enforced

| Layer | What it does |
|---|---|
| Row-level security | **enabled on every table**. A policy exists for the `authenticated` role only. There is **no policy for `anon`**: a guest reaches nothing. No policy uses `using (true)`. |
| The service's own queries | the Python service holds the service-role key, which bypasses row-level security, so every query it runs is scoped to the owner explicitly. The two layers are complementary. |
| The bucket | `public = false`. A public URL is never created, stored or returned; the owner-scoped route reads the bytes and hands them to the owner. |
| The object key | `<user id>/<recording id>`. It is derived, never stored, and never leaves the service. |
| The durable record | a check constraint refuses the content keys by name (`transcript`, `quotedMistakes`, `modelText`, `audioUrl`, `embedding`, `customTopic`, `publicUrl`, `signedUrl`, `url`, `objectKey`). The Python store refuses them again before the write. |
| The recording lifecycle | `expires_at` is written when the recording is saved; the deletion is a **state** (`state = 'deleted'`, `deleted_at`), not an erasure of the fact; a late write cannot recreate a deleted recording (the fence). |

**User-linked is not anonymous.** A row belongs to one account. The
policies are what keep one account out of another's rows.

## The expiry cleanup

* the retention period is **30 days**;
* `expires_at` is written on the row when the recording is saved;
* `public.purge_expired_recordings()` marks the expired rows as deleted
  and removes the audio objects;
* the job `purge-expired-recordings` runs **every day at 03:17 UTC**
  through `pg_cron` (see `20261020190300_expired_recording_schedule.sql`);
* the function can also be run by hand:
  `select public.purge_expired_recordings();`

## The retention statement (the privacy copy)

Use this wording, because it is the true one:

> Turning recording retention off stops **this app** from keeping your
> audio and your session metrics. It cannot stop a provider from keeping
> its own records: the Gnani speech-to-text service keeps the original
> raw transcript in its billing records, so no setting in this app can
> promise that your words are stored nowhere else. Before a real-user
> launch, the selected providers' processing and retention terms have to
> be verified and the actual behaviour disclosed.

Two more sentences the same copy needs:

> Recording retention is **off by default** and is a separate decision
> from the consent to process speech live. Permission to keep audio is
> not permission to keep a transcript, and the metrics-only mode is
> genuinely content-free: it keeps numbers and identifiers.

> A signed-out caller is a **guest**: a guest has no saved history and no
> retained audio, and a guest call still works.

## What is proven and what is not

* **Proven statically** (see `services/voice/tests/persistence/`): every
  table has row-level security enabled, every policy targets
  `authenticated` and names `auth.uid()`, no policy uses `using (true)`,
  no grant names `anon` or `public`, and the bucket is private.
* **Proven against a local PostgreSQL** (see the report): the migrations
  were applied to a local PostgreSQL 16 with the Supabase-managed
  `auth` and `storage` objects stubbed, which proves the SQL parses and
  that the constraints and the policies behave.
* **Not proven**: the migrations have **not** been applied to a real
  Supabase project. The Supabase CLI and Docker are not installed in the
  build environment, so `supabase db push` was not run. The live item is
  recorded as `BLOCKED: no local Supabase`.
