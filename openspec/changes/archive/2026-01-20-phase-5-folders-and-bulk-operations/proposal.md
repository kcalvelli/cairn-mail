# Change: Phase 5 - Folders and Bulk Operations

## Why

Phase 4 successfully implemented single message operations (view body, mark read, delete) and basic tag filtering. However, the web UI is still missing key productivity features that users expect from a modern email client:

1. **No bulk operations**: Users cannot select multiple messages to delete, mark as read, or retag them - they must click each message individually, which is tedious for managing large volumes of email
2. **Single folder view**: Only INBOX is displayed - users cannot access Sent, Drafts, Archive, or Trash folders
3. **No "select all"**: No way to quickly select all messages matching current filter for bulk actions
4. **Polling-based sync**: IMAP accounts sync every 5 minutes, causing delays in seeing new mail
5. **No visual feedback for selection**: Users need clear indication of which messages are selected and what actions are available
6. **Inconsistent filtering UX**: Tags have a rich filtering UI in the sidebar, but account filtering is hidden or inconsistent - users expect to filter by account using the same interaction pattern as tags

User quote: *"ability to delete messages from the main screen. There should be a UI element to show radio buttons to the left of every message when clicked, that can then be selected, and a trash icon that will delete the selected messages. There should also be a delete all option."*

## What Changes

### Bulk Selection UI
- Add checkbox to the left of each message in the list
- "Select All" checkbox in the list header to toggle all visible messages
- Visual indication of selected state (highlighted row, count badge)
- Floating action bar appears when messages are selected
- Actions: Delete, Mark Read/Unread, Add/Remove Tags

### Bulk Operations API
- POST /api/messages/bulk/read - Mark multiple messages as read/unread
- POST /api/messages/bulk/delete - Delete multiple messages
- POST /api/messages/bulk/tags - Update tags for multiple messages
- All operations sync to email providers (IMAP, Gmail)

### Delete All Functionality
- "Delete All" button in toolbar (contextual based on current view/filter)
- Confirmation dialog showing count and filter criteria
- Executes bulk delete of all messages matching current filter
- Option to permanently delete vs move to trash

### Multi-folder Support
- Folder navigation at top of sidebar: Inbox, Sent, Trash
- Sync additional folders beyond INBOX during sync operation
- Database schema updated to include folder field on messages
- Folder configuration per account in Nix config
- Clicking folder shows messages from that folder across all accounts

### IMAP IDLE for Real-time Sync
- Implement IMAP IDLE for push notifications
- Maintain persistent connection for instant new mail detection
- Fall back to polling for servers without IDLE support
- WebSocket notifications to update UI in real-time
- Systemd service updated for long-running IDLE connection

### Unified Account and Tag Filtering
- Treat accounts as tags in the existing Tags section
- Each account appears as a clickable tag chip (e.g., "kc.calvelli@gmail.com", "work", "personal")
- No separate Accounts section - maintains tag-focused filtering approach
- Clicking account tag filters to show only messages from that account
- Combine account tags + AI tags + folder filters seamlessly
- Show message count per account (like other tag counts)

## Impact

- Affected capabilities: `web-ui`, `email-management`, `imap-provider`, `gmail-provider`
- Affected code:
  - `web/src/components/MessageList.tsx` - Bulk selection checkboxes
  - `web/src/components/BulkActionBar.tsx` - NEW: Floating action bar
  - `web/src/components/Sidebar.tsx` - Folder navigation
  - `web/src/hooks/useMessages.ts` - Bulk operation hooks
  - `src/cairn_mail/api/routes/messages.py` - Bulk endpoints (already exist, need testing)
  - `src/cairn_mail/providers/implementations/imap.py` - Multi-folder, IDLE
  - `src/cairn_mail/db/models.py` - Add folder field
  - `modules/home-manager/default.nix` - Folder configuration

## Breaking Changes

None - this is additive functionality. Existing single-message operations remain unchanged.

## User-Facing Changes

### Before
- Click individual messages to open, mark read, or delete
- Only see INBOX messages
- Wait up to 5 minutes for new mail to appear
- Account filtering requires dropdown or hidden UI

### After
- Select multiple messages with checkboxes
- Bulk delete/mark read/retag selected messages
- "Delete All" option for current view
- Navigate between Inbox, Sent, Drafts, Archive, Trash
- New mail appears instantly (if IDLE supported)
- Filter by account using same UI as tags (clickable chips in sidebar)
