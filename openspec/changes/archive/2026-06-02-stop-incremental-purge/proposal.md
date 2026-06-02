# Change: Stop the Incremental Sync From Deleting Mail

## Why

The 5-minute incremental sync was deleting live mail from the local database.

The incremental fetch is **windowed** — it issues `IMAP SEARCH SINCE <date>` and only ever sees a recent slice of each folder. On top of that fetch sat a "stale-row purge" that tried to mirror server-side deletions by deleting any local row that wasn't in the fetch. Inferring "the server deleted X" from "X wasn't in a fetch that was never going to include X" is unsound: the purge cannot tell a genuinely-deleted message from one that simply fell outside the window.

It bit us concretely. The purge anchored its cutoff a full day *earlier* than the fetch's floor (`floor(last_sync) − 1 day` vs. a fetch of `SINCE <last_sync_day>`), opening a one-day band — all of "yesterday" — where local rows were purge-eligible but never re-fetched. Every message dated the day before a sync was deleted locally while still sitting on the server. Deep reconciliation would re-add the block on its next pass and the very next incremental sync would wipe it again (the observed "added 10 → added 18" oscillation). Discovered when a known invoice vanished from `companies@calvelli.us` (INBOX UID 42936) while still live on the server; the lost rows were a contiguous "yesterday" band (UIDs 42930–42936).

The buggy cutoff dated to `0bc75329`, itself a fix to stop the purge eating the *historical* archive. Rather than re-tune a fundamentally fragile heuristic a third time, this change removes it. Detecting server-side deletions correctly requires a complete UID-set diff — which is exactly what deep reconciliation already does, with an empty-folder safety rail. So deletion reconciliation becomes deep reconciliation's sole responsibility, and deep moves from weekly to daily so deletions made in other clients still reconcile within a day.

## What Changes

- **Remove the incremental purge entirely.** `SyncEngine.sync()` no longer computes a purge window, gathers per-folder fetched IDs, or deletes any local rows to mirror server deletions. It only adds and updates.
- **Remove the now-dead purge support surface** on the IMAP provider: `get_last_queried_imap_folders()`, `get_truncated_folders()`, and the `_last_queried_imap_folders` / `_truncated_imap_folders` tracking sets. The truncation *warning* stays (it can no longer cause data loss).
- **Deep reconciliation becomes the sole owner of deletion reconciliation** and runs **daily** instead of weekly. NixOS default `OnCalendar` changes from `Sun 03:00` to `*-*-* 03:00:00`.
- User-initiated deletions are unaffected — they still apply immediately through the pending-operations queue.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `sync-engine`:
  - **ADDED** requirement "Incremental Sync Is Non-Destructive" — the incremental sync never deletes local rows to mirror server-side deletions.
  - **MODIFIED** "Deep Reconciliation Sync" — now the sole mechanism for mirroring server-side deletions; scenario wording no longer references an "incremental window" for deletions.
  - **MODIFIED** "Deep Sync Scheduling" — default cadence is now daily at 03:00.

## Impact

- Affected code:
  - `src/cairn_mail/sync_engine.py` — remove the purge block and dead counters from `sync()`
  - `src/cairn_mail/providers/implementations/imap.py` — remove the purge tracking sets and their getters; keep the truncation warning
  - `modules/nixos/default.nix` — deep `onCalendar` default `Sun 03:00` → `*-*-* 03:00:00`; docstrings updated
  - `CHANGELOG.md`
- No DB schema changes. No frontend changes. No API changes.
- Behavior change (intentional, non-breaking): a message deleted in another client (phone, webmail) now lingers locally until the next daily deep pass instead of being reconciled within ~5 minutes. New-mail arrival is unchanged (every 5 minutes). User-initiated deletes are instant.
- Known gap (unchanged, now documented): Gmail is skipped by deep reconciliation, so Gmail has no automatic server-side-deletion reconciliation. Pending a label-aware design.
