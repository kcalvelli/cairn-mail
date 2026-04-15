# mcp-server Specification

## Purpose

Provide an MCP (Model Context Protocol) server that exposes cairn-mail's email capabilities as tools for AI assistants, enabling natural language email automation workflows.

## ADDED Requirements

### Requirement: MCP Server Initialization

The system SHALL provide an MCP server that starts via CLI and communicates over stdio transport.

#### Scenario: Starting MCP server

- **GIVEN** cairn-mail is installed
- **WHEN** user runs `cairn-mail mcp`
- **THEN** an MCP server starts listening on stdio
- **AND** the server advertises available tools to the client

#### Scenario: Custom API URL

- **GIVEN** the web API is running on a non-default port
- **WHEN** user runs `cairn-mail mcp --api-url http://localhost:9000`
- **THEN** the MCP server connects to the specified API URL

#### Scenario: API not reachable

- **GIVEN** the web API is not running
- **WHEN** an MCP tool is invoked
- **THEN** the tool returns an error indicating the API is unreachable
- **AND** suggests checking that the cairn-mail web service is running

### Requirement: List Accounts Tool

The system SHALL provide a `list_accounts` tool that returns all configured email accounts.

#### Scenario: Listing accounts

- **GIVEN** multiple email accounts are configured
- **WHEN** AI assistant calls `list_accounts`
- **THEN** returns a list containing each account's name, email, provider, and ID

#### Scenario: No accounts configured

- **GIVEN** no email accounts are configured
- **WHEN** AI assistant calls `list_accounts`
- **THEN** returns an empty list

### Requirement: Search Emails Tool

The system SHALL provide a `search_emails` tool that queries messages with optional filters.

#### Scenario: Basic text search

- **GIVEN** messages exist in the database
- **WHEN** AI assistant calls `search_emails(query="invoice")`
- **THEN** returns messages matching "invoice" in subject, sender, or body
- **AND** results are limited to 20 by default

#### Scenario: Filter by account name

- **GIVEN** messages exist across multiple accounts
- **WHEN** AI assistant calls `search_emails(account="work")`
- **THEN** returns only messages from the account named "work"

#### Scenario: Filter by unread status

- **GIVEN** both read and unread messages exist
- **WHEN** AI assistant calls `search_emails(unread_only=True)`
- **THEN** returns only unread messages

#### Scenario: Combined filters

- **GIVEN** messages exist with various attributes
- **WHEN** AI assistant calls `search_emails(account="personal", folder="inbox", unread_only=True, limit=5)`
- **THEN** returns up to 5 unread messages from the personal account's inbox

### Requirement: Read Email Tool

The system SHALL provide a `read_email` tool that returns full email content.

#### Scenario: Reading email body

- **GIVEN** a message exists with ID "msg123"
- **WHEN** AI assistant calls `read_email(message_id="msg123")`
- **THEN** returns the full message including subject, sender, recipients, date, and body text
- **AND** includes attachment metadata if attachments are present

#### Scenario: Message not found

- **GIVEN** no message exists with ID "invalid"
- **WHEN** AI assistant calls `read_email(message_id="invalid")`
- **THEN** returns an error indicating the message was not found

### Requirement: Compose Email Tool

The system SHALL provide a `compose_email` tool that creates a draft without sending.

#### Scenario: Creating a draft with explicit account

- **GIVEN** an account named "dev" exists
- **WHEN** AI assistant calls `compose_email(to="joe@example.com", subject="Hello", body="Hi Joe", account="dev")`
- **THEN** creates a draft in the "dev" account
- **AND** returns the draft ID for later sending

#### Scenario: Creating a draft with default account

- **GIVEN** only one account is configured
- **WHEN** AI assistant calls `compose_email(to="joe@example.com", subject="Hello", body="Hi Joe")`
- **THEN** creates a draft in the only available account
- **AND** returns the draft ID

#### Scenario: Ambiguous account selection

- **GIVEN** multiple accounts are configured
- **AND** no account parameter is provided
- **WHEN** AI assistant calls `compose_email(to="joe@example.com", subject="Hello", body="Hi")`
- **THEN** returns an error listing available accounts
- **AND** prompts to specify which account to use

#### Scenario: Multiple recipients

- **GIVEN** an account exists
- **WHEN** AI assistant calls `compose_email(to=["a@example.com", "b@example.com"], cc="c@example.com", subject="Group email", body="Hello all")`
- **THEN** creates a draft with multiple TO recipients and a CC recipient

