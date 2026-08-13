## Why

AI classification tags never reach the IMAP server. `update_labels()` gates
all keyword writes on the string `"KEYWORD"` appearing in the CAPABILITY
response (`providers/implementations/imap.py:83-90`), but that is not a real
IMAP capability token — RFC 3501 advertises custom-keyword support per-mailbox
via `PERMANENTFLAGS (... \*)` in the SELECT response. On essentially every real
IMAP server the check fails, `_supports_keywords` stays false, and
`update_labels()` returns early in "read-only mode" (`imap.py:945-949`). The
result: a headline feature — persisting AI tags back to the mailbox so they
survive across clients and reinstalls — is a silent no-op. Nobody sees an
error; the tags simply never leave the local DB.

## What Changes

- Detect custom-keyword support from the **`PERMANENTFLAGS` response of a
  `SELECT`/`EXAMINE`**, not from the CAPABILITY string. Support is present when
  `PERMANENTFLAGS` contains the special `\*` flag (server accepts arbitrary new
  keywords). This is a per-mailbox property, so detection moves from
  connect-time to folder-select-time and caches per folder.
- Remove the bogus connect-time `"KEYWORD" in capabilities_str` check
  (`imap.py:83-90`) and the `_supports_keywords` single-boolean field it feeds.
- Stop silently swallowing the two `UID STORE` calls (`imap.py:967/975`).
  Inspect the imaplib response tuple; on a non-`OK` result, raise so the sync
  engine can defer the pending op to a later cycle rather than reporting a
  success that never happened.
- When a mailbox genuinely does not support custom keywords, keep the graceful
  degrade (log once, skip the write) — but that path should now be rare and
  correctly identified, not the default for every server.

## Capabilities

### New Capabilities

- `imap-keyword-writeback`: How the IMAP provider persists local labels/tags to
  the server as IMAP keywords — support detection via `PERMANENTFLAGS`, the
  `UID STORE +FLAGS`/`-FLAGS` write path, error surfacing on failed stores, and
  the fallback when a mailbox does not accept custom keywords.

### Modified Capabilities

None. No existing spec currently describes keyword/tag write-back; this
behavior was implemented but never specified, which is how it shipped broken.

## Impact

- **Code:** `src/cairn_mail/providers/implementations/imap.py` — keyword
  support detection (`:83-90`), the `_supports_keywords` field (`:48` area),
  `_select_folder`, and `update_labels()` (`:945-980`).
- **Behavior:** AI tags and manual label changes begin actually reaching IMAP
  servers. Pending label ops that fail at the server are retried instead of
  marked done.
- **No API, config, schema, or dependency changes.** Gmail is unaffected (it
  uses labels via the Gmail API, not IMAP keywords).
