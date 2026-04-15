# Email Sync Capability

## ADDED Requirements

### Requirement: Declarative Account Configuration

The system SHALL support declarative account configuration via NixOS/Home Manager modules, maintaining the infrastructure-as-code approach.

#### Scenario: Define accounts in Nix

- **WHEN** a user configures accounts in their home.nix or NixOS configuration
- **THEN** the system SHALL generate the necessary runtime configuration files
- **AND** SHALL validate account configuration at build time (invalid provider, missing required fields)
- **AND** SHALL apply configuration changes on activation (home-manager switch)
- **AND** SHALL restart services if configuration changes require it

#### Scenario: Multiple account types

- **WHEN** a user configures different provider types (Gmail, IMAP, Outlook) in the same configuration
- **THEN** the system SHALL generate provider-specific configuration for each account
- **AND** SHALL support mixing OAuth2 and password-based authentication
- **AND** SHALL validate provider-specific options (e.g., IMAP requires host/port, Gmail requires OAuth)

#### Scenario: Configuration validation

- **WHEN** a user activates a configuration with invalid account settings
- **THEN** the Nix build SHALL fail with a clear error message indicating:
  - Which account has the error
  - What field is invalid or missing
  - Example of correct configuration
- **AND** SHALL NOT allow deployment of invalid configuration

#### Scenario: Idempotent configuration

- **WHEN** a user runs `home-manager switch` multiple times with the same configuration
- **THEN** the system SHALL produce identical results each time (idempotent)
- **AND** SHALL NOT create duplicate accounts or configurations
- **AND** SHALL only restart services if configuration actually changed

### Requirement: Provider Abstraction

The system SHALL provide a unified interface for interacting with different email providers (Gmail, IMAP, Outlook) to abstract provider-specific API differences.

#### Scenario: Gmail provider fetch

- **WHEN** the sync engine calls `fetch_messages()` on a Gmail provider
- **THEN** the provider SHALL use the Gmail API to retrieve messages
- **AND** SHALL return messages in a normalized `Message` format
- **AND** SHALL include message ID, subject, sender, recipients, date, snippet, and current labels

#### Scenario: IMAP provider fetch

- **WHEN** the sync engine calls `fetch_messages()` on an IMAP provider
- **THEN** the provider SHALL use IMAP protocol to retrieve messages
- **AND** SHALL detect available IMAP extensions (X-GM-LABELS, KEYWORD, METADATA)
- **AND** SHALL return messages in the same normalized `Message` format as other providers

#### Scenario: Provider label update

- **WHEN** the sync engine calls `update_labels(message_id, add_labels, remove_labels)`
- **THEN** the provider SHALL apply the specified label changes to the message
- **AND** SHALL handle provider-specific label formats (Gmail labels vs Outlook categories vs IMAP keywords)
- **AND** SHALL create labels that don't exist using provider-specific creation methods

### Requirement: Two-Way Synchronization

The system SHALL synchronize email metadata and labels bidirectionally between the local database and email providers.

#### Scenario: Fetch new messages

- **WHEN** a sync operation is triggered (timer or manual)
- **THEN** the system SHALL fetch messages newer than the last sync timestamp
- **AND** SHALL store message metadata in the local SQLite database
- **AND** SHALL queue unclassified messages for AI processing

#### Scenario: Push AI labels to provider

- **WHEN** a message is classified by the AI engine
- **THEN** the system SHALL map AI tags to provider-specific labels (e.g., `work` → `AI/Work` Gmail label)
- **AND** SHALL call the provider's `update_labels()` method to apply labels remotely
- **AND** SHALL record the label push in the database with timestamp

#### Scenario: Detect user label changes

- **WHEN** a user manually changes labels in their email client (Gmail web, Outlook mobile, etc.)
- **THEN** the next sync operation SHALL detect the label difference
- **AND** SHALL record the change as user feedback in the database
- **AND** SHALL NOT override user changes with AI classifications

#### Scenario: Incremental sync

- **WHEN** performing a sync operation on an account that was previously synced
- **THEN** the system SHALL use provider-specific incremental sync mechanisms:
  - Gmail: historyId to fetch only changes since last sync
  - Outlook: deltaLink for incremental queries
  - IMAP: UIDNEXT and CHANGEDSINCE extension if available
