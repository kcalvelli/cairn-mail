## ADDED Requirements

### Requirement: Incremental Sync Is Non-Destructive

The regular incremental sync (the 5-minute timer and any manual `sync run`) SHALL NOT delete local message rows in order to mirror server-side deletions. It SHALL only create and update rows from its windowed fetch. Because the incremental fetch is windowed (`SEARCH SINCE <date>`) it never observes the full mailbox, so the absence of a stored message from a fetch SHALL NOT be treated as evidence that the message was deleted on the server. Detection of server-side deletions SHALL be performed exclusively by deep reconciliation. User-initiated deletions SHALL continue to apply immediately, independent of any reconciliation pass.

#### Scenario: Stored message absent from a windowed fetch is retained

- **WHEN** the incremental sync fetches a folder with a SINCE window and a message already stored locally is not present in the fetch results
- **THEN** the incremental sync SHALL leave the local row intact and SHALL NOT delete it

#### Scenario: A truncated fetch causes no deletion

- **WHEN** a folder's incremental fetch hits the max-results cap and returns only a subset of the server's UIDs
- **THEN** the incremental sync SHALL NOT delete any local rows for that folder, and the truncation SHALL be logged as informational (older messages are deferred to a later sync, not at risk)

#### Scenario: User-initiated deletion still applies immediately

- **WHEN** a user deletes or trashes a message in cairn-mail
- **THEN** the deletion SHALL be applied to the local database and queued to the provider through the pending-operations queue, independent of the incremental sync or any reconciliation pass

## MODIFIED Requirements

### Requirement: Deep Reconciliation Sync

The system SHALL provide a deep reconciliation mode that walks every folder for every account whose provider uses folder-scoped, position-stable message IDs (IMAP), diffs the full server UID set against the local message rows for that folder, and reconciles existence and flag state. This mode SHALL bypass the windowing used by the regular incremental sync, but SHALL NOT refetch message bodies and SHALL NOT run AI classification.

Deep reconciliation SHALL be the sole mechanism by which server-side deletions are mirrored into the local database; the incremental sync does not delete (see "Incremental Sync Is Non-Destructive").

For providers whose message IDs are stable across folder/label moves (e.g. label-based providers such as Gmail), the per-folder "absence == deletion" assumption does not hold, so the system SHALL skip deep reconciliation for those accounts. A consequence is that such accounts currently have no automatic reconciliation of server-side deletions; this is a known gap pending a label-aware design.

#### Scenario: Label-based provider is skipped

- **WHEN** deep reconciliation is invoked for an account whose provider does not use folder-scoped UIDs (e.g. Gmail)
- **THEN** the system SHALL log that the account is skipped, SHALL NOT add, purge, or modify any local rows for that account, and SHALL continue with the remaining accounts

#### Scenario: Server-side deletion is reconciled

- **WHEN** a message exists in the local database and the server no longer reports its UID in `UID SEARCH ALL` for that folder
- **THEN** deep reconciliation SHALL delete the local message row, subject to the empty-folder purge safety rail

#### Scenario: Server-side message missing locally is added

- **WHEN** a UID is reported by the server but is missing from the local database for that folder
- **THEN** deep reconciliation SHALL fetch envelope and header data for that UID and create the corresponding local message row, without invoking the AI classifier

#### Scenario: Flag drift on a message

- **WHEN** a message exists on both server and local, both reporting the same UID, but the server's `\Seen` flag differs from the local `is_unread` state
- **THEN** deep reconciliation SHALL update the local row to match the server's flag state

#### Scenario: AI classification is not run

- **WHEN** deep reconciliation creates a new local row for a server UID not previously known locally
- **THEN** the message SHALL be stored without invoking the AI classifier, regardless of folder or content

#### Scenario: Message bodies are not refetched

- **WHEN** deep reconciliation processes a UID that exists on both server and local
- **THEN** the local body text and HTML SHALL NOT be replaced or refetched

### Requirement: Deep Sync Scheduling

The system SHALL provide a systemd timer for invoking deep reconciliation on a configurable cadence. Because deep reconciliation is the sole mechanism that mirrors server-side deletions into the local database, the default cadence SHALL be daily at 03:00 local time, so that deletions made in other clients are reconciled within roughly a day. The timer SHALL be controllable via NixOS module options under `services.cairn-mail.sync.deep`.

#### Scenario: Default schedule

- **WHEN** the NixOS module is enabled without overriding `services.cairn-mail.sync.deep.onCalendar`
- **THEN** the `cairn-mail-sync-deep.timer` unit SHALL be installed with `OnCalendar=*-*-* 03:00:00`

#### Scenario: Disabled via module option

- **WHEN** `services.cairn-mail.sync.deep.enable = false` is set in the NixOS configuration
- **THEN** neither `cairn-mail-sync-deep.timer` nor `cairn-mail-sync-deep.service` SHALL be installed

#### Scenario: Manual invocation

- **WHEN** a user runs `cairn-mail sync deep` from the command line
- **THEN** the system SHALL perform a full deep reconciliation pass for all configured accounts, subject to the concurrency lock requirement
