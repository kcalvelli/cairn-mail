## Context

Two providers implement `Provider.send_message(mime_message: bytes, thread_id=None)`:

- **IMAP/SMTP** (`imap.py:1287`): parses the MIME back with `email.message_from_bytes`, then
  rebuilds the delivery envelope by reading the `To`/`Cc`/`Bcc` headers off the parsed message
  and `header.split(",")`. It hands that list to `smtp_client.send_message(msg, from_addr,
  to_addrs)`. The SMTP client already accepts an explicit `to_addrs` list (`smtp_client.py:37`)
  — it just isn't being fed a correct one.
- **Gmail** (`gmail.py:603`): base64-encodes the raw MIME and calls the Gmail API `messages.send`.
  There is no envelope parameter; Gmail derives recipients from the message headers.

`mime_builder.py:176` intentionally omits the `Bcc` header from the built message ("handled
separately in SMTP"). Nothing handles it, so:

- IMAP re-derives the envelope from headers where `Bcc` no longer exists → Bcc never gets a
  `RCPT TO`.
- Gmail has no `Bcc` header to deliver from → Bcc never delivered.

The draft carries structured recipients (`draft.to_emails`, `draft.cc_emails`,
`draft.bcc_emails`), so the correct envelope is available upstream at the call site
(`send.py:75-102`) and does not need to be reconstructed from serialized headers at all. Only
one external caller of `send_message` exists (`send.py:99`), so changing its signature is
contained.

## Goals / Non-Goals

**Goals:**
- Bcc recipients actually receive sent mail, on both IMAP/SMTP and Gmail.
- Bcc addresses never appear in the copy delivered to any recipient (privacy preserved).
- Envelope recipients are derived from the draft's structured fields, not by re-parsing
  serialized headers.
- Recipient values with commas in display names parse to one recipient each.

**Non-Goals:**
- No change to the compose UI, draft schema, or any HTTP request/response contract.
- Not adding a `Bcc:` record to the sender's own Sent-folder copy (see Risks).
- No new dependencies — `email.utils.getaddresses` is stdlib.

## Decisions

### 1. Thread an explicit envelope recipient list through `send_message`

Change the provider contract to:

```python
def send_message(
    self,
    mime_message: bytes,
    envelope_recipients: list[str],
    thread_id: Optional[str] = None,
) -> str: ...
```

`send.py` builds `envelope_recipients` from `draft.to_emails + draft.cc_emails +
draft.bcc_emails`, normalized to bare addresses via `email.utils.getaddresses`. This is the
single source of truth for who the message is delivered to. Update `base.py` (both stub
definitions), `imap.py`, `gmail.py`, and the `send.py:99` call site together.

**Rationale:** The envelope is a delivery concern, not a message-body concern. Deriving it from
structured draft data upstream eliminates the entire "re-parse headers to find recipients"
failure mode — the bug's root cause. Alternative considered: keep the header re-parsing but add
the `Bcc` header back into the built MIME and let each transport strip it. Rejected — it makes
the message body the carrier of a delivery detail, and every serialization of that message (the
Sent-folder append, logging) has to remember to strip Bcc or it leaks. Explicit envelope is the
narrower, safer contract.

### 2. IMAP/SMTP: pass the envelope straight to the SMTP client; drop header re-parsing

`imap.send_message` stops reading `To`/`Cc`/`Bcc` off the parsed message and passes
`envelope_recipients` directly as `to_addrs`. Because `mime_builder` still omits the `Bcc`
header, the transmitted `DATA` carries no Bcc header — privacy is preserved by construction, no
stripping needed. This also deletes the `header.split(",")` code entirely, so the
`"Calvelli, Keith" <x@y>` explosion goes away.

### 3. Gmail: inject a `Bcc` header from the envelope so Google delivers, then strips

Gmail has no envelope parameter, so Bcc recipients must reach it through the message. In
`gmail.send_message`, compute which `envelope_recipients` are not already present in the
message's `To`/`Cc` headers — those are the Bcc addresses — and add a `Bcc:` header to the raw
MIME before base64-encoding. Google's `messages.send` delivers to `To`+`Cc`+`Bcc` and removes
the `Bcc` header before the message leaves Google, so recipient copies stay clean.

**Rationale:** Localizes Gmail's quirk inside the Gmail provider instead of leaking it into
`mime_builder` or `send.py`. The generic MIME the rest of the system handles stays Bcc-free.

### 4. Normalize addresses with `email.utils.getaddresses`

Everywhere the envelope is assembled (`send.py`) and wherever the Gmail provider inspects
existing `To`/`Cc` headers, use `getaddresses([...])` and take the `addr_spec` (second tuple
element). Never `.split(",")` a recipient string.

### 5. Leave `mime_builder` omitting the `Bcc` header — but fix the comment

The current behavior (no `Bcc` in the built message) is now correct-by-design rather than a
half-finished handoff. Replace the misleading "handled separately in SMTP" comment with an
accurate note that Bcc delivery is driven by the explicit envelope passed to `send_message`.

## Risks / Trade-offs

- **Sender's Sent copy loses the Bcc record.** The IMAP `APPEND` stores the Bcc-free
  `mime_message`, so the sender can't later see who they Bcc'd from the Sent folder. This
  matches today's behavior and keeps the change small; adding a Bcc-annotated Sent copy is a
  separate enhancement, explicitly out of scope.
- **Signature change is breaking for `send_message` callers.** Mitigated: only one external
  caller exists (`send.py:99`); both `base.py` stubs, both provider implementations, and that
  call site are updated in the same change. `thread_id` stays keyword/optional so Gmail reply
  threading is unaffected.
- **Gmail Bcc detection relies on address matching.** Determining "which envelope addresses are
  Bcc" by diffing against `To`/`Cc` headers assumes address normalization matches on both sides
  — hence the shared `getaddresses` normalization. Edge case: the same address in both a visible
  header and Bcc collapses to visible-only, which is the correct, non-leaking outcome.
- **Test coverage.** Needs unit tests asserting: (a) Bcc-only send yields a `RCPT TO`/Gmail
  recipient for the Bcc address, (b) delivered/serialized message contains no `Bcc` header on
  the SMTP path, (c) a `"Last, First" <a@b>` recipient produces exactly one envelope entry.
