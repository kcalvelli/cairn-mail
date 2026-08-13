## Context

The incremental sync flow: `sync_engine.run()` reads `last_sync`
(`sync_engine.py:186`), calls `provider.fetch_messages(since=last_sync,
max_results=...)` (line 189), stores/classifies the batch, then unconditionally sets
`last_sync = now()` (line 330).

`fetch_messages` returns a bare `List[Message]` and has three places where it can return an
incomplete window without saying so:

- **IMAP per-folder truncation** (`imap.py:573-578`): keeps `msg_ids[-max_results:]`, dropping
  the oldest UIDs, with a comment claiming this "can't cause data loss."
- **IMAP combined-cap truncation** (`imap.py:524-525`): after merging folders, trims to
  `max_results`.
- **IMAP folder-fetch failure** (`imap.py:518-520`): a folder that raises is logged and
  `continue`d — its messages are simply absent from the window.
- **Gmail page truncation** (`gmail.py:153-160`): `messages.list(maxResults=...)` returns one
  page and a `nextPageToken` that the code ignores.

Both providers also build a date-granular query from a UTC cursor: IMAP `SINCE %d-%b-%Y` vs
server-local `INTERNALDATE`, Gmail `after:%Y/%m/%d` vs account-local time. A cursor stored in UTC
can therefore exclude messages that arrived near a day boundary.

Recovery asymmetry: the nightly deep reconciliation walks folder-scoped providers (IMAP) and
repairs gaps, but it is IMAP-only. Gmail has no equivalent, so any window Gmail skips is lost
permanently and silently.

Only two callers of `fetch_messages` exist: `sync_engine.py:189` (the real path) and
`cli/accounts.py:509`, which is an already-broken connection test — it passes `max_messages=1`,
a kwarg no implementation accepts, so it always raises into its own `except` and never touches
the return value. That keeps the blast radius of any signature/behaviour change to the sync
engine.

## Goals / Non-Goals

**Goals:**
- Stop dropping day-boundary / timezone-skewed messages from the fetch window.
- Stop advancing the sync cursor past messages that were never fetched or never stored.
- Remove Gmail's permanent-loss path directly, since it has no deep-reconcile backstop.

**Non-Goals:**
- No change to deep reconciliation, the sync lock, or scheduling.
- Not fixing the broken `cli/accounts.py:509` connection test (separate, harmless bug).
- No new user-facing config knob for the slack window — a sensible constant is enough.
- Not re-architecting IMAP truncation into oldest-first pagination; deep reconcile plus cursor
  discipline already covers IMAP.

## Decisions

### 1. Subtract a slack margin from `since` in the sync engine

In `sync_engine.py`, compute `fetch_since = last_sync - SYNC_WINDOW_SLACK` (a module constant,
`timedelta(days=1)`) and pass that to `fetch_messages`. The slack absorbs both the date-
granularity and the UTC-vs-local skew — a full day comfortably covers any timezone offset. The
store loop already dedupes on message id (`sync_engine.py:198-204`), so re-observing messages in
the overlap is a no-op beyond a normal update.

**Rationale:** Fixes the boundary drop for both providers in one place, upstream of the provider-
specific query formatting, without touching either query builder. Alternative considered:
convert the cursor to server-local time and use finer-grained query operators — rejected as
provider-specific, fragile, and unnecessary once dedup makes overlap free.

### 2. Report window completeness from `fetch_messages` via provider instance state

Each provider sets `self.last_fetch_complete: bool` at the end of `fetch_messages` — `True` when
the window was fully returned, `False` when any truncation or per-folder fetch failure occurred.
Reset to `True` at the top of every `fetch_messages` call. `sync_engine` reads
`provider.last_fetch_complete` after the fetch.

**Rationale:** Keeps `fetch_messages` returning `List[Message]`, so the return contract and the
(broken but untouched) CLI caller are unaffected. Consistent with existing provider instance
state (`_keyword_support`, connection/folder caches). Alternative considered: change the return
type to a `FetchResult` dataclass — cleaner in isolation but ripples into callers and the base
Protocol for a single boolean; rejected as more surface for no correctness gain, since the flag
is read immediately by the same synchronous caller that made the fetch.

### 3. Advance the cursor only over a complete, failure-free sync

Replace the unconditional `update_last_sync(now())` at `sync_engine.py:330` with:

```python
if provider_fetch_complete and not errors:
    self.db.update_last_sync(self.account_id, sync_started_at)
else:
    logger.warning("Holding last_sync: fetch truncated or stores failed; window will be retried")
```

Advance to the time the sync *started* (captured before the fetch), not `now()`, so mail that
arrived during the sync isn't skipped by the next window. When the window was incomplete, leave
the cursor untouched so the next sync re-observes the same range (dedup makes that safe).

**Rationale:** This is the loss-prevention guarantee for providers without deep reconciliation.
On IMAP a held cursor plus the nightly reconcile drains any backlog; on Gmail the held cursor is
the whole safety net — combined with decision 4 it means Gmail never advances past mail it didn't
ingest.

### 4. Paginate Gmail's list until the window is drained (bounded)

In `gmail.fetch_messages`, follow `nextPageToken` and accumulate pages until the query is
exhausted or a hard safety ceiling (`max_results`, i.e. the caller's cap) is reached. If the
ceiling is hit with a token still outstanding, set `last_fetch_complete = False` so the cursor
holds and the next sync continues the drain.

**Rationale:** Gmail has no deep-reconcile backstop, so "hold the cursor" alone would stall a
backlog larger than one page. Pagination turns truncation from permanent loss into bounded,
resumable progress. IMAP keeps its newest-N behaviour (deep reconcile is its drainer) and merely
reports truncation via decision 2.

## Risks / Trade-offs

- **More overlap per sync.** Every incremental fetch now reaches ~1 day further back. Bounded and
  deduped, but it is extra fetch/parse work each cycle — acceptable against silent mail loss.
- **Held cursor could stall forward progress on IMAP** if a window perpetually exceeds the cap.
  In practice a >cap window only follows downtime or a burst, and deep reconciliation drains it;
  normal 5-minute operation never truncates. Documented, not engineered around.
- **`sync_started_at` capture point matters.** It must be read before the fetch begins; reading it
  after would reintroduce a smaller version of the same skip-during-sync gap.
- **Instance-state completeness flag must be reset per call** or a truncated sync could
  permanently pin the cursor. The reset-at-top-of-`fetch_messages` rule is load-bearing; tests
  must cover a complete fetch immediately following a truncated one.
- **Gmail pagination ceiling.** A first-ever sync of a very large mailbox will hit the ceiling and
  hold the cursor, draining over several syncs. That is correct behaviour (no loss), just slower
  initial convergence.

## Test Strategy

- Slack: a cursor at day boundary still includes a message timestamped just before it.
- Cursor: truncated fetch (flag `False`) and store-error batch each leave `last_sync` unchanged;
  a clean fetch advances it to `sync_started_at`.
- Flag hygiene: a complete fetch following a truncated one reports `True`.
- Gmail: multi-page window accumulates all pages; ceiling-hit sets `last_fetch_complete = False`.
