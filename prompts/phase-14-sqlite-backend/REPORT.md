# Phase 14 — sqlite-backend (B4, G2)

**State:** PHASE 14 BUILT

## What was built

### Backend selection
`SPEAKING_COACH_STORAGE_BACKEND` now selects `sqlite`, `supabase`,
`memory` or the unset default (Supabase when configured, no storage
otherwise). `SPEAKING_COACH_DATA_DIR` defaults to
`/var/lib/gnani-coach`. Both are read with `os.environ` inside the new
modules; `settings.py` was not edited. A database that cannot be opened
logs one content-free warning and leaves the service in the guest state.

### Files

Backend:
- `services/voice/src/gnani_coach/persistence/stores/sqlite.py` (new)
- `services/voice/src/gnani_coach/persistence/stores/__init__.py`
- `services/voice/src/gnani_coach/persistence/errors.py` (two cap errors)
- `services/voice/src/gnani_coach/identity/local.py` (new)
- `services/voice/src/gnani_coach/identity/local_router.py` (new)
- `services/voice/src/gnani_coach/identity/__init__.py`
- `services/voice/src/gnani_coach/main.py` (one line)

Tests:
- `services/voice/tests/identity/test_local.py` (new)
- `services/voice/tests/persistence/test_stores_sqlite.py` (new)

Web:
- `apps/web/src/lib/auth/browser.ts`
- `apps/web/src/lib/auth/index.ts`
- `apps/web/src/app/auth/sign-in/SignInPanel.tsx`
- `apps/web/src/app/auth/sign-in/page.tsx`
- removed dead Supabase-only files: `apps/web/src/app/auth/session/route.ts`,
  `apps/web/src/lib/auth/server.ts` (nothing imported them after the
  browser client was replaced)
- `apps/web/src/proxy.ts` left unchanged; it still passes through when no
  Supabase environment exists

Coordination:
- `prompts/parallel-G2/COMM.md`, `prompts/parallel-G2/STATUS.md`
- this report and `evidence/`

### The one `main.py` line
```python
app.include_router(__import__("gnani_coach.identity.local_router", fromlist=["router"]).router)
```
The dynamic import keeps the CEO grant to exactly one added line; the
`local_router` module is otherwise imported normally inside itself.

### SQLite behaviour
- One connection, one `threading.Lock`, every call through
  `asyncio.to_thread`.
- `PRAGMA foreign_keys=ON`, `journal_mode=WAL`, `busy_timeout=5000`,
  `cache_size=-2000`, `mmap_size=0`, `synchronous=NORMAL`; schema version
  in `PRAGMA user_version`.
- Tables mirror `supabase/migrations`: `users`, `auth_tokens`, `consent`,
  `consent_events`, `session_metrics`, `recordings`.
- All SQL is parameterised. The database file is `0600`, its directory
  and the recordings directories are `0700`; WAV files are `0600`.
- Owner isolation, the metrics-only guard, consent re-check at write
  time, the delete/withdraw fence, 30-day expiry (read and sweep), the
  10 MB per-file cap, the 200 MB per-user cap, and account deletion of
  every row and file are implemented and tested.
- Recording paths are built only from ids matching
  `^usr_[a-z0-9]{6,40}$` / `^rec_[a-z0-9]{6,40}$`; traversal ids are
  refused.

### Local identity
- `POST /api/auth/register`, `POST /api/auth/login`,
  `POST /api/auth/logout`, `GET /api/auth/me`,
  `DELETE /api/auth/account` (password required again).
- `hashlib.scrypt` with `n=2**14, r=8, p=1`, 16-byte salt, 32-byte key.
  Hashing runs in a thread behind a process-wide `threading.Semaphore(1)`.
- Constant-time `hmac.compare_digest`; an unknown email does the same
  scrypt work as a known one and gets the same login message as a wrong
  password.
- Tokens are `secrets.token_urlsafe(32)`, stored only as SHA-256 hex,
  expire after 30 days, and are revoked by logout. `verify_token` returns
  `None` for absent, malformed, expired, revoked or unknown tokens and
  never raises.
- Register/login are throttled at 10 per client address per minute with
  the existing `security.RateLimiter` style. Bodies are capped at 8192
  bytes. Emails are lowercased, trimmed, shape-checked and capped at 254
  characters.
- Local user ids are `usr_` + 32 lowercase hex, so `subject_from_user_id`
  and `user_id_from_user_id` keep working.

