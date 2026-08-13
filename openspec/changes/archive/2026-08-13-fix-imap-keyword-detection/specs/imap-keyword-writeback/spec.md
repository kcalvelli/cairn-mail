## Purpose

Defines how the IMAP provider persists local labels and AI-assigned tags back
to the mail server as IMAP keywords, so tag state survives across clients and
local database rebuilds instead of living only in cairn-mail's SQLite store.

## ADDED Requirements

### Requirement: Keyword Support Detection From PERMANENTFLAGS

The IMAP provider SHALL determine whether a mailbox accepts custom keywords by
inspecting the `PERMANENTFLAGS` response returned when the mailbox is selected,
NOT by inspecting the server's CAPABILITY response. A mailbox supports custom
keywords when its `PERMANENTFLAGS` list includes the special `\*` flag. Because
`PERMANENTFLAGS` is a per-mailbox property, support SHALL be evaluated for the
mailbox targeted by a write and MAY be cached per mailbox.

#### Scenario: Server advertises custom-keyword support via PERMANENTFLAGS

- **WHEN** a mailbox is selected and its `PERMANENTFLAGS` response contains `\*`
- **THEN** the provider treats the mailbox as accepting custom keywords
- **AND** keyword write-back proceeds for messages in that mailbox

#### Scenario: CAPABILITY string is not used for detection

- **WHEN** the server's CAPABILITY response does not contain the token `KEYWORD`
- **AND** the target mailbox's `PERMANENTFLAGS` response contains `\*`
- **THEN** the provider still treats the mailbox as accepting custom keywords
- **AND** keyword write-back is NOT skipped on the basis of the CAPABILITY string

#### Scenario: Mailbox does not accept custom keywords

- **WHEN** a mailbox's `PERMANENTFLAGS` response does not contain `\*`
- **THEN** the provider treats the mailbox as read-only for custom keywords
- **AND** it logs the unsupported state once for that mailbox
- **AND** it skips the keyword write without raising an error

### Requirement: Keyword Write-Back Of Labels

The IMAP provider SHALL persist label additions and removals to the server as
IMAP keywords using `UID STORE`, applying the configured keyword prefix to each
label. Additions SHALL use `+FLAGS` and removals SHALL use `-FLAGS`, both
scoped by UID within the message's own mailbox.

#### Scenario: Labels added to a message

- **WHEN** `update_labels` is called with labels to add for a message in a
  keyword-supporting mailbox
- **THEN** the provider issues a `UID STORE <uid> +FLAGS` command containing the
  prefixed keywords in that message's mailbox

#### Scenario: Labels removed from a message

- **WHEN** `update_labels` is called with labels to remove for a message in a
  keyword-supporting mailbox
- **THEN** the provider issues a `UID STORE <uid> -FLAGS` command containing the
  prefixed keywords in that message's mailbox

### Requirement: Failed Keyword Stores Are Surfaced

The IMAP provider SHALL inspect the result of each `UID STORE` keyword command.
If the server returns a non-`OK` status, the provider SHALL raise an error
rather than reporting success, so that the sync engine can leave the pending
operation unresolved and retry it on a later sync cycle.

#### Scenario: Server rejects a keyword store

- **WHEN** a `UID STORE` keyword command returns a non-`OK` status
- **THEN** the provider raises an error identifying the affected message and
  mailbox
- **AND** the operation is not recorded as successfully synced

#### Scenario: Keyword store succeeds

- **WHEN** every `UID STORE` keyword command for the operation returns `OK`
- **THEN** the provider completes without error
- **AND** the label change is considered persisted to the server
