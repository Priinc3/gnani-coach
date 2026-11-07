# Phase 06 — private-history (B2, G1)

**Status: BUILT.** Identity, metrics-only persistence, an opt-in
recording lifecycle and private access are implemented, tested against
fakes, and the SQL is proved against a local PostgreSQL. The live
Supabase item is **BLOCKED** (no Supabase CLI and no Docker in this
environment); nothing else is blocked.

---

## 1. The dependency decisions (with sources)

The manifest exception of ADDENDUM §F was used **once, first**, and the
manifests were not touched afterwards. The notice was posted in
`prompts/parallel-G1/COMM.md` at 18:50; Phase 05 recreated that file at
18:53 without it, so the notice was re-posted as entry 04 at 19:18.

| Where | Dependency | Pin | Why | Source |
|---|---|---|---|---|
| `apps/web/package.json` | `@supabase/ssr` | `0.12.7` | the cookie-based browser and server clients that the Next.js guide uses | <https://supabase.com/docs/guides/auth/server-side/nextjs> (checked 2026-10-20) |
| `apps/web/package.json` | `@supabase/supabase-js` | `2.118.0` | the client itself; `@supabase/ssr@0.12.7` declares the peer dependency `@supabase/supabase-js ^2.114.0`, and 2.118.0 satisfies it | <https://www.npmjs.com/package/@supabase/ssr> (checked 2026-10-20) |
| `services/voice/pyproject.toml` | `httpx` | `0.28.1` | the Supabase Auth, PostgREST and Storage APIs are plain HTTPS | <https://supabase.com/docs/guides/auth/jwts> (checked 2026-10-20) |

**No new package was downloaded on the Python side.** `httpx==0.28.1`
was already resolved in `services/voice/uv.lock` as a transitive
dependency of `google-genai==2.31.0`; it is now declared **directly**,
because the identity verifier and the stores import it. The lock was
re-resolved with `uv lock`: no package version changed and nothing was
removed — the only difference is that `httpx` is now a direct
dependency of `gnani-coach` (and the lock gained the transitive entries
that the previous resolution had left out: `certifi`, `cffi`,
`pycparser`).

### The verification approach

The service verifies a bearer token against the **Supabase Auth
server**, not by decoding it:

```http
GET https://<project>.supabase.co/auth/v1/user
apikey: <publishable key>
Authorization: Bearer <the caller's access token>
```

