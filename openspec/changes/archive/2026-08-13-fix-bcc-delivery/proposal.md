## Why

Mail sent with a Bcc recipient is silently never delivered to that recipient — and the
sender is told the send succeeded. The Bcc header is stripped from the MIME during build
(`email/mime_builder.py:176`) with a comment claiming SMTP handles it "separately," but
nothing does: the IMAP/SMTP path re-derives its envelope by parsing recipients back out of
the message headers (`providers/implementations/imap.py:1329-1331`), and the Bcc header is
no longer there to parse. Gmail sends the raw MIME with no envelope at all, so it drops Bcc
for the same reason. This is a critical correctness bug — the primary purpose of Bcc
(privately copying a recipient) fails without any error.

## What Changes

- Thread an explicit envelope recipient list (To + Cc + Bcc) from the send path through
  `provider.send_message` instead of re-deriving recipients from message headers.
- **SMTP/IMAP path**: deliver to the full envelope (including Bcc) via `RCPT TO`, while the
  transmitted message body carries no Bcc header — preserving Bcc privacy on the wire.
- **Gmail path**: include the Bcc recipients in the message the Gmail API receives so Google
  delivers to them and strips the header before delivery (Gmail owns envelope derivation;
  there is no separate RCPT list to pass).
- Replace the naive `header.split(",")` recipient parsing in `imap.py` with
  `email.utils.getaddresses`, so display names containing commas
  (`"Calvelli, Keith" <x@y>`) no longer explode into garbage `RCPT TO` entries.
- **BREAKING** (internal API only): `Provider.send_message` signature changes to accept the
  envelope recipient list. No external/HTTP contract changes.

## Capabilities

### New Capabilities
- `outbound-mail`: Sending a composed/replied message through a provider — how envelope
  recipients (To, Cc, Bcc) are derived, how Bcc privacy is preserved, and the per-provider
  (SMTP vs. Gmail) delivery semantics. No spec currently covers the send path.

### Modified Capabilities
<!-- None. No existing spec describes outbound send behavior. -->

## Impact

- **Code**:
  - `src/cairn_mail/email/mime_builder.py` — Bcc handling during build; expose envelope
    recipients to the caller.
  - `src/cairn_mail/api/routes/send.py` — pass the envelope recipient list into
    `send_message`.
  - `src/cairn_mail/providers/base.py` — updated `send_message` signature.
  - `src/cairn_mail/providers/implementations/imap.py` — use passed envelope + `getaddresses`;
    stop re-parsing Bcc from headers.
  - `src/cairn_mail/providers/implementations/gmail.py` — ensure Bcc recipients are delivered.
  - `src/cairn_mail/email/smtp_client.py` — confirm it forwards the caller-supplied recipient
    list unchanged.
- **APIs**: internal `Provider.send_message` signature only; no HTTP/UI contract change.
- **Dependencies**: none added (`email.utils.getaddresses` is stdlib).
