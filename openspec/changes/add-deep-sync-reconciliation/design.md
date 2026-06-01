## Context

The 5-minute incremental sync (`SyncEngine.sync()`) is intentionally windowed: it issues `IMAP SEARCH SINCE <last_sync_day - 1>` so per-folder reconciliation only touches messages dated within that window. The window is bounded that way because (a) IMAP `SINCE` is day-granular and server clocks drift, so a one-day back-off prevents false-positive purges, and (b) walking every UID in every folder on a 5-minute cadence is wasteful when 99% of the time nothing has changed outside the window.

The cost is that anything older than the window is invisible to incremental sync. State drift accumulates silently:
- Server-side deletion of old messages (retention policy, manual archive cleanup on another client, third-party tool).
- Server-side moves outside the window (message moved from inbox → archive three weeks ago on another client; local DB still says inbox).
- Read/unread changes on old threads.
- Label / flag changes on old messages.

The recent `0bc75329 fix: stop the sync purge from eating the historical archive` and `aa0daacd fix: purge sweep reconciles folders that came back empty` are both adjacent symptoms — the local/provider divergence pattern is a real one, and right now nothing periodically asks the provider for the full picture.

The empty-sync-backoff bug that motivated this change took ~11 hours to surface, and was only noticed because the user happened to look at logs. A weekly deep reconciliation would have noticed the same drift the next time it ran.

## Goals / Non-Goals

**Goals:**
- Periodically (weekly) reconcile the full per-folder UID set between provider and local DB, ignoring the SINCE window.
- Reconcile read/unread and label state for messages that exist on both sides.
- Survive enumeration failures without mass-deleting local data. The historical-archive bug is a strong prior — assume it will happen again and design for it.
- Coexist safely with the 5-minute sync timer. No double-sync, no races.
- Cheap enough to run weekly without thinking about it (a few seconds per account in steady state).

**Non-Goals:**
- Re-fetching message bodies. Bodies are immutable on the provider side; if a body exists locally for a UID that still exists remotely, it does not need refetching.
- Re-running AI classification. The existing `sync reclassify` command already covers that, and conflating it with reconciliation muddies cost expectations.
- Per-message label diffing for Gmail-style cross-folder semantics. Deferred until we observe real drift in that dimension.
- SQLite vacuum / compact. Different concern, different cadence, different tool.
- Replacing the 5-minute incremental sync. Deep reconciliation augments it; it does not subsume it.

## Decisions

### 1. New `SyncEngine.deep_reconcile()` method, not a flag on `sync()`

**Decision:** Add a separate method instead of `sync(deep=True)`.

**Rationale:** The two operations have meaningfully different invariants. `sync()` maintains the empty-sync backoff counter, runs AI classification, processes pending operations, fires push notifications, and updates `last_sync`. `deep_reconcile()` does none of those — it is a structural diff. Wedging both code paths into one method via a flag would force every existing call site to reason about both shapes. Separate methods keep each one honest.

**Alternatives considered:**
- `sync(deep=True)` — rejected for the above reasons.
- Standalone script outside `SyncEngine` — rejected because the IMAP connection pool, provider abstraction, and DB session lifecycle all live behind `SyncEngine` already.

### 2. Use `UID SEARCH ALL` + `UID FETCH FLAGS` per folder

**Decision:** Two IMAP round trips per folder: `UID SEARCH ALL` to get every UID, then `UID FETCH <set> (FLAGS)` to get flags for the union of local and remote.

**Rationale:** Both calls are cheap on the wire. `UID SEARCH ALL` returns a flat list of integers; a 50k-UID folder is well under a second. `UID FETCH FLAGS` returns no body data. We do **not** issue a full `UID FETCH (ENVELOPE BODY)` — for UIDs we already have locally, we trust the stored envelope; for UIDs new to us, we fall back to the existing incremental-fetch path for that specific UID range so envelope/header storage stays in one code path.

**Alternatives considered:**
- `UID SEARCH MODSEQ` for servers supporting CONDSTORE — faster but unavailable on a non-trivial fraction of IMAP servers, and the deep sync is weekly and small, so the speed delta does not justify the complexity.
- Reuse the existing `fetch_messages()` per folder with no SINCE — works but pulls full envelopes for messages we already have. Wasteful and slow on large folders.

### 3. Per-folder safety rail against empty-enumeration

**Decision:** Before purging any local rows in a folder, require that `len(server_uids) > 0` OR `len(local_rows) <= EMPTY_FOLDER_PURGE_THRESHOLD` (proposed default: 5). If `server_uids` is empty and local has more than the threshold, abort that folder with an error-level log and skip purges for that folder. Reconciliation of read/unread/flags is also skipped for that folder (there is nothing to reconcile against).

**Rationale:** The `0bc75329` commit explicitly fixed the case where a sync purge ate the historical archive. The underlying cause was the same shape: a folder enumeration silently returned empty, and we treated that as "all local rows are stale." A populated local folder going from N rows to 0 server UIDs in a single deep sync run is almost always an enumeration failure, not a real deletion. We make that a loud abort, not a silent purge.

The threshold exists for the genuinely-empty-folder case: a user actually deleting the last five drafts in their Drafts folder should not require manual override.

