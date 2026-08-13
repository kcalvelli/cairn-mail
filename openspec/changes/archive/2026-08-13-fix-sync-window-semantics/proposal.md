## Why

The incremental sync can silently and permanently lose mail. Two compounding bugs: the fetch
window is derived from a UTC timestamp truncated to a calendar date and compared against
server-/account-local time, so messages near a day boundary fall outside the window; and the
sync cursor (`last_sync`) advances to `now()` unconditionally — even when a fetch was truncated
at the max-results cap or a store failed. On IMAP the nightly deep reconciliation eventually
recovers the gap, but deep reconciliation is IMAP-only, so on Gmail the loss is permanent and
invisible: the sender's copy shows nothing wrong and the message simply never appears locally.

## What Changes

- Subtract a slack window (~1 day) from the `since` value before it is handed to a provider's
  `fetch_messages`, so day-boundary and timezone-skew messages stay inside the fetch window.
  Refetching already-stored messages is harmless — the store step already dedupes on message id
  (`sync_engine.py:198-204`).
- Stop advancing `last_sync` past work that was not durably completed: when a fetch was
  truncated at the max-results cap or the store/classify step reported failures, the cursor MUST
  NOT jump to `now()` and skip the un-fetched backlog.
- Correct the false "not at risk" claim baked into both the code comment (`imap.py:570-572`) and
  the spec (`sync-engine/spec.md:221-222`): truncation is only safe when the cursor does not
  advance past the dropped messages AND a recovery mechanism exists. On Gmail neither was true.
- **BREAKING** (internal only): the sync engine's cursor-advance logic changes; no external API
  or config surface changes.

## Capabilities

### New Capabilities
<!-- None. Behavior lives in the existing sync-engine capability. -->

### Modified Capabilities
- `sync-engine`: The incremental fetch window gains a slack/overlap so date-granular,
  timezone-skewed boundaries no longer drop messages; the sync cursor advances only over windows
  that were fetched completely and stored without failure; and the existing "truncation is not
  at risk" scenario is corrected to reflect that this safety depends on the cursor discipline
  (and, for folder-scoped providers, deep reconciliation) rather than being unconditionally true.

## Impact

- **Code**:
  - `src/cairn_mail/sync_engine.py` — apply slack to the `since` passed into `fetch_messages`
    (line 189); make the `update_last_sync` call (line 330) conditional on a complete,
    failure-free sync; thread a "truncated" signal up from the providers.
  - `src/cairn_mail/providers/implementations/imap.py` — surface whether a folder fetch was
    truncated (lines 573-578); adjust/clarify the misleading data-loss comment.
  - `src/cairn_mail/providers/implementations/gmail.py` — surface truncation
    (`maxResults`/`nextPageToken`, lines 156-160); Gmail has no deep-reconcile backstop, so its
    cursor discipline matters most here.
- **Specs**: `openspec/specs/sync-engine/spec.md` — modify the non-destructive/truncation
  requirement and add window-slack and cursor-advance requirements.
- **Behavior**: mildly more overlap per sync (bounded by the slack window; deduped on store), in
  exchange for not losing mail. No user-visible config or API change.
- **Dependencies**: none.
