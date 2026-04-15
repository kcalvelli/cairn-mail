# Design: Phase 4 - Enhanced Email Experience

## Context

Phase 3 delivered working IMAP provider support with Gmail API integration. Users can sync multiple accounts (Gmail + IMAP), classify messages with local LLM, and view results in the web UI. This phase enhances the core email experience with real-time updates, full message viewing, and standard email operations.

**Stakeholders**: End users who want a complete email client experience in the web UI.

**Constraints**:
- Must maintain local-first architecture (no cloud dependencies beyond email providers)
- Must work with both Gmail API and generic IMAP
- Must not break existing sync functionality

## Goals / Non-Goals

### Goals
- Real-time email notifications via IMAP IDLE
- View complete email content including HTML body
- Search and filter across all synced messages
- Perform standard email operations (read/delete)
- Support multiple folders beyond INBOX

### Non-Goals (deferred)
- Email composition/sending (future phase)
- Attachment download/preview
- Email forwarding/reply
- Drag-and-drop folder management
- Offline mode

## Decisions

### Decision 1: IMAP IDLE Implementation

**What**: Use a dedicated background thread per IMAP account for IDLE connections.

**Why**: IDLE requires a persistent connection that blocks. A background thread allows the main application to continue processing while listening for new mail.

**Alternatives considered**:
- **asyncio with aioimap**: More complex, adds dependency, limited benefit since IDLE is inherently blocking
- **Systemd socket activation**: Over-engineered for this use case
- **Polling only**: User requested real-time, polling has 5-minute delay

**Implementation**:
```python
class IMAPIdleManager:
    def __init__(self, account_id: str, config: IMAPConfig, callback: Callable):
        self.thread = threading.Thread(target=self._idle_loop, daemon=True)

    def _idle_loop(self):
        while self.running:
            try:
                conn = self._connect()
                conn.idle()  # Blocks until new mail or timeout
                if conn.idle_check(timeout=29*60):  # RFC recommends <30min
                    self.callback(self.account_id)
                conn.idle_done()
            except Exception:
                time.sleep(30)  # Reconnect after delay
```

### Decision 2: Multi-folder Architecture

**What**: Add `folder` column to messages table, sync configurable folders per account.

**Why**: Users need access to sent mail, drafts, and archived messages. Folder is a natural organizational unit.

**Folder mapping**:
| Logical Name | Gmail API | IMAP (standard) |
|--------------|-----------|-----------------|
| inbox | INBOX | INBOX |
| sent | SENT | Sent, "Sent Mail", "Sent Items" |
| drafts | DRAFT | Drafts |
| archive | All Mail (minus labels) | Archive |
| trash | TRASH | Trash, "Deleted Items" |

**Configuration (Nix)**:
```nix
programs.cairn-mail.accounts.work = {
  provider = "imap";
  folders = [ "inbox" "sent" "archive" ];  # Default: [ "inbox" ]
};
```

### Decision 3: Email Body Storage

**What**: Store full email body in database, render in UI on demand.

**Why**: Fetching body from server on every click is slow. Local storage enables instant display and offline viewing.

**Trade-offs**:
- **Pro**: Fast display, enables search, works offline
- **Con**: Increases database size (~50KB-200KB per email with HTML)

**Schema change**:
```sql
ALTER TABLE messages ADD COLUMN body_text TEXT;
ALTER TABLE messages ADD COLUMN body_html TEXT;
```

**Rendering**: Use `dangerouslySetInnerHTML` with DOMPurify sanitization for HTML emails. Fall back to plain text if HTML not available.

### Decision 4: Search Implementation

**What**: SQLite FTS5 (Full-Text Search) on subject, from_email, body_text.

**Why**: Fast, built-in to SQLite, no external dependencies.

**Alternatives considered**:
- **Meilisearch/Elasticsearch**: Over-engineered for local use
- **LIKE queries**: Too slow for large mailboxes
- **Notmuch**: Would require Maildir storage, conflicts with API-based architecture

**Implementation**:
```sql
CREATE VIRTUAL TABLE messages_fts USING fts5(
    subject, from_email, body_text,
    content='messages',
    content_rowid='rowid'
);
```

### Decision 5: Read/Delete Operations

**What**: Immediate server sync with optimistic UI update.

**Why**: Users expect instant feedback. If server sync fails, show error and revert.

**Flow**:
1. User clicks "mark as read" or "delete"
2. UI updates immediately (optimistic)
3. Background task syncs to server
4. On failure: revert UI, show toast notification

**IMAP commands**:
- Mark read: `STORE uid +FLAGS (\Seen)`
- Mark unread: `STORE uid -FLAGS (\Seen)`
- Delete: `STORE uid +FLAGS (\Deleted)` then `EXPUNGE` (or move to Trash)

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| IDLE connection drops | Auto-reconnect with exponential backoff |
| Large database from body storage | Compress old messages, configurable retention |
| FTS index size | Rebuild index periodically, limit indexed fields |
| HTML email security (XSS) | DOMPurify sanitization, CSP headers |
| Server sync failures | Retry queue, user notification |

## Migration Plan

1. **Database migration**: Add body_text, body_html, folder columns
2. **Backfill bodies**: Fetch bodies for existing messages (background task)
3. **Create FTS index**: Populate from existing messages
4. **Enable IDLE**: Start idle threads for IMAP accounts
5. **Rollback**: Drop new columns, revert to polling-only

## Open Questions

1. **Attachment handling**: Store metadata only or download content? (Deferred)
2. **HTML email images**: Block remote images by default? Allow user preference?
3. **Folder sync frequency**: Sync all folders on timer, or only on folder switch?
4. **Delete behavior**: Immediate expunge or move to trash first?
