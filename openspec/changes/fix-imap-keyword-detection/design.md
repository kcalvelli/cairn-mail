## Context

All changes are confined to `src/cairn_mail/providers/implementations/imap.py`.
The bug: `_supports_keywords` is set once at connect time from a bogus
`"KEYWORD" in CAPABILITY` test (`imap.py:83-90`), so it is effectively always
`False` and `update_labels()` short-circuits (`imap.py:945-949`). Custom-keyword
support is not a server-wide capability — it is advertised per-mailbox in the
`PERMANENTFLAGS` untagged response of a `SELECT`, by the presence of the special
`\*` flag. Detection therefore has to move from connect-time to select-time.

## Goals / Non-Goals

**Goals**
- Detect keyword support from `PERMANENTFLAGS`, per mailbox.
- Actually persist label add/remove as IMAP keywords.
- Raise on a failed `UID STORE` so the pending op is retried, not silently
  marked done.

**Non-Goals**
- No change to Gmail (labels go through the Gmail API, not IMAP keywords).
- No change to the keyword *prefix* scheme or the tag taxonomy.
- No connection-pool or folder-state-race work — that is Phase 1.1
  (`fix-imap-connection-races`), tracked separately.

## Decisions

### Read PERMANENTFLAGS via `connection.response()`, not `select()`'s return

`imaplib`'s `select(folder)` returns `(typ, data)` where `data` is the message
count — **not** the flags. The untagged `PERMANENTFLAGS` line is parked in the
connection's response cache and is read back with:

```python
typ, perm = self.connection.response("PERMANENTFLAGS")
# perm == [b'(\\Answered \\Flagged \\Deleted \\Seen \\Draft \\*)'] or [None]
```

A mailbox accepts arbitrary new keywords when `\*` appears in that list. Parse
by decoding `perm[0]` (guard `None`) and testing for the `\*` token. If the
server sends no `PERMANENTFLAGS` at all, treat it as unsupported (conservative).

This read happens inside `_select_folder` right after a successful `select`,
because that is the only place the response is fresh for the target mailbox.

### Replace the single bool with a per-folder cache

`self._supports_keywords: Optional[bool]` (`imap.py:47`) becomes
`self._keyword_support: dict[str, bool]` keyed by folder. `_select_folder`
populates it the first time it actually issues a `select` for a folder. Delete
the connect-time detection block entirely (`imap.py:83-90`).

Caveat noted, not fixed here: `_current_folder` skips re-selecting a folder
already current (`imap.py:388`), so the cache is populated on first real select
and reused — correct as long as support doesn't change mid-connection, which it
doesn't. The connection-swap reset of `_current_folder` is Phase 1.1's problem;
this change must not regress it, so the cache lives on the same object and is
naturally discarded when the provider instance goes away.

### `update_labels` consults the cache for the message's own folder

`update_labels` already parses `folder, uid` from the message id and calls
`_select_folder(folder)` (`imap.py:960-963`). After that select, look up
`self._keyword_support.get(folder)`. If `False`, log once per folder and return
(the graceful degrade). If `True`, proceed to the STOREs. This replaces the
`if not self._supports_keywords:` gate at `imap.py:945`.

"Log once per folder" = track a small `set[str]` of already-warned folders so a
5-minute sync of an old server doesn't spew a line per message.

### Inspect `UID STORE` results and raise on non-OK

`connection.uid("STORE", uid, "+FLAGS", ...)` returns `(typ, data)`. Today the
return is discarded (`imap.py:967/975`). Capture it; if `typ != "OK"`, raise
`RuntimeError` with the uid and folder. The existing `except` in `update_labels`
(`imap.py:977-979`) already re-raises, so the sync engine sees the failure and
leaves the pending op unresolved for the next cycle — which is the behavior the
spec requires. Both the `+FLAGS` and `-FLAGS` calls get the same treatment.

## Risks / Trade-offs

- **Servers with quirky PERMANENTFLAGS.** Some servers omit `\*` but still
  accept keywords, or omit the line entirely. We degrade to "unsupported" and
  skip — same as today's behavior, just now correct for the common case instead
  of wrong for all cases. Acceptable; erring toward not-writing is safe.
- **A newly-raising STORE path** means label ops that used to (silently) look
  successful can now surface as retryable failures. That is the point — but it
  does mean a genuinely broken server will retry each cycle. Bounded by the
  existing pending-op mechanism; no new retry loop introduced here.

## Migration Plan

None. No schema, config, or API change. Behavior change only: keywords that
were being dropped begin reaching supporting servers on the next sync. No
backfill — the next classification/label op per message writes through.

## Open Questions

None blocking. If a specific server is later found to accept keywords without
advertising `\*`, add a narrow allow-list override then — out of scope now.
