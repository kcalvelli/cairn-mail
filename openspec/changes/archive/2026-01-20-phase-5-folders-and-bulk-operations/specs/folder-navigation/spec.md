# Capability: Multi-Folder Navigation

## ADDED Requirements

### Requirement: Users SHALL be able to navigate between different email folders

Users MUST have access to standard email folders beyond just INBOX (Sent, Drafts, Archive, Trash) to manage their complete email workflow.

#### Scenario: View folder list in sidebar

**Given** the user has configured folders: Inbox, Sent, Drafts, Archive, Trash
**When** the user opens the web UI
**Then** a "Folders" section appears in the sidebar
**And** all configured folders are listed with appropriate icons
**And** each folder shows a message count badge
**And** "Inbox" is selected by default
**And** the Inbox folder is highlighted

#### Scenario: Navigate to Sent folder

**Given** the user is viewing the Inbox folder
**And** the Sent folder shows "12" in the count badge
**When** the user clicks "Sent" in the folder list
**Then** the message list updates to show messages from the Sent folder
**And** the Sent folder is highlighted in the sidebar
**And** the URL updates to include ?folder=sent
**And** the message list shows 12 sent messages
**And** each message displays the recipient email (To:) instead of sender

#### Scenario: Navigate to Drafts folder

**Given** the user is viewing any folder
**When** the user clicks "Drafts"
**Then** the message list shows draft messages
**And** draft messages display a "Draft" label/badge
**And** the URL includes ?folder=drafts

#### Scenario: Navigate to Trash folder

**Given** the user has deleted 5 messages
**When** the user clicks "Trash" in the folder list
**Then** the trash folder is selected
**And** the message list shows the 5 deleted messages
**And** a "Permanently Delete" option is available for trash items

### Requirement: Folder message counts SHALL be accurate and update in real-time

Folder counts MUST reflect the actual number of messages and update when messages are moved/deleted.

#### Scenario: Folder count updates after deletion

**Given** the Inbox folder shows "50" messages
**When** the user deletes 3 messages from Inbox
**Then** the Inbox count updates to "47"
**And** the Trash count increases by 3

#### Scenario: Folder count updates after bulk delete

**Given** the Inbox folder shows "100" messages
**And** the user has filtered to show only "newsletter" tag (25 messages)
**When** the user executes "Delete All"
**Then** the Inbox count decreases by 25 to "75"
**And** the Trash count increases by 25

#### Scenario: Unread count per folder

**Given** the Inbox folder has 50 total messages, 12 unread
**When** the folder list is displayed
**Then** the Inbox shows "50" as total count
**And** displays a separate unread indicator "12 unread"
**Or** displays "12/50" to show unread/total

### Requirement: Backend SHALL sync messages from multiple folders

The sync process MUST fetch messages from all configured folders, not just INBOX.

#### Scenario: Multi-folder sync via IMAP

**Given** an IMAP account configured with folders: ["INBOX", "Sent", "Drafts"]
**When** the sync process runs
**Then** the system executes IMAP SELECT for each folder
**And** fetches messages from each folder
**And** stores each message with its folder name
**And** all folder contents are available in the database

**Example database records**:
```
message_id: "msg1", folder: "INBOX", subject: "Meeting tomorrow"
message_id: "msg2", folder: "Sent", subject: "RE: Project update"
message_id: "msg3", folder: "Drafts", subject: "(Draft) Proposal"
```

#### Scenario: Folder name mapping for Gmail

**Given** a Gmail account
**When** syncing folders
**Then** Gmail labels are mapped to logical folder names:
- "[Gmail]/Sent Mail" → "Sent"
- "[Gmail]/Drafts" → "Drafts"
- "[Gmail]/Trash" → "Trash"
- "[Gmail]/All Mail" → "Archive"

#### Scenario: Folder name mapping for Fastmail

**Given** a Fastmail IMAP account
**When** syncing folders
**Then** standard IMAP folders are mapped:
- "INBOX" → "Inbox"
- "Sent Items" → "Sent"
- "Drafts" → "Drafts"
- "Trash" → "Trash"

### Requirement: API SHALL support folder-based filtering and queries

The API MUST allow filtering messages by folder and provide folder statistics.

#### Scenario: List messages in specific folder

**Given** a GET request to /api/messages?folder=sent
**When** the API processes the request
**Then** only messages with folder="sent" are returned
**And** the response matches MessagesListResponse schema
**And** pagination works within the folder scope

#### Scenario: Get folder list with stats

**Given** a GET request to /api/folders?account_id=work
**When** the API processes the request
**Then** the response includes all folders for that account:
```json
{
  "folders": [
    {
      "name": "Inbox",
      "message_count": 50,
      "unread_count": 12
    },
    {
      "name": "Sent",
      "message_count": 23,
      "unread_count": 0
    },
    {
      "name": "Drafts",
      "message_count": 3,
      "unread_count": 3
    }
  ]
}
```

#### Scenario: Combine folder and tag filters

**Given** a GET request to /api/messages?folder=inbox&tags=work&tags=urgent
**When** the API processes the request
**Then** only messages in Inbox folder with tags "work" OR "urgent" are returned

### Requirement: Database schema SHALL support folder field

Messages table MUST include a folder column for efficient folder-based queries.

#### Scenario: Database schema includes folder column

