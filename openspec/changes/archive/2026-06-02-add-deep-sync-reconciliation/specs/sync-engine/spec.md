## ADDED Requirements

### Requirement: Deep Reconciliation Sync

The system SHALL provide a deep reconciliation mode that walks every folder for every account whose provider uses folder-scoped, position-stable message IDs (IMAP), diffs the full server UID set against the local message rows for that folder, and reconciles existence and flag state. This mode SHALL bypass the SINCE date window used by the regular incremental sync, but SHALL NOT refetch message bodies and SHALL NOT run AI classification.

For providers whose message IDs are stable across folder/label moves (e.g. label-based providers such as Gmail), the per-folder "absence == deletion" assumption does not hold, so the system SHALL skip deep reconciliation for those accounts and rely on the incremental sync to cover them. See design.md decision 7.

#### Scenario: Label-based provider is skipped

- **WHEN** deep reconciliation is invoked for an account whose provider does not use folder-scoped UIDs (e.g. Gmail)
- **THEN** the system SHALL log that the account is skipped, SHALL NOT add, purge, or modify any local rows for that account, and SHALL continue with the remaining accounts

#### Scenario: Server-side deletion outside the incremental window

- **WHEN** a message exists in the local database, the server no longer reports its UID in `UID SEARCH ALL` for that folder, and the message date is older than the incremental sync's SINCE cutoff
- **THEN** deep reconciliation SHALL delete the local message row

#### Scenario: Server-side new message inside the incremental window

- **WHEN** a UID is reported by the server but is missing from the local database for that folder
- **THEN** deep reconciliation SHALL fetch envelope and header data for that UID and create the corresponding local message row, without invoking the AI classifier

#### Scenario: Flag drift on an old message

- **WHEN** a message exists on both server and local, both reporting the same UID, but the server's `\Seen` flag differs from the local `is_unread` state
- **THEN** deep reconciliation SHALL update the local row to match the server's flag state

#### Scenario: AI classification is not run

- **WHEN** deep reconciliation creates a new local row for a server UID not previously known locally
- **THEN** the message SHALL be stored without invoking the AI classifier, regardless of folder or content

#### Scenario: Message bodies are not refetched

- **WHEN** deep reconciliation processes a UID that exists on both server and local
- **THEN** the local body text and HTML SHALL NOT be replaced or refetched

### Requirement: Empty-Folder Purge Safety Rail

The system SHALL refuse to purge local rows from a folder when the server returns zero UIDs for that folder and the local row count for that folder exceeds the configured threshold (default: 5). When the rail triggers, the run SHALL log an error-level message identifying the account and folder, skip all purges and flag reconciliation for that folder, and continue with the remaining folders.

#### Scenario: Folder appears empty on server but has many local rows

- **WHEN** `UID SEARCH ALL` for a folder returns zero UIDs and the local database has more than 5 rows for that account and folder
- **THEN** deep reconciliation SHALL log an error identifying the account and folder, SHALL NOT delete any local rows in that folder, and SHALL continue reconciling other folders for the account

#### Scenario: Folder is legitimately empty (small)

- **WHEN** `UID SEARCH ALL` for a folder returns zero UIDs and the local database has 5 or fewer rows for that account and folder
- **THEN** deep reconciliation SHALL delete the local rows for that folder as part of normal reconciliation

#### Scenario: One folder triggers the rail, another succeeds

- **WHEN** one folder for an account triggers the safety rail and a different folder reconciles successfully
- **THEN** the safe folder SHALL complete its reconciliation and the run SHALL continue to subsequent accounts

### Requirement: Concurrency Lock With Incremental Sync

The system SHALL prevent the deep reconciliation sync and the incremental 5-minute sync from running concurrently for the same installation. Both processes SHALL acquire a non-blocking advisory file lock on entry; if the lock is already held, the entering process SHALL log the contention and exit cleanly without performing any sync work.

#### Scenario: Incremental timer fires while deep sync is running

- **WHEN** the 5-minute incremental sync timer fires while deep reconciliation holds the advisory lock
- **THEN** the incremental sync process SHALL log that the lock is held and exit with success without fetching, classifying, or modifying any data

#### Scenario: Manual deep sync invoked while incremental is running

- **WHEN** a user invokes `cairn-mail sync deep` while the incremental sync holds the advisory lock
- **THEN** the deep sync process SHALL log that the lock is held and exit with success without performing reconciliation

#### Scenario: Lock is released on normal completion

- **WHEN** either sync process completes normally
- **THEN** the advisory lock SHALL be released so that the next scheduled or manual invocation can acquire it

#### Scenario: Lock is released on crash

- **WHEN** a sync process holding the lock crashes or is killed
- **THEN** the lock file SHALL not prevent the next invocation from running, either because it lives in a tmpfs runtime directory that is cleaned by systemd or because the advisory lock is released by the operating system on process exit

### Requirement: Deep Sync Scheduling

The system SHALL provide a systemd timer for invoking deep reconciliation on a configurable cadence. The default cadence SHALL be weekly at Sunday 03:00 local time. The timer SHALL be controllable via NixOS module options under `services.cairn-mail.sync.deep`.

#### Scenario: Default schedule

- **WHEN** the NixOS module is enabled without overriding `services.cairn-mail.sync.deep.onCalendar`
- **THEN** the `cairn-mail-sync-deep.timer` unit SHALL be installed with `OnCalendar=Sun 03:00`

#### Scenario: Disabled via module option

- **WHEN** `services.cairn-mail.sync.deep.enable = false` is set in the NixOS configuration
- **THEN** neither `cairn-mail-sync-deep.timer` nor `cairn-mail-sync-deep.service` SHALL be installed

#### Scenario: Manual invocation

- **WHEN** a user runs `cairn-mail sync deep` from the command line
- **THEN** the system SHALL perform a full deep reconciliation pass for all configured accounts, subject to the concurrency lock requirement
