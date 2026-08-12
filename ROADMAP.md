# cairn-mail Roadmap

Product of a full codebase review (2026-08-12): five parallel deep-dives over the
sync/provider core, API security, frontend/PWA, AI + send pipeline, and
infra/tests/packaging. Findings are grouped into phases; each item is scoped to
become an OpenSpec change (suggested change name in parentheses). File:line
references are from commit `c7f1af2f`.

Deliberate non-goals, per existing decisions — not on this roadmap:

- Deep reconciliation stays IMAP-only. Gmail's stable-ID/label model breaks
  per-folder UID diffing. (The correct Gmail answer is history-based sync —
  Phase 3.)
- AI scope stays tagging + short reply pills on personal mail, small local
  model. No summarization, no full drafting, no bigger models.

---

## Phase 0 — Stop the bleeding (security + silent data loss)

Things that are broken *right now* in ways that lose mail, leak mail, or
destroy mail. Do these before anything else.

### 0.1 API authentication (`add-api-authentication`)

**Severity: critical.** There is no auth anywhere — no `Depends`, no token, no
session, on any route or the WebSocket (`src/cairn_mail/api/main.py`,
`api/websocket.py:213`). Any tailnet device (family laptop, compromised phone,
ACL mistake) — or a DNS-rebinding page in any browser on the tailnet, since
there's no Host check — can read all mail, send as Keith, or hit the
irreversible endpoints: `bulk/permanent-delete` (`api/routes/messages.py:382`),
`delete-all` (`:802`), `clear-trash` (`:862`).

**Decided design — implement exactly this, don't redesign:**

- **Mechanism: static bearer token.** Not Tailscale identity headers (revisit
  later if per-device identity ever matters), not sessions, not OAuth.
