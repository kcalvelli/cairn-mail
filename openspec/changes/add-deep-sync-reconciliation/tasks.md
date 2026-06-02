## 1. Provider Surface

- [x] 1.1 Add abstract `list_all_uids(folder: str) -> set[str]` to `BaseEmailProvider` returning every UID in the named folder (no SINCE filter)
- [x] 1.2 Add abstract `fetch_flags(folder: str, uids: Iterable[str]) -> dict[str, set[str]]` returning IMAP flags keyed by UID
- [x] 1.3 Implement both methods in the IMAP provider using `UID SEARCH ALL` and `UID FETCH (FLAGS)` respectively
- [x] 1.4 Implement both methods in the Gmail provider — for `list_all_uids` use the messages.list API without a date filter, for `fetch_flags` use messages.get with `format=metadata` and labelIds-as-flags mapping. (Implemented to satisfy the abstract provider interface, but deep reconciliation does NOT call them: verification showed Gmail's stable-ID/label model breaks the per-folder "absence == deletion" diff — phantom adds and move-triggered purges. `deep_reconcile()` now gates on `provider.uses_imap_folders` and skips Gmail; these methods remain as the seed for a future label-aware design. See design.md decision 7.)
- [x] 1.5 Add a `fetch_envelope(folder: str, uids: Iterable[str])` helper used by deep reconciliation to hydrate newly-discovered server UIDs without invoking the AI classifier — reuse the existing message-parsing logic, just skip the classifier call site

## 2. Sync Engine: Deep Reconciliation

- [x] 2.1 Add `SyncEngine.deep_reconcile()` returning a `SyncResult`-shaped object with counts for `reconciled_folders`, `messages_added`, `messages_purged`, `flags_updated`, `safety_rail_aborts`
- [x] 2.2 In `deep_reconcile()`, call `provider.list_folders()` fresh (bypass any cache) so newly-created server folders are included
- [x] 2.3 For each folder, fetch server UIDs and local rows, compute three-way diff sets: `to_add`, `to_purge`, `to_reconcile_flags`
- [x] 2.4 Enforce the empty-folder safety rail: if `len(server_uids) == 0` and `len(local_rows) > EMPTY_FOLDER_PURGE_THRESHOLD` (constant `= 5`), log an `error` with account+folder and skip purges/flag reconciliation for that folder; count the abort
- [x] 2.5 For `to_add` UIDs, call `fetch_envelope` and persist rows via the existing `create_or_update_message` path; do NOT call the AI classifier and do NOT mark them as new for push notifications
- [x] 2.6 For `to_purge` UIDs, call `db.delete_message` per row
- [x] 2.7 For `to_reconcile_flags`, compare server `\Seen` flag against local `is_unread`; update local row when they disagree. Same shape for label/keyword drift if cheap; otherwise document the gap inline
- [x] 2.8 Do NOT touch `consecutive_empty_syncs`, do NOT touch `last_sync`, do NOT fire push notifications
- [x] 2.9 Process folders sequentially per account, accounts sequentially per run; an exception in one folder logs and continues to the next

## 3. Concurrency Lock

- [x] 3.1 Add a module `cairn_mail.sync_lock` providing a `with sync_lock(db_path):` context manager that acquires a non-blocking `fcntl.LOCK_EX | LOCK_NB` on `<db_dir>/sync.lock`. (Originally specced as `/run/cairn-mail/sync.lock` with an XDG fallback; verification showed that path diverges between manual and systemd invocations and never excludes them — moved the lock beside the DB so every entrant contends on one stable path. See design.md decision 4.)
- [x] 3.2 If acquisition fails, the context manager raises a `SyncLockHeld` exception with the holder's PID if readable
- [x] 3.3 Wrap the body of `cairn-mail sync run` in the lock; on `SyncLockHeld`, log info and `raise typer.Exit(0)` cleanly
- [x] 3.4 Wrap the body of `cairn-mail sync deep` in the lock; on `SyncLockHeld`, log info and `raise typer.Exit(0)` cleanly

## 4. CLI Subcommand

- [x] 4.1 Add `cairn-mail sync deep` subcommand in `cli/sync.py` accepting `--account` and `--db` flags consistent with `sync run`
- [x] 4.2 Subcommand resolves accounts (single or all), opens provider, calls `SyncEngine.deep_reconcile()`, prints a Rich summary table per account with the new counters
- [x] 4.3 Print a clear single-line summary on safety-rail aborts so they are visible in journal output

## 5. NixOS Module

- [x] 5.1 Add `services.cairn-mail.sync.deep` option block to `modules/nixos/default.nix` with `enable` (default `false` initially) and `onCalendar` (default `"Sun 03:00"`) sub-options
- [x] 5.2 Conditionally install `cairn-mail-sync-deep.service` (oneshot, `ExecStart=… sync deep`) and `cairn-mail-sync-deep.timer` (`OnCalendar=${cfg.deep.onCalendar}`, `Persistent=true`) when enabled
- [x] 5.3 ~~Add `RuntimeDirectory=cairn-mail` to both units so the lock file's parent dir exists on tmpfs~~ — dropped during verification. The lock moved beside the DB (decision 4), so no RuntimeDirectory is needed; the data dir is already in `ReadWritePaths`. Keeping a shared `RuntimeDirectory` would also have introduced an unlink race (`RuntimeDirectoryPreserve=no` removes the dir when either oneshot exits).

## 6. Verify and Roll Out

- [x] 6.1 Build locally via `nix build` (or whatever the project's CI invocation is) to confirm the module change parses
- [ ] 6.2 Push branch and rebuild `edge` with `services.cairn-mail.sync.deep.enable = true` in `nixos_config`
- [ ] 6.3 Manually invoke `sudo systemctl start cairn-mail-sync-deep.service` and read the journal — verify reconciliation counts look plausible and that the safety rail did not abort spuriously
- [ ] 6.4 Confirm the 5-minute timer continues firing without errors after the deep run completes
- [ ] 6.5 Once a clean run is observed on `edge`, flip the module default `enable` to `true`
- [x] 6.6 Update `CHANGELOG.md` with the new feature and the manual override path