**Given** the messages table schema
**Then** a "folder" column exists with type VARCHAR(255)
**And** the default value is "INBOX"
**And** an index exists on (account_id, folder) for performance
**And** an index exists on (account_id, folder, date) for sorted queries

#### Scenario: Alembic migration creates folder column

**Given** a database running the Phase 4 schema
**When** the Phase 5 Alembic migration runs
**Then** the folder column is added
**And** existing messages are updated to folder='INBOX'
**And** indexes are created
**And** the migration is reversible (can downgrade)

### Requirement: Folder configuration SHALL be per-account

Different email accounts MUST support different folder structures and naming conventions.

#### Scenario: Configure folders in Nix module

**Given** a Nix configuration for an IMAP account:
```nix
programs.cairn-mail.accounts.work = {
  provider = "imap";
  email = "user@fastmail.com";
  folders = ["INBOX", "Sent Items", "Drafts", "Archive"];
};
```
**When** the configuration is generated
**Then** the account settings include the folders list
**And** the sync process uses these folder names

#### Scenario: Default folders if not specified

**Given** an account configuration without explicit folders
**When** the sync process runs
**Then** default folders are used: ["INBOX", "Sent"]
**And** other folders are not synced

### Requirement: Folder operations SHALL sync to email provider

Actions performed in a folder (delete, mark read) MUST sync to the corresponding IMAP/Gmail folder.

#### Scenario: Delete from Trash permanently deletes

**Given** a message in the Trash folder
**When** the user deletes it from Trash
**Then** the message is permanently deleted (IMAP EXPUNGE)
**And** the message is removed from the database
**And** it cannot be recovered

#### Scenario: Delete from Inbox moves to Trash

**Given** a message in the Inbox folder
**When** the user deletes it
**Then** the message is moved to Trash folder (IMAP COPY + DELETE)
**Or** the IMAP \Deleted flag is set and EXPUNGE is deferred
**And** the database record is updated to folder="Trash"

### Requirement: Users SHALL be able to filter by account by treating accounts as tags

Since the inbox and folder structure are unified across all accounts, users MUST be able to filter by email account by clicking account tags in the Tags section, maintaining the tag-focused filtering approach.

#### Scenario: View accounts as tags in Tags section

**Given** the user has configured 2 email accounts: "work" and "personal"
**When** the user opens the web UI
**Then** the "Tags" section includes account tags alongside AI-generated tags
**And** each account appears as a tag chip showing the account ID or email address
**And** account tags show a message count badge (like other tags)
**And** account tags use the same visual styling as regular tags (outlined chips)
**And** account tags are clearly identifiable (e.g., different icon or label prefix)

#### Scenario: Filter messages by clicking account tag

**Given** the Tags section displays "work" (150 messages) and "personal" (75 messages)
**And** the Tags section also displays AI tags like "urgent" and "newsletter"
**When** the user clicks the "work" account tag
**Then** the tag is visually highlighted (filled/selected state)
**And** the message list updates to show only messages from "work" account
**And** the URL updates to include ?tags=work
**And** the message list shows 150 messages
**When** the user clicks the "work" tag again
**Then** the filter is removed
**And** all messages from all accounts are shown
**And** the chip returns to outlined state

#### Scenario: Combine account tags with AI tags

**Given** the user has clicked the "work" account tag (selected)
**And** the message list shows only work messages
**When** the user clicks the "urgent" AI tag
**Then** both "work" AND "urgent" tags are selected/highlighted
**And** the message list shows messages with either "work" account OR "urgent" tag (OR logic)
**And** the URL includes ?tags=work&tags=urgent
**And** both filters can be cleared independently

**Note**: Tags already support multi-selection with OR logic, so account tags behave identically to AI tags.

#### Scenario: Account tag count badges update after operations

**Given** the "work" account tag shows "50" messages
**And** the user has filtered to show work messages
**When** the user bulk deletes 10 messages
**Then** the "work" account tag badge updates to "40"
**And** the count reflects the new total across all folders

#### Scenario: Distinguish account tags from AI tags visually

**Given** the Tags section displays both account tags and AI tags
**When** the user views the Tags section
**Then** account tags have a visual indicator (e.g., email icon, "@" prefix, or lighter color)
**And** AI tags have their own visual indicator (e.g., robot icon or semantic colors)
**And** both types of tags use the same interaction pattern (clickable chips)

**Alternative**: Use subsections within Tags:
- "Accounts" subsection header with account tags
- "Categories" subsection header with AI tags

#### Scenario: Account tags use account name or email

**Given** an account configured with id="work" and email="user@company.com"
**When** the account tag is displayed in the Tags section
**Then** the tag shows the account ID "work" (if human-readable)
**Or** the tag shows the email address "user@company.com" (if no custom name)
**And** hovering shows the full email address in a tooltip

## MODIFIED Requirements

### Requirement: Message listing SHALL filter by folder in addition to tags

The message listing API MUST support filtering by folder field in addition to existing filters (account, tags, read status).

**Previously**: Messages were filtered only by account, tags, and read status.

**Now**: Messages MUST also be filterable by folder field.

#### Scenario: Filter by folder and tags

**Given** a message list filtered by folder="Inbox" and tag="work"
**When** the query executes
**Then** only messages in Inbox with tag "work" are returned

## REMOVED Requirements

None - this is additive functionality.