A `200` means the token is genuine; anything else is a guest. This is
the check the Supabase JWT guide documents for the shared-secret case,
and it is valid for asymmetric-key projects too
(<https://supabase.com/docs/guides/auth/jwts>, checked 2026-10-20).

It was chosen over a local JWKS verification because it needs **no new
cryptographic dependency** and no key-rotation handling in this
process; the cost is one HTTPS round trip, which the short-TTL cache
amortises. The **shared-secret HS256 approach was not used**: the guide
calls it out as strongly discouraged, and nothing in this repository
verifies a token with a shared secret.

Before the round trip the token is screened locally, and every screen
can only **reject**: a malformed token, an expired token, a token whose
audience is not `authenticated`, and a token whose issuer is not this
project's Auth server. The decoded claims are never used to accept
anything — acceptance is always the Auth server's decision.

---

## 2. The files

### Python — identity (Phase 06's own tree)

| File | What it holds |
|---|---|
| `services/voice/src/gnani_coach/identity/__init__.py` | the frozen export `get_identity()`, plus `get_identity_for()` for an explicit configuration |
| `services/voice/src/gnani_coach/identity/verifier.py` | the verifier, the bounded token cache, the opaque user id, the guest implementation |

### Python — persistence (Phase 06's own tree)

| File | What it holds |
|---|---|
| `services/voice/src/gnani_coach/persistence/__init__.py` | `router`, `get_session_store()`, `get_recording_store()`, `get_consent_store()` |
| `services/voice/src/gnani_coach/persistence/router.py` | the four routes, the bearer verification, the frozen error shape, the body size limit |
| `services/voice/src/gnani_coach/persistence/metrics.py` | the metrics-only guard: content keys are refused, and every string must be a controlled identifier |
| `services/voice/src/gnani_coach/persistence/consent.py` | the consent state, its version and its times |
| `services/voice/src/gnani_coach/persistence/errors.py` | the five domain errors (no token, no path, no bucket key in a message) |
| `services/voice/src/gnani_coach/persistence/stores/memory.py` | the in-memory session, recording and consent stores (the reference semantics) |
| `services/voice/src/gnani_coach/persistence/stores/supabase.py` | the Supabase-backed stores, the private bucket client, the derived object key |
| `services/voice/src/gnani_coach/persistence/stores/__init__.py` | the three accessors; each returns `None` when storage is unconfigured |

### Python — tests (Phase 06's own tree)

`services/voice/tests/identity/{conftest.py,fake_auth.py,test_identity.py}`
(25 tests) and
`services/voice/tests/persistence/{conftest.py,phase06_support.py,fake_supabase.py,test_router.py,test_router_supabase.py,test_stores_memory.py,test_stores_supabase.py,test_sql_static.py}`
(79 tests, including the four routes against the Supabase stores).

### Supabase assets (Phase 06's own tree)

`supabase/README.md` and four migrations in `supabase/migrations/`:
the four tables with row-level security, the private bucket with the
owner-scoped storage policies, the expiry sweep, and its `pg_cron`
schedule.

### Web (Phase 06's own tree)

| File | What it holds |
|---|---|
| `apps/web/src/lib/auth/index.ts` | the frozen seam: `useSession()`, `signOut()`; the additive `getAccessToken()`, `onSignOut()`, `setRecordingRetention()` |
| `apps/web/src/lib/auth/browser.ts` | the browser Supabase client, the session store, the sign-out registry, the device recording flag |
| `apps/web/src/lib/auth/server.ts` | the server-only Supabase configuration and the server client |
| `apps/web/src/lib/auth/types.ts` | `SessionStatus`, `SessionState`, the guest and loading states |
| `apps/web/src/app/auth/sign-in/page.tsx` | the server component: reads the URL and the publishable key, passes them as props |
| `apps/web/src/app/auth/sign-in/SignInPanel.tsx` | the client component: the email magic link and the rendered session state |
| `apps/web/src/app/auth/sign-out/page.tsx` + `SignOutButton.tsx` | the sign-out page |
| `apps/web/src/app/auth/session/route.ts` | `GET`/`DELETE` `/auth/session`: the verified session and the access token to forward |
| `apps/web/src/proxy.ts` | the real proxy: refresh with `getClaims()`, no-cache headers, never a guard |

### Manifests (the one exception)

`apps/web/package.json`, `package-lock.json`,
`services/voice/pyproject.toml`, `services/voice/uv.lock` — dependencies
only, as listed in §1.

### Tests and evidence

`prompts/phase-06-private-history/web-tests/{playwright.config.ts,auth.spec.ts}`
(14 tests) and `prompts/phase-06-private-history/evidence/` (the raw
output of every command, plus the local-PostgreSQL script).

---

## 3. The commands and their raw output

Every output is in `prompts/phase-06-private-history/evidence/`.

| Command | Result | Evidence |
|---|---|---|
| `uv run --project services/voice python -m pytest services/voice/tests -v` | **4 failed, 366 passed, 3 skipped** — every failure is in **Phase 05's** in-flight `services/voice/tests/conversation/test_transport.py` | `pytest-voice-full.txt` |
| the same command without Phase 05's two in-flight directories (identity, persistence, foundation, providers) | **351 passed, 3 skipped**, exit 0 | `pytest-voice.txt` |
| `npm run lint` | **exit 0** (no errors) | `npm-lint.txt` |
| `npm run typecheck` | **exit 2** — every error is in **Phase 04's** `apps/web/tests/unit/*.spec.ts` | `npm-typecheck.txt` |
| `npm run build` | **exit 1** — the same Phase 04 test files (the build type-checks them) | `npm-build.txt` |
| `npm run test:contracts` | **PASS** — 78 examples, 8 schemas | `npm-test-contracts.txt` |
| `uv run --project services/voice python tools/probes/secret_scan.py` | **2 findings**, both in sibling files (Phase 04's `apps/web/tests/unit/client.spec.ts:232`, Phase 05's `services/voice/tests/conversation/test_transport.py:299`); **0 in any Phase 06 file** | `secret-scan.txt` |
| `npx playwright test --config=prompts/phase-06-private-history/web-tests/playwright.config.ts` | **14 passed**, exit 0 | `playwright-phase06.txt` |
| `eslint src/lib/auth src/app/auth src/proxy.ts` (the Phase 06 web files alone) | **no findings**, exit 0 | `eslint-phase06-files.txt` |
| `uv run --project services/voice python -m pytest tests/integration -v` (Phase 03's files, not mine) | **9 failed** — 5 of them are the old `503` stub expectations of Phase 06's routes, 4 are Phase 05's stub expectations (see §9) | `pytest-integration.txt` |
| `bash prompts/phase-06-private-history/evidence/local_postgres_check.sh` | the migrations apply, RLS and the constraints behave | `local-postgres-sql.txt` |

**Every failing command fails in a file that belongs to a sibling**, and
every Phase 06 file is green: the **104 tests** of `tests/identity` (25)
and `tests/persistence` (79), the **14 web tests**, the lint of the Phase
06 web files, and the secret scan of the Phase 06 files.

The build shows the three Phase 06 routes and the proxy:

```
├ ƒ /auth/session
├ ƒ /auth/sign-in
└ ƒ /auth/sign-out
ƒ Proxy (Middleware)
```

---

## 4. The isolation matrix

Two accounts, **A** and **B**, plus a guest. Every cell is a test in
`services/voice/tests/persistence/` — `test_router.py` (the routes over
the in-memory stores), `test_router_supabase.py` (the same routes over
the **Supabase** stores and a fake backend) and
`test_stores_supabase.py` (the stores on their own).

| Request | Guest | Owner A, own object | Owner B, A's object |
|---|---|---|---|
| `GET /api/history` | **401** + the frozen error shape (`unauthenticated`, `retryable: false`) | **200**, only A's sessions, newest first | **200**, only B's sessions — A's rows are not in the list |
| `POST /api/consent` | **401** | **200**, the consent of A is written (version + time) | **200**, the consent of B is written |
| `GET /api/recordings/{id}` | **401** | **200** `audio/wav`, the bytes | **404** — byte-identical to a missing id (same code, category, message, retryable; only the per-response correlation id and timestamp differ) |
| `DELETE /api/recordings/{id}` | **401** | **204** | **404**, and A's recording is still there |
| a repeated `DELETE` | — | **404** | — |
| a forged `user_id` in the body | — | ignored: the owner is the verified `sub` | — |
| the durable store, cross-owner | — | `list_sessions`/`get_session` are scoped to the owner | B sees nothing of A's |

The same owner scoping is enforced twice, on purpose:

* **in the database**, by row-level security (`auth.uid() = user_id`) —
  proved against a local PostgreSQL with two real roles (§6);
* **in the service**, by an explicit `user_id` filter in every query —
  the service-role key bypasses RLS, so the query is the gate there.

A recording id that cannot exist (`../../etc/passwd`, `rec_../../x`) is
answered **404**, like a missing one, and never reaches a query.

---

## 5. The privacy behaviours

| Promise | Where it is proved |
|---|---|
| A guest has no history and no recording | `test_a_guest_has_no_history`, `test_a_guest_cannot_read_or_delete_a_recording`, `test_a_guest_writes_nothing` |
| `GET /api/history` for a guest is `401` | `test_a_guest_has_no_history` |
| Another user's recording id is `404`, identical to a missing one | `test_a_missing_recording_and_a_foreign_one_answer_identically` |
| A repeated delete is `404` | `test_a_repeated_delete_is_a_missing_recording` |
| No endpoint echoes a token, a path or a bucket key | `test_no_response_echoes_a_token_a_path_or_a_bucket_key` |
| The errors use the frozen shape | every error test validates against `packages/contracts/schemas/error-shape.schema.json` with `jsonschema` |
| The request bodies are size-limited | `test_an_oversized_body_is_refused` → **413**, frozen shape, and the body is never parsed |
| The consent records a version and a time | `test_granting_the_consent_records_the_version_and_the_time`, `test_the_consent_write_records_the_version_and_the_time` |
| A withdrawal stops future retention and does **not** delete | `test_withdrawing_the_consent_does_not_delete_the_old_recordings`, `test_a_withdrawal_does_not_delete_the_old_recording` |
| A late save after a delete cannot recreate the recording | `test_a_late_save_after_a_delete_cannot_recreate_the_recording` (both stores) |
| A late save after a withdrawal is refused | `test_a_late_save_after_a_withdrawal_is_refused` (both stores) |
| The consent is re-checked at write time | `test_the_consent_is_re_checked_at_write_time` |
| The expiry is 30 days and the recording is gone afterwards | `test_a_recording_expires_after_thirty_days`, `test_an_expired_recording_is_gone` |
| Metrics-only is content-free | `test_a_document_with_content_is_refused_before_the_write`, `test_a_nested_content_key_is_refused`, `test_free_text_is_refused`, `test_the_stored_record_holds_no_content` (the fake database and the captured log are inspected) |
| Ten concurrent saves all land | `test_ten_concurrent_saves_all_land`, `test_ten_concurrent_session_saves_all_land` |
| The whole chain works over the Supabase backend | `test_router_supabase.py`: the consent reaches the table, the history reaches the table, the recording is uploaded under the owner's own folder and is read, deleted and deleted again, and a guest reaches the backend **not at all** |

**The metrics-only guard** is stricter than the schema: a document is
refused when it carries a content key **anywhere** in the tree
(`transcript`, `quotedMistakes`, `modelText`, `audioUrl`, `embedding`,
`customTopic`, `publicUrl`, `signedUrl`, `url`, `objectKey`, and a few
more), and when **any string** in it is not a controlled identifier (an
opaque id, a catalog id, a version, a timestamp, or one of the closed
enumerations of the frozen schema). The refusal names the *path* of the
offending key and never its value.

---

## 6. The static SQL proof and the local-PostgreSQL proof

### The static proof (in the test suite)

`services/voice/tests/persistence/test_sql_static.py` reads the four
migration files and asserts:

* row-level security is enabled on **every** table
  (`alter table ... enable row level security`);
* every policy targets **`authenticated`** — no policy for `anon`, no
  policy for `public`, no policy without a role;
* no policy uses `using (true)` or `with check (true)`;
* every policy names the owner with `auth.uid()`;
* **no grant names `anon` or `public`** (the only grant is
  `grant execute on function public.purge_expired_recordings() to service_role`);
* the bucket is **private** (`public = false`);
* the storage policies are owner-scoped
  (`storage.foldername(name))[1] = auth.uid()::text`);
* the content keys are refused by a check constraint
  (`jsonb_path_exists` on `$.transcript`, `$.quotedMistakes`, …);
* the cleanup function and its `cron.schedule` job exist, and the
  README documents the schedule and the environment names.

### The local-PostgreSQL proof (in the evidence)

The Supabase CLI and Docker are **not installed** in this environment,
but a local PostgreSQL 16 is. The script
`prompts/phase-06-private-history/evidence/local_postgres_check.sh`
applies the migrations to a scratch database with the Supabase-managed
objects stubbed (`auth.users`, `auth.uid()`, `storage.buckets`,
`storage.objects`, `storage.foldername`) and the real role names
(`authenticated`, `anon`, `service_role`), and then shows:

* row-level security is enabled on all four tables;
* the nine policies, all of them `to authenticated`;
* the bucket is private;
* a record carrying `transcript` is **refused by the check constraint**,
  and a metrics-only record is accepted;
* user A sees its own row, user B sees **0** rows and its `DELETE`
  affects **0** rows, and the **guest role sees 0** rows;
* the storage policies are owner-scoped (A sees its object, B sees 0);
* `public.purge_expired_recordings()` marks the expired recording as
  `deleted` and removes the audio object;
* the service role sees everything — which is exactly why the service
  scopes its own queries.

The scratch database and the roles it created are dropped again by the
script.

### The live-Supabase item

**BLOCKED: no local Supabase.** The Supabase CLI is not installed and
Docker is not available, so `supabase db push` against a real project
was not run, and **no project is provisioned by this repository**. What
is proved is the static proof and the local-PostgreSQL proof above.

---

## 7. The sign-out hook

**The exact name: `onSignOut(handler: () => void): () => void`**, exported
from `@/lib/auth` (`apps/web/src/lib/auth/index.ts`).

```ts
import { onSignOut } from "@/lib/auth";

const unsubscribe = onSignOut(() => {
  // close the live call connection here
});
```

The handler runs inside `signOut()`'s `finally` block, so it runs
**whatever happens** — even when the sign-out itself fails. The name is
posted in `prompts/parallel-G1/COMM.md` as a `DECISION`.

**Phase 04 uses it.** Their adapter
`apps/web/src/lib/session-ui/accessToken.ts` reads the seam through the
ADDENDUM §C pattern and already handles all three additive exports:

```ts
type AuthModule = {
  getAccessToken?: () => Promise<string | null>;
  onSignOut?: (handler: () => void) => () => void;
  setRecordingRetention?: (granted: boolean) => Promise<void>;
};
```

`apps/web/src/lib/session-ui/useCallSession.ts:120` subscribes through
`subscribeToSignOut`, so a signed-out learner keeps no live socket. The
adapter casts the module, so it does not depend on my internals — only
on the three names.

---

## 8. The web side

* **The frozen seam is unchanged.** `useSession()` and `signOut()` keep
  their names and their shapes (`status`, `userId`, `recordingRetention`).
  `useSession()` is now a real hook (`useSyncExternalStore` over the
  session store) instead of a constant.
* **`getAccessToken()`** is the additive export of ADDENDUM §C. It
  returns the caller's own short-lived access token, or `null` for a
  guest. It is forwarded to our own voice service, which verifies it
  again.
* **The sign-in method is an email magic link** (a one-time password by
  email), chosen over a password because it keeps the credential out of
  the application entirely — there is no password to store, hash, leak
  or reset. Source:
  <https://supabase.com/docs/guides/auth/auth-otp/email-otp> (checked
  2026-10-20). The deployment needs the Redirect URLs of the project to
  allow this origin and an email provider to be configured.
* **The proxy** refreshes the session with `getClaims()` (never
  `getSession()`), writes the refreshed cookies to the request and to
  the response, and sets `Cache-Control: private, no-store, ...`,
  `Pragma: no-cache` and `Expires: 0`. It **never guards** a route: it
  contains no redirect, no rewrite and no refusal, so `/` is never
  blocked — a guest may call.
* **The configuration is server-read.** `SUPABASE_URL` and
  `SUPABASE_PUBLISHABLE_KEY` are read in the server component and
  handed to the browser client as props; no `NEXT_PUBLIC_SUPABASE_*`
  variable exists anywhere in the web tree (proved by a test), and the
  **service-role key never appears in the web tree** (proved by a test).
* **`setRecordingRetention(granted)`** writes the device-local
  preference and, for a signed-in learner, records the consent on the
  voice service (`POST /api/consent` with the caller's own bearer
  token). It is additive; Phase 04's adapter already reads it under that
  name (`apps/web/src/lib/session-ui/accessToken.ts`), and their
  `setRecordingRetentionConsent` is their own wrapper around it.

---

## 9. The deviations, the `HELP:` items and the sibling failures

### Deviations

1. **The routes stay out of the OpenAPI document**
   (`include_in_schema=False`, as the Phase 03 stub had them). The
   BUILD allows either, as long as it is documented. It is documented
   because the service publishes no API surface at all
   (`docs_url` and `redoc_url` are `None`) and the Phase 01 invariant
   that *"/health is the only documented route"* is still asserted by a
   Phase 01 test file that Phase 06 may not edit — publishing the
   routes would turn the service's own suite red for no gain.
   `docs/contracts/seams.md` §2 says the routes join the document once
   they are real; that sentence belongs to Phase 03, so it is raised as
   a `HELP:` below. Publishing them is a one-line change
   (`include_in_schema=True` on the four decorators).
2. **The owner of a metrics write is the verified request context.**
   The frozen `SessionStorePort.save_metrics(record)` carries no owner
   and the durable-metrics schema has no user field (and forbids
   unknown ones), so the owner is resolved from the identity context
   (`identity.current_user()`), which the identity verifier sets when
   it verifies the token. The store also offers the explicit
   `save_metrics_for(user_id, record)` for a caller that knows the
   owner. Phase 05's runtime verifies the token in the same task as the
   write, so the owner is there when it writes.

### `HELP:` items (for the CEO / the contract owner)

1. **`HELP:` — the Phase 03 integration test expects the old stub.**
   `tests/integration/test_seams.py` and `tests/integration/test_origins.py`
   are not Phase 06's files. They now fail because the seams are real:
   * `tests/integration/test_seams.py:83` — `assert response.status_code == 503`
     (history; it is `401` for a guest now);
   * `tests/integration/test_seams.py:89` — `assert response.status_code == 503`
     (consent; `401` for a guest now);
   * `tests/integration/test_seams.py:96` — `assert response.status_code == 503, method`
     (recordings; `401` for a guest now);
   * `tests/integration/test_seams.py:102` — `assert
     response.headers["content-type"].startswith("application/json")`
     in `test_a_recording_route_never_returns_audio`; the route answers
     `401` + the frozen error shape for a guest, and `200 audio/wav` for
     the owner;
   * `tests/integration/test_origins.py:163` — `assert response.status_code == 503`
     (the CORS check on `/api/history`; it is `401` for a guest now).

   These are the *expected* failures of a phase that replaces a stub.
   The B2 TEST should assert the new behaviour: a guest is `401`, an
   owner gets their own rows, and another user's recording is `404`.
2. **`HELP:` — the `.env.example` entries.** `SUPABASE_URL`,
   `SUPABASE_SERVICE_ROLE_KEY` and `SUPABASE_PUBLISHABLE_KEY` need an
   entry in `.env.example` (root, `apps/web/.env.example` and
   `services/voice/.env.example`). Those files are Phase 03's, so the
   request is a `HELP:` and not a silent edit. The names are documented
   in `supabase/README.md`.
3. **`HELP:` — the OpenAPI document.** `docs/contracts/seams.md` §2 says
   the routes join the OpenAPI document once they are real; Phase 06
   kept them excluded (deviation 1). Please confirm which of the two is
   wanted; it is a one-line change on the Phase 06 side.
4. **`HELP:` — the owner of `save_metrics`.** See deviation 2. The frozen
   port has no owner parameter, so the owner comes from the verified
   request context. Phase 05's runtime already verifies the token in the
   same task, so nothing has to change on their side; a note in
   `docs/contracts/seams.md` would make the rule explicit for later
   phases.

### Failures that belong to a sibling (not Phase 06)

* `uv run --project services/voice python -m pytest services/voice/tests`
  fails **4 tests, all in Phase 05's** in-flight
  `services/voice/tests/conversation/test_transport.py` (the happy path
  over a real websocket, the heartbeat, the idle timeout and the call
  cap). Without that directory the suite is green: **351 passed, 3
  skipped**. The raw output of both runs is in `pytest-voice-full.txt`
  and `pytest-voice.txt`. (The count moved during the phase — it was 11
  an hour earlier — because Phase 05 is still building that tree.)
* `npm run typecheck` and `npm run build` fail on **Phase 04's** test
  files, `apps/web/tests/unit/settings.spec.ts:181,191,197,199` (a
  `SessionSettings` object that is missing four frozen fields) and
  `apps/web/tests/unit/worklet.spec.ts:61,89`. The build type-checks
  the test files, so it fails for the same reason. `npm run lint` is
  green.
* The **credential scan** reports **2 findings**, both in sibling files:
  `apps/web/tests/unit/client.spec.ts:232` (Phase 04) and
  `services/voice/tests/conversation/test_transport.py:299` (Phase 05).
  The rule is `GENERIC_SECRET` — an assignment of a long literal to a
  secret-ish name — and the scan never prints the matched text. **No
  Phase 06 file is a finding**: the fake tokens in
  `services/voice/tests/*/fake_*.py` are not credential-shaped, and the
  report and the evidence carry no key.
* `tests/integration/test_seams.py` and `tests/integration/test_origins.py`
  also fail on **Phase 05's** stub expectations, now that the call
  socket is real:
  * `tests/integration/test_seams.py::test_call_socket_closes_with_the_frozen_error`;
  * `tests/integration/test_origins.py::test_an_allowed_origin_opens_the_call_socket`;
  * `tests/integration/test_origins.py::test_a_missing_origin_opens_the_call_socket`;
  * `tests/integration/test_seams.py::test_analysis_port_reports_insufficient_evidence`
    fails with `TypeError: can only concatenate tuple (not "str") to tuple`
    in `services/voice/src/gnani_coach/analysis/service.py:260`.

---

## 10. The limits: what is fake-proven and what is live-proven

**Proven against fakes** (the behaviour is real, the backend is not):

* the whole token matrix, the cache, the concurrency and the
  fail-closed behaviour of the identity verifier (a fake Auth server);
* the four routes, the isolation matrix, the consent lifecycle, the
  fence, the expiry and the metrics-only guard (the in-memory stores,
  and the Supabase stores against a fake Supabase that speaks the same
  HTTPS);
* the whole web experience: the guest state, the sign-in page, the
  sign-out page and the session endpoint (a real browser, no project);
* the SQL: statically, and against a local PostgreSQL with the
  Supabase-managed objects stubbed.

**Not proven live:**

* no Supabase project was provisioned, so **no live Auth, PostgREST or
  Storage call was made** (`BLOCKED: no local Supabase`);
* the magic-link sign-in was **not** exercised end to end: it needs a
  project, an email provider and an allow-listed redirect URL;
* the `pg_cron` schedule was **not** applied (the extension is
  Supabase-managed); the cleanup *function* was applied and proved;
* the web side was proved **unconfigured** (a guest deployment). With a
  project configured, the proxy, the browser client and the session
  endpoint take the other branch of the code, which is the branch the
  Supabase guide documents but which this environment cannot exercise;
* the recording lifecycle was proved against the stores, not against a
  real bucket with real audio bytes.

**The data retention statement** (the wording the privacy copy has to
use) is in `supabase/README.md`:

> Turning recording retention off stops **this app** from keeping your
> audio and your session metrics. It cannot stop a provider from keeping
> its own records: the Gnani speech-to-text service keeps the original
> raw transcript in its billing records, so no setting in this app can
> promise that your words are stored nowhere else.

---

PHASE 06 BUILT — AWAITING B2 TEST
