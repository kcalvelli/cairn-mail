# Change: Phase 4 - Enhanced Email Experience

## Why

Phase 3 established working IMAP provider support with basic sync functionality. However, the current implementation has several limitations that affect the user experience:

1. **Polling-based sync**: IMAP accounts sync every 5 minutes via timer, causing delays in seeing new mail
2. **Single folder**: Only INBOX is synced, missing sent mail, drafts, and archived messages
3. **No search**: Users cannot search or filter messages in the web UI
4. **Missing email body**: Clicking an email only shows metadata/snippet, not full content
5. **Read status not synced**: Reading an email in the UI doesn't mark it as read on the server
6. **No deletion**: Users cannot delete unwanted emails from the UI

## What Changes

### IMAP IDLE Support
- Implement IMAP IDLE for real-time push notifications
- Fall back to polling for servers that don't support IDLE
- Maintain persistent connections for instant new mail detection

### Multi-folder Support
- Sync additional folders: Sent, Drafts, Archive, Trash
- Configurable folder list per account in Nix config
- Folder selection in web UI sidebar

### Web UI Search & Filtering
- Full-text search across subject, from, body
- Filter by: tags, account, date range, read/unread status
- Saved searches / smart folders

### Email Body Display
- Fetch and display full email body when clicked
- Support HTML and plain text rendering
- Display attachments list (download deferred to future phase)

### Read Status Sync
- Mark messages as read on server when opened in UI
- Sync read/unread status bidirectionally
- Batch mark as read/unread

### Email Deletion
- Delete single or multiple emails
- Move to trash vs permanent delete option
- Sync deletion to server

## Impact

- Affected capabilities: `imap-provider`, `web-ui`, `email-management`
- Affected code:
  - `src/cairn_mail/providers/implementations/imap.py` - IDLE, multi-folder, delete
  - `src/cairn_mail/api/routes/messages.py` - body fetch, mark read, delete
  - `src/cairn_mail/db/models.py` - folder field, body storage
  - `web/src/pages/InboxPage.tsx` - search, filtering, folder nav
  - `web/src/components/MessageDetail.tsx` - full body display
  - `modules/home-manager/default.nix` - folder configuration