### Requirement: Send Email Tool

The system SHALL provide a `send_email` tool that sends drafts or composes and sends in one step.

#### Scenario: Sending an existing draft

- **GIVEN** a draft exists with ID "draft123"
- **WHEN** AI assistant calls `send_email(draft_id="draft123")`
- **THEN** the draft is sent via the email provider
- **AND** the draft is deleted after successful send
- **AND** returns the sent message ID

#### Scenario: Compose and send in one step

- **GIVEN** an account named "personal" exists
- **WHEN** AI assistant calls `send_email(to="joe@example.com", subject="Quick note", body="See you tomorrow", account="personal")`
- **THEN** a draft is created internally
- **AND** the draft is immediately sent
- **AND** returns the sent message ID

#### Scenario: Send fails

- **GIVEN** a draft exists but the email provider is unreachable
- **WHEN** AI assistant calls `send_email(draft_id="draft123")`
- **THEN** returns an error explaining the failure
- **AND** the draft is NOT deleted (preserved for retry)

### Requirement: Reply To Email Tool

The system SHALL provide a `reply_to_email` tool that creates reply drafts.

#### Scenario: Reply to single sender

- **GIVEN** a message exists from "alice@example.com"
- **WHEN** AI assistant calls `reply_to_email(message_id="msg123", body="Thanks for the info")`
- **THEN** creates a draft with TO set to "alice@example.com"
- **AND** sets the subject to "Re: [original subject]"
- **AND** includes thread context (in_reply_to, thread_id)
- **AND** returns the draft ID

#### Scenario: Reply all

- **GIVEN** a message exists with multiple recipients
- **WHEN** AI assistant calls `reply_to_email(message_id="msg123", body="Thanks all", reply_all=True)`
- **THEN** creates a draft with all original recipients
- **AND** excludes the user's own address from recipients

### Requirement: Mark Read Tool

The system SHALL provide a `mark_read` tool to change read status of messages.

#### Scenario: Mark single message as read

- **GIVEN** an unread message exists with ID "msg123"
- **WHEN** AI assistant calls `mark_read(message_ids="msg123")`
- **THEN** the message is marked as read
- **AND** returns confirmation of the operation

#### Scenario: Mark multiple messages as unread

- **GIVEN** read messages exist with IDs "msg1", "msg2", "msg3"
- **WHEN** AI assistant calls `mark_read(message_ids=["msg1", "msg2", "msg3"], unread=True)`
- **THEN** all three messages are marked as unread

### Requirement: Delete Email Tool

The system SHALL provide a `delete_email` tool to trash or permanently delete messages.

#### Scenario: Move to trash

- **GIVEN** a message exists with ID "msg123"
- **WHEN** AI assistant calls `delete_email(message_ids="msg123")`
- **THEN** the message is moved to trash
- **AND** returns confirmation

#### Scenario: Permanent delete

- **GIVEN** a message exists with ID "msg123"
- **WHEN** AI assistant calls `delete_email(message_ids="msg123", permanent=True)`
- **THEN** the message is permanently deleted
- **AND** cannot be restored

#### Scenario: Bulk delete

- **GIVEN** messages exist with IDs "msg1", "msg2"
- **WHEN** AI assistant calls `delete_email(message_ids=["msg1", "msg2"])`
- **THEN** both messages are moved to trash

### Requirement: Account Name Resolution

The system SHALL resolve human-readable account names to account IDs.

#### Scenario: Resolve by name

- **GIVEN** an account exists with name "dev" and ID "abc-123"
- **WHEN** a tool receives `account="dev"`
- **THEN** the account ID "abc-123" is used for the API call

#### Scenario: Resolve by ID

- **GIVEN** an account exists with ID "abc-123"
- **WHEN** a tool receives `account="abc-123"`
- **THEN** the account ID "abc-123" is used directly

#### Scenario: Partial name match

- **GIVEN** accounts exist with names "work-gmail" and "work-imap"
- **WHEN** a tool receives `account="work"`
- **THEN** returns an error indicating ambiguous match
- **AND** lists both "work-gmail" and "work-imap" as options

#### Scenario: Name not found

- **GIVEN** no account exists matching "unknown"
- **WHEN** a tool receives `account="unknown"`
- **THEN** returns an error indicating account not found
- **AND** lists available account names
