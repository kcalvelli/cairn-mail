## 1. Window slack (sync engine)

- [x] 1.1 Add a module constant `SYNC_WINDOW_SLACK = timedelta(days=1)` to
      `src/cairn_mail/sync_engine.py`.
- [x] 1.2 Capture `sync_started_at = datetime.now(timezone.utc)` before the fetch, and compute
      `fetch_since = last_sync - SYNC_WINDOW_SLACK` when `last_sync` is set (leave `None`
      untouched for a first/full sync). Pass `fetch_since` to `fetch_messages` (line 189).

## 2. Completeness signal (providers)

- [x] 2.1 In `src/cairn_mail/providers/base.py`, document a `last_fetch_complete: bool` attribute
      on the provider contract (default `True`), set by `fetch_messages` to report whether the
      window was fully returned.
- [x] 2.2 In `src/cairn_mail/providers/implementations/imap.py`, reset
      `self.last_fetch_complete = True` at the top of `fetch_messages`; set it `False` on any
      per-folder truncation (573-578), the combined-cap trim (524-525), or a folder-fetch failure
      (518-520). Replace the misleading "can't cause data loss" comment with an accurate note.
- [x] 2.3 In `src/cairn_mail/providers/implementations/gmail.py`, reset
      `self.last_fetch_complete = True` at the top of `fetch_messages`.

## 3. Gmail pagination

- [x] 3.1 In `gmail.fetch_messages`, loop on `nextPageToken`, accumulating message items across
      pages until the token is exhausted or a hard ceiling (the caller's `max_results`) is
      reached.
- [x] 3.2 If the ceiling is hit while a `nextPageToken` is still outstanding, set
      `self.last_fetch_complete = False` so the cursor holds and the next sync resumes the drain.

## 4. Cursor discipline (sync engine)

- [x] 4.1 Replace the unconditional `update_last_sync(now())` at `sync_engine.py:330` with a
      guarded advance: only advance (to `sync_started_at`) when `provider.last_fetch_complete`
      is `True` AND `errors` is empty.
- [x] 4.2 When the window was incomplete or stores failed, leave `last_sync` unchanged and log a
      warning that the window will be retried. Confirm the empty-sync backoff counter
      (`reset_empty_syncs` / `increment_empty_syncs`, 336-339) still keys off `messages_fetched`,
      not the cursor.

## 5. Spec sync

- [x] 5.1 The change's delta already modifies `sync-engine`; ensure `openspec/specs/sync-engine/
      spec.md:219-222` no longer claims truncation is unconditionally "not at risk" once synced
      (handled at archive/sync time).

## 6. Tests

- [x] 6.1 Slack: a message timestamped just below the stored cursor's day boundary is included in
      the computed `fetch_since` window (assert `fetch_since <= message_time`).
- [x] 6.2 Cursor holds on truncation: a fetch reporting `last_fetch_complete = False` leaves
      `last_sync` unchanged.
- [x] 6.3 Cursor holds on store failure: a batch with a store/classify error leaves `last_sync`
      unchanged even when the fetch was complete.
- [x] 6.4 Cursor advances on clean sync: complete fetch + no errors advances `last_sync` to
      `sync_started_at` (not a post-fetch `now()`).
- [x] 6.5 Flag hygiene: a complete fetch immediately following a truncated one reports
      `last_fetch_complete = True`.
- [x] 6.6 Gmail pagination: a mocked multi-page list accumulates all pages; a ceiling-hit with an
      outstanding token sets `last_fetch_complete = False`.

## 7. Validation

- [x] 7.1 `openspec validate fix-sync-window-semantics --strict` passes.
- [x] 7.2 Backend test suite (`pytest`, excluding the mcp module that can't import in the dev
      venv) green.
