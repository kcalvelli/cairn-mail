# Change: Add Weekly Deep Reconciliation Sync

## Why

The regular 5-minute sync is windowed — it issues `IMAP SEARCH SINCE <last_sync_day - 1>` and only reconciles UIDs within that window. Anything older is invisible to incremental sync, so the local DB drifts from the provider over time. We have already been bitten by adjacent failure modes (commits `0bc75329`, `aa0daacd`, `a216e6cc`), and the empty-sync-backoff outage that just resolved sat undetected partly because nothing periodically asks the provider "what do you actually have, in full?" A weekly deep reconciliation closes the drift window without the cost of running a full mailbox walk on the 5-minute cadence.

## What Changes

- New `cairn-mail sync deep` CLI subcommand that runs a full per-folder UID reconciliation, bypassing the SINCE window.
- New `SyncEngine.deep_reconcile()` method that walks every folder per account, diffs server UIDs against local rows, and reconciles existence + flags. **Does not** refetch bodies or re-run AI classification.
- Safety rail: if a folder returns zero server UIDs while local has more than a configurable threshold of rows for that folder, abort that folder loudly. Same failure shape as the historical-archive purge bug — protect against silent enumeration failure.
- Advisory lock so the deep sync and the regular 5-minute sync cannot overlap. If the regular timer fires mid-deep, it skips cleanly.
- New systemd timer `cairn-mail-sync-deep.timer`, default `OnCalendar=Sun 03:00`.
- New NixOS module option `services.cairn-mail.sync.deep` with `enable` and `onCalendar` keys.

## Capabilities

### New Capabilities

None. This extends existing sync behavior.

### Modified Capabilities

- `sync-engine`: adds a "Deep reconciliation" requirement covering the bypass-window walk, the per-folder safety rail, the advisory lock against the 5-minute timer, and the explicit non-goals (no body refetch, no reclassification).

## Impact

- Affected code:
  - `src/cairn_mail/sync_engine.py` — add `deep_reconcile()` and supporting helpers
  - `src/cairn_mail/cli/sync.py` — add `sync deep` subcommand
  - `src/cairn_mail/providers/base.py` / `implementations/imap.py` / `implementations/gmail.py` — add `list_all_uids(folder)` and `fetch_flags(folder, uids)` if not already present
  - `src/cairn_mail/db/database.py` — add helpers for "all rows in folder regardless of date" if the existing helpers are date-bounded
- Affected infra:
  - `modules/nixos-module.nix` (or wherever the systemd units are defined) — add the new timer + service
  - `modules/home-manager-module.nix` — add the `sync.deep` option block
- No DB schema changes. No frontend changes. No API changes.
- No breaking changes — the regular 5-minute sync is untouched.