- **Server side:** ASGI middleware on the FastAPI app checks
  `Authorization: Bearer <token>` with `secrets.compare_digest` on every route
  except `GET /health` (leave that open for probes) and the static frontend
  assets. WebSocket handshake authenticates via `?token=` query param (browsers
  can't set headers on WS connects); reject with 4401-close before accepting.
- **Token source:** the service reads the token from a file whose path comes
  from env var `CAIRN_MAIL_TOKEN_FILE`. NixOS module gets a `tokenFile` option
  (agenix-compatible path) wired into the unit via `LoadCredential=` so the
  hardened service can read it; home-manager does NOT handle this secret.
  All three units (web, sync, deep) get it — sync doesn't serve the API but the
  web-route sync path and MCP both need the same token, keep it uniform.
- **Frontend:** on any 401, show a token-entry screen; store the token in
  localStorage; axios interceptor attaches the header; WS URL appends the query
  param. No login/logout ceremony beyond that — single user.
- **MCP server:** reads `CAIRN_MAIL_API_TOKEN` (literal) or
  `CAIRN_MAIL_TOKEN_FILE` (path) from its environment and attaches the header
  in its HTTP client (`mcp/server.py:17`).
- **DNS rebinding:** `TrustedHostMiddleware` allowing `localhost`, `127.0.0.1`,
  and hostnames from a new module option `allowedHosts` (default includes the
  machine's Tailscale FQDN).
- Also in this change: stop returning `str(e)` in 500s everywhere
  (`messages.py:178` et al.) — log it, return generic.

### 0.2 Fix IMAP keyword write-back (`fix-imap-keyword-detection`)

**Severity: critical — a core feature is silently a no-op.**
`providers/implementations/imap.py:83-90` gates keyword support on `"KEYWORD"`
appearing in the CAPABILITY string. That's not a real capability token; support
is advertised via `PERMANENTFLAGS (... \*)` in the SELECT response. Result:
`update_labels()` (imap.py:945-949) enters "read-only mode" on essentially
every IMAP server and AI tags never reach the server. Also check the status of
the two `UID STORE` calls (imap.py:967/975) — failures are currently swallowed.

### 0.3 Bcc delivery (`fix-bcc-delivery`)

**Severity: critical.** `email/mime_builder.py:176-177` omits the Bcc header
("handled separately in SMTP") but nothing handles it: `send.py:99` passes raw
MIME, and `imap.py:1294-1297` re-derives envelope recipients from To/Cc/Bcc
headers — Bcc isn't there. Bcc recipients never receive mail; the sender sees
success. Fix: pass an explicit envelope recipient list (to+cc+bcc) through
`provider.send_message`. While in there: `imap.py:1295-1297` comma-splits
headers — `"Calvelli, Keith" <x@y>` produces garbage RCPT entries; use
`email.utils.getaddresses`.

### 0.4 Sync window can lose mail (`fix-sync-window-semantics`)

**Severity: high; permanent loss on Gmail.** Two compounding bugs:

- `sync_engine.py:186-189` passes UTC `last_sync`; IMAP formats it as a
  date-granular `SINCE` compared against server-local INTERNALDATE
  (imap.py:534-537), Gmail as `after:YYYY/MM/DD` in account-local time
  (gmail.py:146-150). Messages near the day boundary fall out of the window.
  IMAP recovers via nightly deep reconcile; Gmail never does.
- `sync_engine.py:329-330` advances `last_sync = now()` even when stores failed
  or the fetch was truncated at `max_results` (imap.py:552-557 keeps newest N) —
  the "deferred to a later sync" log line is false.

Fix: subtract ~1 day of slack from `since` (dedup makes refetch harmless), and
don't advance `last_sync` past truncation/failures. Update
`openspec/specs/sync-engine/spec.md:222` to match reality.

### 0.5 Web sync must honor the sync lock (`fix-web-sync-lock`)

**Severity: high; spec violation.** Only the CLI takes `sync_lock`
(`cli/sync.py:130`). `api/routes/sync.py` (`_sync_account_blocking`) never
acquires it, so UI/IDLE-triggered syncs race the systemd timer. With no claim
state on pending ops (see 1.3), both processes read the same `pending` rows and
execute provider ops twice — double `move_to_trash` on IMAP duplicates mail in
Trash. Violates spec.md:167-189 (Concurrency Lock).

### 0.6 Gmail: token expiry crash + invisible Trash (`fix-gmail-token-and-trash`)

- `credentials.py:99-101` forces tz-aware expiry; google-auth's `expired`
  compares against naive `utcnow()` → `TypeError` (gmail.py:87) whenever the
  token file contains `token_expiry` — which `authenticate()` writes after the
  first refresh (gmail.py:101-111), poisoning the file. Normalize to naive UTC.
- `gmail.py:146` queries `in:all -in:draft -in:spam`; All Mail excludes Trash,
  so mail trashed in another client never enters the local DB. Use
  `in:anywhere -in:drafts -in:spam`.

### 0.7 Print-window XSS (`fix-print-window-xss`)

**Severity: high; independent of 0.1.** `MessageDetail.tsx:340-418` and the
duplicate in `MessageDetailPage.tsx:465-507` interpolate `subject`,
`from_email`, and raw `body_text` into `document.write()` unescaped. The
`about:blank` print window inherits the app origin, so a crafted email subject
executes script that can call the API. HTML-escape everything interpolated;
sanitize the `body_text` branch too. (Dedup of these two files is 2.5.)

---

## Phase 1 — Correctness (bugs users will hit)

### 1.1 Connection pool + folder-state races (`fix-imap-connection-races`)

- `connection_pool.py:124-150`: concurrent acquire orphans the in-use
  connection and can hand the same imaplib socket to two threads after a
  mismatched `release_connection()` (:155-170). Track per-connection identity
  or a per-account connection list.
- `imap.py:48` caches `_current_folder` but `authenticate()`/`release()` never
  reset it — a swapped connection no-ops the SELECT and subsequent UID commands
  fail or hit the wrong folder. Reset to `None` on authenticate/release/close.

### 1.2 Confidence gating for destructive AI actions (`add-confidence-gating`)

`sync_engine.py:614-618` auto-archives on raw LLM output; `ai_classifier.py:247-248`
does no bool coercion, so string `"false"` is truthy → archive. Confidence is
parsed, clamped, stored — and never consulted anywhere. Fix: strict `is True`
coercion; gate archive (and junk tagging) on a confidence floor. Related:
JSON-parse failures currently become a permanent `personal/0.5` classification
(`ai_classifier.py:283-292`) — raise instead so sync retries next cycle.

### 1.3 Pending-operation claim state (`add-pending-op-claiming`)

No `in_progress` status exists. Consequences: cancel-pairs race the executing
worker (`database.py:1330-1356` vs `sync_engine.py:647-651`) — a `restore` can
be swallowed while the trash still executes; a crash mid-op re-runs
non-idempotent trash (duplicate in Trash); a provider-delete-succeeded /
local-delete-failed retry dead-ends (`sync_engine.py:683-694`, worse on Gmail
where delete-404 raises, `gmail.py:595-601`). Add a transactional claim state;
only cancel ops still `pending`; treat already-gone as success on both
providers.

### 1.4 Reply threading headers (`fix-reply-threading-headers`)

`mime_builder.py:189-193` sets In-Reply-To/References from the *internal* id
(`account:INBOX:1234` — filled in by `Compose.tsx:341` and `mcp/tools.py:375`).
Replies leak internal IDs and don't thread in recipients' clients. Store the
RFC822 Message-ID on `Message` (a real column — it's currently smuggled through
`thread_id` for IMAP, sync_engine.py:660-670), use it for In-Reply-To, and
build References = parent's References + parent's Message-ID.

### 1.5 Frontend compose/reply/forward bugs (`fix-compose-flows`)

- Attaching to a new draft always fails — stale `draftId` closure
  (`Compose.tsx:429-435`); use `saveDraft()`'s return value.
- Forward button forwards nothing — omits `forward_from`
  (`MessageDetail.tsx:282-289`, `MessageDetailPage.tsx:389-397`); the keyboard
  `f` path does it right, copy that.
- Reading-pane `r` reply navigates with a `?reply=` param Compose doesn't read
  (`MessageList.tsx:367`) → blank compose.
- Duplicate-draft race: two quick blur-saves both take the create path
  (`Compose.tsx:346-357`); serialize with an in-flight ref.
- No Reply-All anywhere; original Cc recipients are dropped. Add it.

### 1.6 WebSocket reconnect (`fix-websocket-reconnect`)

`useWebSocket.ts:155-158` never reconnects after close. With
`refetchOnWindowFocus: false` and 5-min staleTime, one laptop sleep = stale UI
until manual reload. Exponential backoff on close + reconnect on
`online`/`visibilitychange`; surface the disconnected state (nothing consumes
`isConnected` today). Also close CONNECTING sockets in effect cleanup
(:161-166).

### 1.7 Smart replies: wrong config, blocks event loop (`fix-smart-replies-plumbing`)

`messages.py:1045-1051` reads `app.state.ai_config` (never set — startup sets
`app.state.classifier`) so it always uses defaults pointed at the wrong
endpoint, and calls the synchronous `generate_replies` (30s `requests.post`)
directly in an async handler — a slow LLM stalls the whole app including
WebSockets. Reuse `app.state.classifier` and wrap in `asyncio.to_thread` (the
maintenance route already does this correctly).

### 1.8 Unify the tag taxonomy (`fix-tag-taxonomy-drift`)

The web startup path classifies against the merged 35-tag taxonomy
(`api/main.py:275-283`); the systemd timer sync (`cli/sync.py:64-72`) and the
web sync route use deprecated `get_custom_tags()` → the classifier's private
9-tag default (`ai_classifier.py:35-45`). Same mailbox, different taxonomies by
code path — and `_normalize_tags` strips feedback-corrected tags outside the
active set, so the DFSL loop can't converge. Use `ConfigLoader.get_merged_tags()`
everywhere; delete the classifier-local defaults. Also collapse the three
conflicting default AI configs (`ai_classifier.py:24`, `config/loader.py:65`,
`cli/sync.py:67`) to one source of truth, and honor `ai.enable=false` in the
sync paths (today only web startup respects it; a down LLM costs a
timeout-per-message every 5 minutes with no circuit breaker).

### 1.9 SQLite multi-process hygiene (`fix-sqlite-busy-timeout`)

Two processes write the same WAL DB with no `busy_timeout`
(`database.py:18-25`). Add `PRAGMA busy_timeout=30000` (or connect_args
timeout). Small, prevents "database is locked" flakes during deep reconcile.

### 1.10 SMTP failure visibility (`fix-smtp-error-handling`)

- Retry loop never retries: `_connect` wraps failures in `RuntimeError`
  (`smtp_client.py:129-137`) which escapes the `(SMTPException, OSError)`
  catch on attempt 1.
- Partial recipient refusals silently discarded (`smtp_client.py:64` ignores
  `send_message`'s refused-dict) — some recipients never get mail, UI says sent.
- Sent-folder APPEND failure is only a log warning (`imap.py:1334-1337`).

---

## Phase 2 — Foundations (so Phases 0-1 don't regress)

### 2.1 One migration system (`consolidate-db-migrations`)

Alembic is dead in production: the app never calls it, `alembic.ini`/versions
aren't packaged (the `Path(__file__).parent×4` resolution in `db/migrate.py:13`
breaks in site-packages), the FTS5 table from migration 002 has never existed
in prod, and `alembic_version` is unstamped so drift is unmeasurable. Meanwhile
`Database.__init__` does `create_all` + hand-rolled ALTERs
(`database.py:44-94`).

**Decided: delete alembic, bless the ad-hoc mechanism.** For a single-user
SQLite DB, alembic is machinery without a payoff. Concretely:

- Delete `alembic/`, `alembic.ini`, `src/cairn_mail/db/migrate.py`, and the
  alembic dependency from pyproject.
- Promote `Database._run_migrations` (`database.py:51-94`) to the documented,
  tested mechanism: `create_all` for new tables, idempotent
  `PRAGMA table_info` + `ALTER TABLE` checks for column adds, run at every
  startup. Add a short section to `docs/ARCHITECTURE.md` describing it and the
  rule for adding a migration step.
- Salvage what alembic had that create_all doesn't cover before deleting:
  the FTS5 virtual table + triggers from `alembic/versions/002` move into
  `_run_migrations` as an idempotent `CREATE VIRTUAL TABLE IF NOT EXISTS` +
  trigger-creation step. That makes FTS5 real in prod and removes 3.6's
  dependency on this change's *timing* — but do the table creation here so
  3.6 is purely a query/UI change.
- Add tests (part of 2.2): fresh-DB bootstrap, and upgrade-from-old-schema
  (fixture DB missing the newer columns).

### 2.2 Tests for the sync engine + CI (`add-sync-tests-and-ci`)

Coverage is ~2-3% — one file, `tests/ai/test_ai_classifier.py`. The subsystem
that shipped the last data-loss bug (sync engine, 834 lines) has zero tests, as
do database.py (1920 lines), both providers, all 14 route modules, and the
pending-op queue. Priorities: sync-engine deletion/reconciliation semantics,
pending-op lifecycle (including the Phase 1.3 claim state), migrations, then
API routes via TestClient + tmp SQLite. Plus a minimal GitHub Actions workflow:
`nix build` + pytest + ruff — today a broken commit is discovered by the
production rebuild. Move mandatory `--cov` out of `addopts`
(`pyproject.toml:113-117`) so pytest runs without pytest-cov.

### 2.3 Fix the dev shell (`fix-dev-shell`)

devShell uses python311 while the package builds 3.13 (`flake.nix:125` vs
`:50`); the committed `.venv` symlinks a GC'd store path so tests can't run in
this checkout; `pip install -e .[dev]` omits the api extra so `cairn-mail web`
can't run in dev; `python-multipart` exists only in flake.nix, not pyproject.
Align devShell Python with the package, install `.[all]`, promote
fastapi/uvicorn to core deps (they're unconditionally in the Nix closure
anyway), add nodejs for the frontend, and rewrite `docs/DEVELOPMENT.md` which
documents a shell that doesn't exist.

### 2.4 Operational visibility + backups (`add-sync-failure-alerting`)

- `cairn-mail sync run` exits 0 even when every account fails
  (`cli/sync.py` catches, prints, continues) — the oneshot service always
  reports success. Exit non-zero on any account failure; add `OnFailure=` in
  the NixOS module.
- No DB backup story at all. WAL SQLite is unsafe to copy live. Add a systemd
  timer doing `sqlite3 .backup` (or litestream), and document it.
- `list_folders` swallowing failures makes deep reconcile "succeed" doing
  nothing (`imap.py:245-273` → `sync_engine.py:441-449`); let it raise.

### 2.5 De-duplicate MessageDetail (`dedupe-message-detail`)

`MessageDetailPage.tsx` (~900 lines) re-implements `MessageDetail.tsx` with
drift already visible (print sanitizers differ, the two `handleForward`s
diverged — that's how bug 1.5 happened twice). The page should render
`<MessageDetail>` plus page chrome. Do this before more drift accumulates; it
also halves the surface for the 0.7 XSS fix.

### 2.6 systemd hardening + service scope (`harden-systemd-units`)

Baseline is decent (NoNewPrivileges, ProtectSystem=strict). Add the cheap
rest: PrivateDevices, ProtectKernel*, RestrictNamespaces, RestrictSUIDSGID,
LockPersonality, RestrictAddressFamilies, SystemCallFilter=@system-service.
Consider a dedicated user/group over `Group=users`, and BindReadOnlyPaths for
secrets instead of read-only all of `$HOME`. Also: OAuth token files outside
`~/.local/share/cairn-mail` silently fail refresh write-back under
`ProtectHome=read-only` (`credentials.py:117` failure path only logs) — add the
token dir to ReadWritePaths via a module option or document the constraint.
Remove or fix the no-op `openFirewall` (uvicorn binds 127.0.0.1 regardless,
`modules/nixos/default.nix:40-44` vs `cli/web.py:17-22`).

### 2.7 API/input hardening (`harden-api-inputs`)

Follow-ons to 0.1: unbounded attachment upload (whole file into memory, no
size cap — `attachments.py:55`); push-subscription endpoint stored verbatim and
POSTed to on every sync (SSRF-ish, `push.py:41-67` → `push_service.py:115`) —
validate against known push-service hosts; CRLF validation on compose header
fields (`mime_builder.py:170-180`); run DOMPurify *inside* `EmailContent`
instead of trusting callers (`EmailContent.tsx:387` — the header comment
already claims it does).

---

## Phase 3 — Features (daily-driver gaps)

### 3.1 Gmail history-based sync (`add-gmail-history-sync`)

The right fix for every acknowledged Gmail gap (read-state drift, server-side
deletes, moved mail — spec.md:116 calls it "pending a label-aware design").
`users.history.list` with a stored `historyId` delivers adds/deletes/label
changes incrementally, no per-folder UID diffing — fully consistent with the
deep-sync-is-IMAP-only decision.

**Design constraints (pinned — the openspec design artifact fills in the rest
within these):**

- Store `last_history_id` per Gmail account (new column on the account/sync
  state, not reuse of `last_sync`). Seed it from the profile
  (`users.getProfile().historyId`) after the first full fetch.
- Each sync: `history.list(startHistoryId=...)`, paginate, apply in order:
  `messagesAdded` → fetch + store; `messagesDeleted` → delete local row;
  `labelsAdded`/`labelsRemoved` → map to local state. Label mapping:
  `UNREAD` ↔ `is_unread`; folder derives from `TRASH` > `SPAM` > `SENT` >
  `DRAFT` > `INBOX` precedence, else `archive`. Never touch AI/user tags from
  labels.
- **Local pending ops win:** skip applying a history change to any message
  with a pending op targeting the same field (same rule as 1.3's claim state).
- **Expiry fallback:** `history.list` returns 404 when the historyId is too
  old (Gmail keeps roughly a week). On 404: run the existing full
  date-window fetch once, then re-seed `historyId` from the profile. Log it,
  don't error.
- Batch message fetches (Gmail batch HTTP endpoint) instead of N ×
  `messages().get`.
- The existing `after:` date-window path stays as the fallback and
  first-sync path — history sync replaces the steady-state incremental only.

Stopgap that can ship independently (`fix-gmail-flag-drift`): incremental sync
applies provider `is_unread`/folder for messages with no pending local op
(`sync_engine.py:204-211` currently always prefers local, so Gmail read-state
drifts forever).

### 3.2 IMAP protocol fidelity (`improve-imap-fidelity`)

Bundle of baseline IMAP-client requirements, roughly in value order:

- **UIDVALIDITY tracking** — currently ignored; a folder rebuild silently makes
  every stored uid point at the wrong message, including pending deletes.
- **UID EXPUNGE (UIDPLUS)** instead of blanket `EXPUNGE` (imap.py:804, 841,
  924) which destroys other clients' \Deleted-but-not-expunged mail.
- **Charset-aware body decoding** — use `part.get_content_charset()`
  (imap.py:1144-1177 blind-tries utf-8/latin-1 → mojibake for everything
  else; gmail.py:326 hard-codes utf-8 and `pass`es failures → body dropped).
- **Modified-UTF-7 folder names** (RFC 3501 §5.1.3) + skip `\Noselect`.
- **Restore to `original_folder`** — the column exists (migration 003), the
  providers ignore it and restore everything to INBOX (imap.py:891,
  gmail.py:543).
- **Deep-reconcile scalability**: chunk the comma-joined `UID FETCH` command
  (imap.py:627), batch the per-message flag updates (sync_engine.py:541-552),
  and consider header-only fetch for the add path so deep can't hold the lock
  for hours (sync_engine.py:491-516).
- Deep reconcile flag pass should skip messages with pending mark_read/unread
  ops (`sync_engine.py:538-552` currently clobbers unsynced local state).
- Later: CONDSTORE/QRESYNC for real incremental flag sync; XOAUTH2 for
  IMAP (enables O365).

### 3.3 Threading (`add-conversation-threading`)

IMAP `thread_id` is the message's own Message-ID (imap.py:1071) — replies never
share a thread, so conversation view can't group IMAP mail. Parse
References/In-Reply-To at sync time (pairs with the 1.4 column), group the
message list by conversation, and fix ThreadView's cache invalidation
(`useMessages.ts:39-46` — the `['thread', id]` key is invalidated by nothing)
and its eager body-fetch of collapsed messages (`ThreadView.tsx:40`).

### 3.4 Compose/send quality of life (`add-undo-send`, `improve-compose`)

- **Undo send**: 15-30s cancellable delay. Fits the existing draft model
  server-side; the toast system already supports action buttons.
- **Archive**: no archive concept exists anywhere; `e` is table stakes.
- Drag-drop + paste-image attachments, upload progress, size feedback
  (`Compose.tsx:846` is a hidden file input only).
- Inline-image (cid/multipart-related) support in mime_builder.
- Draft autosave: last-write-wins with no revision guard (`drafts.py:198-241`),
  and `update_draft`'s only-if-not-None semantics can't clear a field.

### 3.5 PWA: offline + update flow (`fix-pwa-offline`)

The existing `add-pwa-background-sync` openspec change covers part of this.

- No offline action queue at all — SwipeableMessageCard even toasts "will be
  queued" and drops the action (`SwipeableMessageCard.tsx:48-55`). Workbox
  BackgroundSyncPlugin on mutating `/api/*` routes, or an app-level outbox.
- Offline deep links fail: `sw.ts` has precaching but no `NavigationRoute`
  fallback — the installed app can't open `/messages/<id>` or the `/compose`
  shortcut offline.
- Deploy mid-session force-reloads the tab within 60s (`sw.ts:23` skipWaiting +
  reload on controllerchange) — switch to the prompt-based update flow.
- `navigator.onLine` is meaningless over Tailscale; treat WS-disconnected as
  offline or probe `/health`.

### 3.6 Real search (`add-fts-search`)

The FTS5 table lands as part of 2.1; this change is queries and UI only.
Replace the in-Python substring filter (`messages.py:118-127`), then surface search
operators (from:, has:attachment), debounce the search box (currently one
request per keystroke, each prefix persisted to IndexedDB for 7 days —
`TopBar.tsx:166`, `App.tsx:50-56`), and exclude search queries from cache
persistence.

### 3.7 Multi-account UX (`add-account-switcher`)

The store supports `selectedAccount` and MessageList filters on it, but no UI
ever sets it. Add a switcher in the Sidebar/TopBar.

---

## Phase 4 — Polish

- **Docs refresh** (`update-docs`): CLAUDE.md deploy section (stale — deploy
  goes through the cairn distro input now); CLI_REFERENCE missing `sync deep`,
  `mcp`, `auth setup-gmail`; CONFIGURATION missing `sync.deep.*` options;
  DEVELOPMENT.md describes a nonexistent shell (covered by 2.3);
  action-tags spec still says "Ollama"; delete or rewrite
  `scripts/setup_test_account.py`; align spec.md:228 defaultArgs precedence
  with code (or vice versa).
- **Dead code sweep** (`remove-dead-code`): duplicate `get_feedback_stats`
  (database.py:737 shadowed by :1182), unused `store_feedback`, dead Gmail
  deep-reconcile surface (gmail.py:185-285), unreachable else-branch
  (sync_engine.py:461-468), `theme.ts` (imported nowhere), stack-trace log on
  every `move_to_trash` (database.py:370-380), `console.log`s in hooks,
  duplicated ~80-line provider bootstrap in cli/sync.py vs routes/sync.py,
  `ConfigLoader.get_actions_config` (unused, and every call site re-implements
  it), `mcp info` hardcoding 8 of 14 tools (cli/mcp.py:63), `cli/status.py`
  loading 100k rows with N+1 queries.
- **Dependency bumps** (`bump-frontend-deps`): axios ≥1.8.2 (CVE-2025-27152),
  dompurify floor ≥3.2.4 (two CVEs below), drop obsolete `@types/dompurify`,
  ESLint 8 is EOL. Backend: `nix flake update` (nixpkgs pin is 7 months old).
- **Frontend performance/a11y** (`improve-frontend-quality`): Zustand
  whole-store subscriptions re-render every card per keystroke
  (`MessageList.tsx:47-60`); 2s `/sync/status` polling forever alongside a
  WebSocket that broadcasts the same events (`useStats.ts:43`); message cards
  invisible to screen readers (`MessageCard.tsx:128` — no role/tabIndex);
  `closest('a')` for link interception (`EmailContent.tsx:251` misses clicks on
  children of anchors); clear `selectedMessageId` on folder change; silent
  attachment-download failures should toast.
- **AI feedback-loop refinement** (in scope): record feedback when manually
  tagging unclassified messages (`messages.py:484-492` skips it); unify the
  two reclassify implementations (API wipes action tags violating spec:22-25;
  CLI ignores `has_user_feedback`); rely on the gateway's structured error
  field instead of sniffing output text for "error" (retries non-idempotent
  tools today, `gateway_client.py:114-131`).

---

## Suggested sequencing

Phase 0 items are independent of each other — they can be parallel openspec
changes. 1.3 (claim state) should land with or right after 0.5 (web sync
lock); they close the same race from two sides. 2.1 (migrations) creates the
FTS5 table, so it precedes 3.6 (FTS search) but 3.6 no longer depends on any
migration machinery. 2.5 (dedupe MessageDetail) shrinks 0.7's blast radius —
fine in either order, but don't fix the XSS in both copies and then dedupe.
2.2 (tests) should grow with each Phase 0/1 fix rather than as a separate
big-bang: every bug above is a test case first.

Model note: 0.1 (auth), 2.1 (migrations), and 3.1 (Gmail history) have their
design decisions pinned above — implement as specified, don't redesign. The
remaining Phase 0/1 items and the Phase 4 sweeps are mechanical given the
file:line references.
