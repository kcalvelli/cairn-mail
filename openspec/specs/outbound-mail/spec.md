# outbound-mail Specification

## Purpose
Defines how a composed or replied message is delivered to its recipients through a mail
provider — specifically how the full set of envelope recipients (To, Cc, and Bcc) is
determined and how Bcc recipient privacy is preserved on the wire.
## Requirements
### Requirement: Bcc recipients receive the message

The system SHALL deliver a sent message to every Bcc recipient in addition to all To and Cc
recipients. Delivery to Bcc recipients MUST NOT depend on the Bcc header being present in the
transmitted message body.

#### Scenario: Message with only a Bcc recipient is delivered

- **WHEN** a user sends a message whose only recipient is a Bcc address
- **THEN** the message is delivered to that Bcc address
- **AND** the send is reported as successful only because delivery actually occurred

#### Scenario: Message with To, Cc, and Bcc recipients

- **WHEN** a user sends a message addressed to one To recipient, one Cc recipient, and one
  Bcc recipient
- **THEN** all three recipients receive the message

### Requirement: Bcc recipients remain hidden from other recipients

The system SHALL NOT reveal Bcc recipient addresses to To, Cc, or other Bcc recipients. The
message body delivered to recipients MUST NOT contain a Bcc header.

#### Scenario: Bcc address not exposed to visible recipients

- **WHEN** a message is sent with both a To recipient and a Bcc recipient
- **THEN** the copy received by the To recipient contains no Bcc header
- **AND** the Bcc recipient's address does not appear anywhere in that copy's headers

### Requirement: Envelope recipients derived from the draft, not the message headers

The system SHALL determine the delivery envelope (the set of addresses mail is delivered to)
from the draft's structured To, Cc, and Bcc recipient fields, not by re-parsing recipient
headers out of the assembled message. A recipient absent from the message headers (such as a
Bcc address) MUST still be included in the delivery envelope.

#### Scenario: Envelope includes a recipient not present in headers

- **WHEN** a message is assembled with no Bcc header but a Bcc recipient exists on the draft
- **THEN** the delivery envelope includes that Bcc recipient

### Requirement: Recipient addresses with display-name commas are parsed correctly

The system SHALL parse recipient values using RFC 5322 address parsing so that a display name
containing a comma (for example `"Calvelli, Keith" <keith@example.com>`) resolves to exactly
one envelope recipient. The system MUST NOT split recipient values on raw commas.

#### Scenario: Display name containing a comma yields one recipient

- **WHEN** a recipient is specified as `"Calvelli, Keith" <keith@example.com>`
- **THEN** the delivery envelope contains exactly one recipient, `keith@example.com`
- **AND** no malformed recipient entry is produced from the display-name fragment