- **AND** SHALL fall back to timestamp-based filtering if incremental sync is unavailable

### Requirement: Multi-Account Support

The system SHALL support synchronizing multiple email accounts simultaneously with independent sync state per account.

#### Scenario: Configure multiple accounts

- **WHEN** a user configures multiple accounts in the configuration file
- **THEN** the system SHALL load all accounts on startup
- **AND** SHALL initialize a separate provider instance for each account
- **AND** SHALL maintain separate sync state (last sync time, cursors) for each account

#### Scenario: Parallel account sync

- **WHEN** a sync operation is triggered
- **THEN** the system SHALL sync all configured accounts
- **AND** SHALL run account syncs in parallel (using thread pool or async tasks)
- **AND** SHALL isolate errors per account (one account failure doesn't block others)

### Requirement: Secure Credential Storage

The system SHALL store OAuth tokens and IMAP passwords securely using encrypted storage mechanisms integrated with NixOS.

#### Scenario: sops-nix integration

- **WHEN** a user configures an account with `oauthTokenFile` or `passwordFile` pointing to a sops-nix secret
- **THEN** the system SHALL read the decrypted secret from the path provided by sops-nix
- **AND** SHALL verify the file has restricted permissions (600)
- **AND** SHALL fail gracefully if the secret file is not accessible with a clear error message

#### Scenario: agenix integration

- **WHEN** a user configures an account with a credential file managed by agenix
- **THEN** the system SHALL read the age-encrypted secret from the agenix-provided path
- **AND** SHALL work transparently with agenix's decryption mechanism

#### Scenario: systemd-creds integration

- **WHEN** a user configures an account with `oauthTokenFile` pointing to `/run/credentials/cairn-mail.service/*`
- **THEN** the system SHALL read credentials loaded by systemd's LoadCredential mechanism
- **AND** SHALL only access credentials available to the service user

#### Scenario: Plain text password file (fallback)

- **WHEN** a user provides a plain text password file (not recommended, but supported)
- **THEN** the system SHALL read the file and warn in logs about security implications
- **AND** SHALL verify the file has restricted permissions (600)
- **AND** SHALL refuse to read world-readable credential files

#### Scenario: Invalid credential file

- **WHEN** a credential file path is configured but the file doesn't exist or isn't readable
- **THEN** the system SHALL log a clear error message indicating which account and file is affected
- **AND** SHALL skip sync for that account
- **AND** SHALL NOT crash or affect other accounts

### Requirement: OAuth2 Authentication

The system SHALL authenticate with email providers using OAuth2 with secure token storage and automatic refresh.

#### Scenario: Initial OAuth2 flow

- **WHEN** a user runs the `cairn-mail auth setup <provider>` command
- **THEN** the system SHALL guide the user through creating an OAuth app in the provider's console
- **AND** SHALL open a browser for the OAuth authorization flow
- **AND** SHALL receive the authorization code via callback
- **AND** SHALL exchange the code for access and refresh tokens
- **AND** SHALL output the token JSON to stdout or a specified file
- **AND** SHALL provide instructions for encrypting the token with sops/age

#### Scenario: Automatic token refresh

- **WHEN** an access token expires (typically after 1 hour)
- **THEN** the system SHALL automatically use the refresh token to obtain a new access token
- **AND** SHALL write the updated token back to the credential file (if writable)
- **AND** SHALL retry the failed API request with the new token
- **AND** SHALL NOT require user intervention
- **AND** SHALL log a warning if the credential file is not writable (will re-read on next restart)

#### Scenario: Token revocation handling

- **WHEN** an API request fails with an authentication error (token revoked)
- **THEN** the system SHALL log the error
- **AND** SHALL mark the account as requiring re-authentication
- **AND** SHALL notify the user via API endpoint or log message
- **AND** SHALL stop sync attempts for that account until re-authenticated

### Requirement: Rate Limiting and Error Handling

The system SHALL respect provider API rate limits and handle errors gracefully with exponential backoff.

#### Scenario: Rate limit exceeded

- **WHEN** a provider API returns a rate limit error (HTTP 429)
- **THEN** the system SHALL wait for the duration specified in the Retry-After header
- **OR** SHALL apply exponential backoff if no Retry-After header is provided
- **AND** SHALL retry the request after the wait period
- **AND** SHALL log the rate limit event for monitoring

#### Scenario: Transient API errors

- **WHEN** a provider API returns a transient error (HTTP 500, 503, network timeout)
- **THEN** the system SHALL retry the request with exponential backoff (1s, 2s, 4s, 8s, 16s)
- **AND** SHALL fail after 5 retry attempts
- **AND** SHALL log the failure for debugging

#### Scenario: Permanent API errors

- **WHEN** a provider API returns a permanent error (HTTP 400, 403, 404)
- **THEN** the system SHALL NOT retry the request
- **AND** SHALL log the error with full request details
- **AND** SHALL continue with the next message (skip the failed one)

### Requirement: Webhook Support for Real-Time Sync

The system SHALL support provider webhooks for real-time notifications of new messages (optional enhancement that falls back to polling if not configured).

#### Scenario: Gmail Pub/Sub webhook

- **WHEN** webhook support is enabled for a Gmail account
- **THEN** the system SHALL subscribe to Gmail Pub/Sub notifications for the user's mailbox
- **AND** SHALL provide an HTTP endpoint to receive push notifications
- **AND** SHALL trigger an immediate sync when a notification is received
- **AND** SHALL fall back to polling if webhook setup fails

#### Scenario: Outlook Graph webhook

- **WHEN** webhook support is enabled for an Outlook account
- **THEN** the system SHALL create a subscription via Microsoft Graph API
- **AND** SHALL provide an HTTP endpoint to receive change notifications
- **AND** SHALL renew subscriptions before they expire (max 3 days for Outlook)

### Requirement: Sync State Persistence

The system SHALL persist sync state to enable efficient incremental syncs and recovery from interruptions.

#### Scenario: Store sync state

- **WHEN** a sync operation completes successfully
- **THEN** the system SHALL update the `last_sync` timestamp in the accounts table
- **AND** SHALL store provider-specific cursors (historyId, deltaLink, UIDNEXT) in the account settings JSON
- **AND** SHALL commit the transaction atomically

#### Scenario: Resume after interruption

- **WHEN** the sync process is interrupted (crash, restart, network loss)
- **THEN** the next sync operation SHALL read the last stored sync state
- **AND** SHALL resume from the last successful sync point
- **AND** SHALL NOT re-process already synced messages

### Requirement: Label Mapping Configuration

The system SHALL allow users to configure how AI tags map to provider labels, including label naming and colors.

#### Scenario: Default label mapping

- **WHEN** no custom label mapping is configured
- **THEN** the system SHALL use a default mapping:
  - AI tag `work` → Gmail label `AI/Work` (blue)
  - AI tag `finance` → Gmail label `AI/Finance` (green)
  - AI tag `todo` → Gmail label `AI/ToDo` (orange)
  - AI tag `prio-high` → Gmail label `AI/Priority` (red)

#### Scenario: Custom label prefix

- **WHEN** a user configures a custom label prefix (e.g., `MyAI`)
- **THEN** the system SHALL create labels with the custom prefix:
  - AI tag `work` → Gmail label `MyAI/Work`

#### Scenario: Label color customization

- **WHEN** a user specifies custom colors for labels in configuration
- **THEN** the system SHALL create labels with the specified colors
- **AND** SHALL update existing labels if colors change

### Requirement: Batch Operations

The system SHALL batch API requests when possible to minimize API calls and improve efficiency.

#### Scenario: Batch message fetch

- **WHEN** fetching messages from a provider
- **THEN** the system SHALL request up to 100 messages per API call (provider maximum)
- **AND** SHALL paginate through results if more messages are available
- **AND** SHALL respect rate limits between batch requests

#### Scenario: Batch label updates

- **WHEN** multiple messages need label updates
- **THEN** the system SHOULD use provider batch update APIs if available (Gmail batchModify)
- **OR** SHALL process updates sequentially with minimal delay if batch APIs are unavailable
