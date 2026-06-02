# sync-engine Specification

## Purpose
TBD - created by archiving change sync-performance. Update Purpose after archive.
## Requirements
### Requirement: IMAP Connection Pooling
The sync engine SHALL maintain persistent IMAP connections to avoid re-authentication overhead on each sync cycle.

#### Scenario: Reusing existing connection
- **Given** an IMAP account has been synced previously
- **And** the connection is still healthy
- **When** a new sync cycle starts
- **Then** the existing connection is reused
- **And** no new authentication handshake occurs

#### Scenario: Connection health check fails
- **Given** an IMAP account has an existing connection
- **And** the connection is stale or disconnected
- **When** a sync cycle starts
- **Then** a new connection is established
- **And** the old connection is closed

#### Scenario: Connection idle timeout
- **Given** an IMAP connection has been idle for longer than the configured timeout
- **When** the idle timeout is reached
- **Then** the connection is closed
- **And** a new connection will be created on the next sync

### Requirement: Parallel Account Syncing
The sync engine SHALL sync multiple accounts concurrently to reduce total sync time.

#### Scenario: Multiple accounts sync in parallel
- **Given** there are 4 email accounts configured
- **When** a sync cycle is triggered
- **Then** all 4 accounts begin syncing concurrently
- **And** the total sync time is approximately max(individual_sync_times) not sum(individual_sync_times)

#### Scenario: One account fails during parallel sync
- **Given** multiple accounts are syncing in parallel
- **When** one account encounters an error
- **Then** the error is logged for that account
- **And** other accounts continue syncing normally
- **And** the sync results include both successes and the failure

### Requirement: Folder Mapping Cache
The sync engine SHALL cache folder discovery results to avoid redundant IMAP LIST commands.

#### Scenario: Cache hit on folder lookup
- **Given** folder mapping was discovered within the cache TTL
- **When** a sync cycle needs the folder mapping
- **Then** the cached mapping is used
- **And** no IMAP LIST command is issued

#### Scenario: Cache invalidation on connection reset
- **Given** folder mapping is cached
- **When** the IMAP connection is reset
- **Then** the folder cache is invalidated
- **And** the next sync will re-discover folders

### Requirement: IMAP IDLE Push Notifications
The sync engine SHALL support IMAP IDLE for near-instant email notifications on supported servers.

#### Scenario: Server supports IDLE
- **Given** an IMAP server advertises the IDLE capability
- **When** the sync service starts
- **Then** an IDLE watcher is started for that account
- **And** the watcher monitors the INBOX folder

#### Scenario: New email arrives via IDLE
- **Given** an IDLE watcher is monitoring an INBOX
- **When** a new email arrives on the server
- **Then** the server sends an EXISTS notification
- **And** the sync engine triggers an immediate sync for that account
- **And** the new email appears in the UI within 2 seconds

#### Scenario: IDLE timeout refresh
- **Given** an IDLE watcher has been waiting for 25 minutes
- **When** the IDLE timeout is reached
- **Then** the IDLE command is re-issued
- **And** no messages are missed during the refresh

#### Scenario: Server does not support IDLE
- **Given** an IMAP server does not advertise the IDLE capability
- **When** the sync service starts
- **Then** no IDLE watcher is created for that account
- **And** the account uses polling-based sync

#### Scenario: IDLE connection drops
- **Given** an IDLE watcher is active
- **When** the connection is lost
- **Then** the watcher attempts to reconnect
- **And** IDLE is resumed after reconnection
- **And** a full sync is triggered to catch any missed messages

### Requirement: Gmail Credential Caching
The sync engine SHALL properly cache Gmail API credentials to avoid unnecessary token refreshes.

#### Scenario: Credentials are valid
- **Given** Gmail credentials are cached and not expired
- **When** a Gmail API request is made
- **Then** the cached credentials are used
- **And** no 401 response occurs

#### Scenario: Credentials near expiry
- **Given** Gmail credentials will expire within 5 minutes
- **When** a sync cycle starts
- **Then** credentials are proactively refreshed before the API call
- **And** no 401 response occurs during the sync

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

The system SHALL prevent the deep reconciliation sync and the incremental 5-minute sync from running concurrently for the same installation. Both processes SHALL acquire a non-blocking advisory file lock (located beside the database, at `<db_dir>/sync.lock`) on entry; if the lock is already held, the entering process SHALL log the contention and exit cleanly without performing any sync work.

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
- **THEN** the lock file SHALL not prevent the next invocation from running, because the advisory `fcntl` lock is released by the operating system when the holding process exits, independent of whether the lock file remains on disk

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