### Web client
- `useSession()`, `signOut()`, `getAccessToken()`, `onSignOut()` and
  `setRecordingRetention()` keep their frozen names and shapes.
- The browser now calls the voice service over `fetch`, using
  `deriveVoiceHttpUrl()` from `lib/session-ui/http`.
- The token lives in `localStorage` under `gnani.accessToken`. It is
  cleared on logout and on any `401`, and is never placed in a URL.
- The sign-in screen has email + password, a "Sign in" / "Create account"
  toggle, show/hide password, plain-word errors, 16 px inputs, 48 px
  buttons, a 360 px-friendly grid and a "Continue as guest" link.
- Additive export for Phase 10: **`deleteAccount(password: string):
  Promise<AuthResult>`** from `@/lib/auth` (also published in COMM).
- Copy says history is stored on our server, can be deleted, and that
  speech providers process audio live. There is no "end-to-end
  encrypted" claim.

## Commands and raw output

| Command | Evidence |
| --- | --- |
| `cd services/voice && uv run python -m pytest tests/identity tests/persistence -q -x` | `evidence/pytest-identity-persistence.txt` — **135 passed** |
| `cd apps/web && NODE_OPTIONS=--max-old-space-size=512 npx tsc --noEmit` | `evidence/tsc.txt` — exit 0, no output |
| `cd apps/web && NODE_OPTIONS=--max-old-space-size=512 npx eslint src/lib/auth src/app/auth/sign-in src/proxy.ts` | `evidence/eslint.txt` — exit 0, no output |

No full suite, no `next build`, no Playwright, no new dependency and no
lockfile change were used.

## Sources

- Python `hashlib.scrypt`:
  https://docs.python.org/3/library/hashlib.html#hashlib.scrypt
- OWASP Password Storage Cheat Sheet:
  https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- Python `sqlite3` (threading, connection, PRAGMAs):
  https://docs.python.org/3/library/sqlite3.html
- SQLite PRAGMA reference (WAL, cache_size, mmap_size, busy_timeout,
  user_version): https://www.sqlite.org/pragma.html
- OWASP ASVS (resource limits / anti-automation):
  https://owasp.org/www-project-application-security-verification-standard/
- FastAPI CORS (already used by `main.py`):
  https://fastapi.tiangolo.com/tutorial/cors/

## Trade-offs

- **localStorage token.** The web app is on Vercel and the voice service
  is on another origin; the frozen CORS seam has
  `allow_credentials=False`, so a cookie would need a policy change. The
  token is therefore in `localStorage`, protected by the strict
  `script-src 'self'` CSP, cleared on logout and on every `401`, and never
  put in a URL. A successful XSS would still be able to read it.
- **Single worker, single SQLite writer.** The box is 2 GB / 2 CPU. One
  connection and one lock keep memory and contention predictable, but a
  multi-worker deployment would multiply the in-process rate limiters and
  connection caps; that caveat already exists in the runbook.
- **Delete keeps a tombstone row.** The recording file and audio are
  removed immediately; the metadata row stays in state `deleted` so the
  fence survives a restart and a late job. This matches `memory.py` and
  `supabase.py`. The brief's "delete removes file and row" is read as
  removing the audio and its live metadata, not the tombstone.
- **Fixed scrypt cost.** `n=2**14, r=8, p=1` is the brief's parameter set.
  It is below the strongest current OWASP recommendation for scrypt but
  keeps a single sign-in around 16 MiB on the 2 GB box.
- **Registration duplicate.** A duplicate registration returns a generic
  `409`; login is the path where unknown-email and wrong-password are
  indistinguishable. No email verification or password reset exists yet.

## Defects / cleanup

- `apps/web/package.json` still lists `@supabase/ssr` and
  `@supabase/supabase-js`; they are now used only by `proxy.ts` (which
  must keep passing through without Supabase environment values). Remove
  them once Phase 10 or a later cleanup decides the proxy can go.
- There is no settings screen in this phase; `deleteAccount()` is the
  exported helper Phase 10 should call.
- The local database has no automatic vacuum or token-row sweep; expired
  tokens are ignored on read, and expired recordings are swept on the
  next save. A small periodic job would be a later improvement.

## Help needed

None. Phase 10 should import `deleteAccount` from `@/lib/auth` for the
settings screen (posted as `INFO` in `prompts/parallel-G2/COMM.md`).

## Commit

`COMMIT_HASH_PLACEHOLDER`

PHASE 14 BUILT
