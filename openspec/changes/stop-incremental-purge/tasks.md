## 1. Remove the Incremental Purge

- [x] 1.1 Delete the purge block in `SyncEngine.sync()` — the `purge_cutoff` computation, the per-folder `fetched_ids_by_folder` gathering, the `truncated_folders` lookup, and the delete loop — replacing it with a comment documenting that the incremental sync is non-destructive by design
- [x] 1.2 Remove the now-dead `messages_purged` local and its constructor kwarg from `sync()` (the `SyncResult.messages_purged` field stays, defaulting to 0)
- [x] 1.3 Drop the unused `timedelta` import from `sync_engine.py`

## 2. Remove the Dead Purge Surface on the IMAP Provider

- [x] 2.1 Remove the `_last_queried_imap_folders` and `_truncated_imap_folders` tracking sets (init, per-round reset, and `.add()` call sites)
- [x] 2.2 Remove the `get_last_queried_imap_folders()` and `get_truncated_folders()` methods
- [x] 2.3 Keep the truncation `logger.warning` in `_fetch_from_folder`, reworded — truncation can no longer cause data loss, older messages are just deferred to a later sync
- [x] 2.4 Confirm no remaining references to the removed methods/sets anywhere in `src/`

## 3. Make Deep Reconciliation the Daily Deletion Owner

- [x] 3.1 Change the NixOS `services.cairn-mail.sync.deep.onCalendar` default from `Sun 03:00` to `*-*-* 03:00:00` (daily at 03:00)
- [x] 3.2 Update the module option description and surrounding comments to state that deep reconciliation is the sole mechanism that mirrors server-side deletions (incremental never purges)

## 4. Docs

- [x] 4.1 CHANGELOG: `Removed` entry for the incremental purge (with the data-loss rationale), and reframe the deep-reconciliation `Added` entry to daily + sole-owner-of-deletions
- [x] 4.2 CHANGELOG: correct the stale `Sun 03:00` / "Off by default" / `/run/cairn-mail/sync.lock` lines in the deep-reconciliation entry

## 5. Deployment & Verification

- [ ] 5.1 Commit + push to `main` (Keith's call)
- [ ] 5.2 Bump the cairn-mail flake input in `~/.config/nixos_config` and `nixos-rebuild switch` on edge
- [ ] 5.3 Confirm the incremental sync runs with no purge log lines and no `messages_purged` deletions
- [ ] 5.4 Confirm `cairn-mail-sync-deep.timer` shows the daily `OnCalendar=*-*-* 03:00:00` cadence
- [ ] 5.5 Run `sync deep` once to restore everything the purge ate (verify the `companies` INBOX block incl. UID 42936 returns and persists across the next incremental sync)
