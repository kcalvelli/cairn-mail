## 1. Detection: PERMANENTFLAGS in place of CAPABILITY

- [x] 1.1 Delete the connect-time keyword block in `authenticate()`
      (`imap.py:83-90`) and the `_supports_keywords: Optional[bool]` field
      (`imap.py:47`).
- [x] 1.2 Add `self._keyword_support: dict[str, bool] = {}` and a
      `self._keyword_unsupported_logged: set[str] = set()` to `__init__`.
- [x] 1.3 In `_select_folder`, after a successful `select`, read
      `self.connection.response("PERMANENTFLAGS")`, decode `perm[0]` (guard
      `None`/empty), and set `self._keyword_support[folder]` to whether the
      `\*` token is present. Only compute on the branch that actually issues
      the `select` (i.e. when `_current_folder != folder`), and make sure a
      folder already selected still has a cached entry.

## 2. Write-back: gate and STORE result handling

- [x] 2.1 Replace the `if not self._supports_keywords:` gate in `update_labels`
      (`imap.py:945`) with a per-folder lookup after `_select_folder(folder)`:
      if `self._keyword_support.get(folder)` is falsy, log once (guarded by
      `_keyword_unsupported_logged`) and return.
- [x] 2.2 Capture the `(typ, data)` return of the `+FLAGS` `UID STORE`
      (`imap.py:967`); raise `RuntimeError` with uid + folder when `typ != "OK"`.
- [x] 2.3 Same for the `-FLAGS` `UID STORE` (`imap.py:975`).
- [x] 2.4 Confirm the existing `except` in `update_labels` re-raises so the sync
      engine leaves the pending op unresolved (no swallow).

## 3. Tests

- [x] 3.1 Unit test: PERMANENTFLAGS containing `\*` → folder marked supported;
      without `\*` → unsupported; missing/`None` response → unsupported.
- [x] 3.2 Unit test: a server whose CAPABILITY lacks `KEYWORD` but whose mailbox
      PERMANENTFLAGS has `\*` still gets keyword write-back (the regression this
      change fixes).
- [x] 3.3 Unit test: `update_labels` on a supported folder issues
      `UID STORE +FLAGS`/`-FLAGS` with the prefixed keywords for the add/remove
      sets (mock the imaplib connection, assert the calls).
- [x] 3.4 Unit test: a non-`OK` `UID STORE` result makes `update_labels` raise.
- [x] 3.5 Unit test: an unsupported folder is skipped without raising and logs
      only once across repeated calls.

## 4. Validate

- [x] 4.1 `openspec validate fix-imap-keyword-detection --strict` passes.
- [x] 4.2 Run the new tests + ruff; confirm green before committing.
