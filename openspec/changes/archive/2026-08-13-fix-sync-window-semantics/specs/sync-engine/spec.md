## ADDED Requirements

### Requirement: Incremental Fetch Window Includes Slack

The incremental sync SHALL widen the fetch window backward by a slack margin (at least one day)
before deriving the provider query from the stored `last_sync` cursor. This compensates for the
date-granular, local-time comparison both providers apply: IMAP formats the cursor as
`SEARCH SINCE <DD-Mon-YYYY>` matched against server-local `INTERNALDATE`, and Gmail formats it as
`after:<YYYY/MM/DD>` evaluated in the account's local time, so a cursor stored in UTC can exclude
messages that arrived near a day boundary. Because the store step deduplicates on message id,
re-observing already-stored messages within the slack margin SHALL have no effect other than
harmless re-fetching.

#### Scenario: Message near the day boundary is not skipped

- **WHEN** a message's server timestamp falls within the slack margin below the stored
  `last_sync` cursor (for example, arriving just before midnight local time on the cursor's day)
- **THEN** the incremental fetch window SHALL include that message rather than excluding it as
  older than the cursor

#### Scenario: Re-fetched messages within the slack margin are deduplicated

- **WHEN** the widened window causes messages already stored locally to be fetched again
- **THEN** the sync SHALL detect them as existing and SHALL NOT create duplicate rows or alter
  local state beyond what a normal update would do

### Requirement: Sync Cursor Advances Only Over Completed Work

The incremental sync SHALL advance the stored `last_sync` cursor only when the fetch for the
account was not truncated at the max-results cap and no message in the batch failed to store.
When a fetch was truncated (older messages were dropped to satisfy the cap) or a store/classify
step reported failure, the sync SHALL NOT advance the cursor past the un-fetched or unstored
messages, so a subsequent sync re-observes them. This requirement is the primary loss-prevention
mechanism for providers without deep reconciliation (Gmail), where a skipped window is never
recovered by any other pass.

#### Scenario: Truncated fetch does not advance the cursor

- **WHEN** an account's incremental fetch hits the max-results cap and returns only the newest
  subset of the messages available in its window
- **THEN** the sync SHALL leave the `last_sync` cursor unchanged (or advanced no further than the
  oldest message it durably stored) so the dropped older messages remain inside a future fetch
  window

#### Scenario: Store failure holds the cursor

- **WHEN** one or more messages in the batch fail to store or classify during a sync
- **THEN** the sync SHALL NOT advance the cursor to the current time, so the failed messages are
  retried on a later sync rather than being permanently skipped

## MODIFIED Requirements

### Requirement: Incremental Sync Is Non-Destructive

The regular incremental sync (the 5-minute timer and any manual `sync run`) SHALL NOT delete local message rows in order to mirror server-side deletions. It SHALL only create and update rows from its windowed fetch. Because the incremental fetch is windowed (`SEARCH SINCE <date>`) it never observes the full mailbox, so the absence of a stored message from a fetch SHALL NOT be treated as evidence that the message was deleted on the server. Detection of server-side deletions SHALL be performed exclusively by deep reconciliation. User-initiated deletions SHALL continue to apply immediately, independent of any reconciliation pass.

#### Scenario: Stored message absent from a windowed fetch is retained

- **WHEN** the incremental sync fetches a folder with a SINCE window and a message already stored locally is not present in the fetch results
- **THEN** the incremental sync SHALL leave the local row intact and SHALL NOT delete it

#### Scenario: A truncated fetch causes no deletion

- **WHEN** a folder's incremental fetch hits the max-results cap and returns only a subset of the server's UIDs
- **THEN** the incremental sync SHALL NOT delete any local rows for that folder, and the truncation SHALL be logged as informational

#### Scenario: Truncated older messages are not lost

- **WHEN** a fetch is truncated at the max-results cap so that the oldest messages in the window are dropped from this pass
- **THEN** those messages SHALL remain retrievable by a later pass — the sync cursor SHALL NOT advance past them (see "Sync Cursor Advances Only Over Completed Work"), and for folder-scoped providers deep reconciliation additionally reconciles them; the safety SHALL NOT be assumed unconditionally, since a provider without deep reconciliation relies solely on the cursor discipline

#### Scenario: User-initiated deletion still applies immediately

- **WHEN** a user deletes or trashes a message in cairn-mail
- **THEN** the deletion SHALL be applied to the local database and queued to the provider through the pending-operations queue, independent of the incremental sync or any reconciliation pass