**Alternatives considered:**
- No threshold, hard rule "never purge a folder where server returns empty" — rejected because then a legitimately emptied folder never gets reconciled.
- Higher threshold (e.g. 50) — could mask real deletions on small folders. 5 is a reasonable "if it's bigger than a manual cleanup, something is wrong" line.

### 4. Advisory lock against the 5-minute timer

**Decision:** Use a file-based advisory `fcntl` lock at `<db_dir>/sync.lock` — i.e. beside the database the lock protects. Both the 5-minute `sync run` and `sync deep` acquire it non-blocking on entry; if it is held, the entrant logs and exits cleanly.

**Rationale:** Two concurrent sync processes hitting the same DB and the same IMAP provider connection pool is asking for trouble — provider connections, transactional sync state, and the empty-sync counter all assume single-writer. A non-blocking file lock is the simplest correct mechanism and does not require DB schema changes. The `fcntl` lock is released by the kernel when the holder exits, so a crash never wedges the next run, and a stale lock file on disk is harmless because the lock lives on the open fd, not on file existence.

**Lock path — original `/run/cairn-mail` plan was wrong (corrected during verification).** The first cut used `/run/cairn-mail/sync.lock` backed by a systemd `RuntimeDirectory=cairn-mail`, with an XDG fallback for non-root. Live testing showed this does NOT provide mutual exclusion: a manual `cairn-mail sync deep` runs without the systemd RuntimeDirectory, so `/run/cairn-mail` doesn't exist and it falls back to `$XDG_RUNTIME_DIR` — a *different* inode from the one the systemd timer uses. The two ran fully concurrent, both writing the DB. Worse, `RuntimeDirectoryPreserve=no` (the default) means each oneshot removes `/run/cairn-mail` on exit, so even in the all-systemd case the incremental finishing mid-deep can unlink the lock dir out from under the deep run. Putting the lock beside the DB gives one stable path for every invocation mode, with no RuntimeDirectory lifecycle to fight. The data dir is already in the units' `ReadWritePaths`, so `ProtectSystem=strict` is satisfied without extra directives.

**Alternatives considered:**
- `/run/cairn-mail` + `RuntimeDirectory` — rejected after verification (see above).
- DB row lock — works but introduces a "what if the row is stale from a crashed sync" recovery problem.
- systemd unit dependency / `Conflicts=` directive — only partial protection because nothing stops a manual `cairn-mail sync deep` invocation from racing the timer.

### 5. Sequential per-folder, sequential per-account

**Decision:** Walk folders one at a time, accounts one at a time. Do not parallelize.

**Rationale:** Weekly cadence at single-digit-seconds-per-account budget makes parallelism unnecessary. Sequential simplifies the safety rail (an abort in one folder cannot affect another in flight) and avoids piling concurrent IMAP connections onto the same provider during a maintenance window. If profiling later shows it matters, parallelize then.

### 6. Schedule via systemd timer, not in-process scheduler

**Decision:** New `cairn-mail-sync-deep.timer` and `cairn-mail-sync-deep.service` units. Default `OnCalendar=Sun 03:00`. Module knob `services.cairn-mail.sync.deep.{enable, onCalendar}`.

**Rationale:** Consistent with the existing `cairn-mail-sync.timer`. Reuses systemd's persistent scheduling, restart semantics, and journal logging. No need to invent a scheduler inside the long-running web service. The user runs NixOS — declarative timers are the native way to do this.

## Risks / Trade-offs

- **[Mass deletion via enumeration failure]** → Per-folder safety rail (decision 3). Loud error log when triggered; the run continues for other folders.

- **[Long-running first deep sync after a long drift period]** → Acceptable. Sequential is fine, and bodies are not refetched. Even a multi-thousand-UID folder reconciles in seconds because we only move UID lists and flag bits over the wire.

- **[Race with the 5-minute timer]** → Advisory lock (decision 4). The 5-minute timer is the more frequent process and tolerates skipping a cycle; deep sync wins the lock contention by happening at 03:00 when nothing else is running.

- **[Provider rate limits on accounts with many folders]** → Mitigated by sequential per-folder walking and the cheapness of `UID SEARCH ALL` + `UID FETCH FLAGS`. Gmail's IMAP is forgiving; generic IMAP servers vary but a serial folder walk at weekly cadence will not trip any documented limit.

- **[Drift in folders we never enumerate]** → If a folder exists on the server but is not in the provider's known-folder list (e.g., a folder created after last `list_folders()` cache fill), deep sync will not touch it. Mitigation: deep sync calls `list_folders()` fresh at the start of each run, bypassing the cache.

- **[The safety threshold of 5 is wrong]** → If it turns out users routinely have ≤5-message folders that genuinely empty themselves, we will see false aborts in logs and bump the threshold. Cheap to tune; making it a NixOS option from day one is overkill.

## Migration Plan

1. Land the code with the new timer **disabled by default** in the module (`services.cairn-mail.sync.deep.enable = false`). Existing deployments are unaffected.
2. Enable on Keith's `edge` first by setting `enable = true` in `nixos_config`. Watch one cycle. Confirm the safety rail does not abort spuriously and that reconciliation finds plausible drift counts in logs.
3. After one clean run, flip the module default to `enable = true`. Document in CHANGELOG.

Rollback: set `services.cairn-mail.sync.deep.enable = false` and rebuild. The 5-minute sync is untouched throughout — there is nothing to roll back at the DB or schema level.
