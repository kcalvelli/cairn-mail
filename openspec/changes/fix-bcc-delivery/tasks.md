## 1. Provider contract

- [x] 1.1 Update both `send_message` stubs in `src/cairn_mail/providers/base.py` to the new
      signature `send_message(self, mime_message: bytes, envelope_recipients: list[str],
      thread_id: Optional[str] = None) -> str`, and document `envelope_recipients` as the full
      To+Cc+Bcc delivery list.

## 2. Call site — build the envelope

- [x] 2.1 In `src/cairn_mail/api/routes/send.py`, build `envelope_recipients` from
      `draft.to_emails + draft.cc_emails + draft.bcc_emails` (guarding `None`), normalized to
      bare addresses via `email.utils.getaddresses`.
- [x] 2.2 Pass `envelope_recipients` into the `provider.send_message(...)` call (send.py:99).
- [x] 2.3 Reject a send with an empty envelope (no To/Cc/Bcc) with a clear error rather than
      handing SMTP/Gmail an empty recipient list.

## 3. IMAP/SMTP path

- [x] 3.1 In `src/cairn_mail/providers/implementations/imap.py`, change `send_message` to the
      new signature and use `envelope_recipients` directly as the SMTP `to_addrs`.
- [x] 3.2 Delete the header re-derivation block (imap.py:1328-1331) — the `for header in
      ["To","Cc","Bcc"]` loop and the `.split(",")`.
- [x] 3.3 Confirm the Sent-folder `APPEND` still stores the Bcc-free `mime_message` (no Bcc
      header written), preserving current Sent behavior.

## 4. Gmail path

- [x] 4.1 In `src/cairn_mail/providers/implementations/gmail.py`, change `send_message` to the
      new signature.
- [x] 4.2 Compute the Bcc addresses = `envelope_recipients` minus the addresses already in the
      message's `To`/`Cc` headers (compare using `getaddresses`-normalized addr_specs).
- [x] 4.3 If any Bcc addresses exist, add a `Bcc:` header to the raw MIME before base64
      encoding so Google delivers to them and strips the header on send.

## 5. MIME builder cleanup

- [x] 5.1 In `src/cairn_mail/email/mime_builder.py`, replace the misleading "handled separately
      in SMTP" comment (lines 176-177) with an accurate note that Bcc delivery is driven by the
      explicit envelope passed to `send_message`. Keep omitting the Bcc header from the built
      message.

## 6. Tests

- [x] 6.1 Bcc-only send: assert the Bcc address appears in the SMTP `to_addrs` (IMAP) and in the
      Gmail delivery recipients.
- [x] 6.2 Privacy: assert the message transmitted/serialized on the SMTP path contains no `Bcc`
      header, and that the Gmail-bound raw only carries Bcc as a strip-on-send header.
- [x] 6.3 To+Cc+Bcc send: assert all three addresses are in the envelope.
- [x] 6.4 Comma display name: `"Calvelli, Keith" <keith@example.com>` yields exactly one
      envelope recipient (`keith@example.com`), no garbage entry.
- [x] 6.5 Empty envelope: send with no recipients raises the expected error (task 2.3).

## 7. Validation

- [x] 7.1 `openspec validate fix-bcc-delivery --strict` passes.
- [x] 7.2 Run the backend test suite (`pytest`) green.
