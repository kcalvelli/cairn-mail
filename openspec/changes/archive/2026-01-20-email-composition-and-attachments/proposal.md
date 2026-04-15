# Change: Email Composition, Sending & Attachments

## Why

Currently, cairn-mail is a **read-only email organizer**. Users can view, search, tag, and delete messages, but cannot:
- Compose new emails
- Reply to or forward messages
- Send emails
- Download or view attachments
- Upload attachments to new messages
- Save drafts

This severely limits the product's usefulness. Users must switch to Gmail's webmail or another client to perform these basic email operations, defeating the purpose of having a unified email interface.

**User Pain Points:**
- "I can see someone sent me a document, but I can't download it"
- "I want to reply to this message, but have to open Gmail in my browser"
- "I can't attach files when composing in cairn-mail"
- "Inline images don't display in message bodies"
- "No way to save drafts while composing"

**Business Impact:**
Without composition and sending, cairn-mail is incomplete as an email client. Users will continue using Gmail/Outlook webmail for actual email work, reducing the value proposition of this tool to "just another email viewer with AI tags."

## What Changes

### Email Composition Features

**Compose New Message:**
- Rich text editor (WYSIWYG) with HTML support
- Plain text fallback option
- Subject line, To/Cc/Bcc fields
- Auto-complete for email addresses (from message history)
- Save as draft (auto-save every 30 seconds)
- Discard draft with confirmation

**Reply & Forward:**
- Reply: Quote original message, preserve thread_id
- Reply All: Include all original recipients
- Forward: Include original message and attachments
- Quoted text formatting (> prefix or indentation)
- Preserve email thread continuity

**Draft Management:**
- Auto-save drafts to database
- List all saved drafts
- Resume editing draft
- Delete draft
- Drafts folder in UI

### Attachment Handling

**Upload Attachments (Compose):**
- Drag-and-drop file upload
- File picker dialog
- Multiple attachments support
- File size limits (provider-dependent: Gmail 25MB, IMAP varies)
- Progress indicator for uploads
- Remove attachment before sending

**Download Attachments (View):**
- Display attachment list with icons and sizes
- Download individual attachments
- Download all attachments (ZIP)
- Preview common file types (images, PDFs, text)
- Inline image display in HTML messages

**Attachment Storage:**
- Store uploaded attachments temporarily in database BLOB
- Base64 encoding for provider API transmission
- Clean up after send/discard
- Cache downloaded attachments (optional)

### SMTP Sending

**Sending Methods:**

1. **Gmail API** (for Gmail accounts):
   - Use Gmail API messages.send()
   - Native threading support
   - No SMTP configuration needed
   - Respects Gmail's 25MB limit

2. **IMAP + SMTP** (for IMAP accounts):
   - Send via SMTP server
   - Store sent message in IMAP Sent folder
   - SMTP credentials from Nix config
   - TLS/SSL support

**Send Operations:**
- Validate recipients (basic email format check)
- Build MIME multipart message
- Encode attachments as base64
- Send via provider API or SMTP
- Move draft to Sent folder
- Update thread_id on replies
- Handle send failures gracefully

### Web UI Updates

**Compose View (New Page):**
- `/compose` - New message
- `/compose?reply={id}` - Reply to message
- `/compose?forward={id}` - Forward message
- `/compose?draft={id}` - Edit draft

**UI Components:**
- Rich text editor (TinyMCE, Quill, or Tiptap)
- Recipient field with autocomplete chips
- Attachment upload area with previews
- Send/Save Draft/Discard action buttons
- Character/attachment size indicators

**Message View Updates:**
- Download attachment buttons
- Inline image rendering in HTML bodies
- Reply/Forward action buttons
- Attachment preview thumbnails

**Drafts Folder:**
- New folder navigation item
- List drafts with subject, timestamp, recipients
- "Continue editing" action

### Database Schema

**New Table: `drafts`**
```sql
CREATE TABLE drafts (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    thread_id TEXT,  -- For replies
    in_reply_to TEXT,  -- Message ID being replied to
    subject TEXT NOT NULL,
    to_emails TEXT NOT NULL,  -- JSON array
    cc_emails TEXT,  -- JSON array
    bcc_emails TEXT,  -- JSON array
    body_text TEXT,
    body_html TEXT,
    attachments TEXT,  -- JSON array of attachment metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);
```

**New Table: `attachments`**
```sql
CREATE TABLE attachments (
    id TEXT PRIMARY KEY,
    draft_id TEXT,  -- NULL for received message attachments
    message_id TEXT,  -- NULL for draft attachments
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size INTEGER NOT NULL,
    data BLOB,  -- Base64 or binary data
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (draft_id) REFERENCES drafts(id) ON DELETE CASCADE,
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
);
```

### API Endpoints

**Composition:**
- `POST /api/drafts` - Create new draft
- `GET /api/drafts` - List all drafts
- `GET /api/drafts/{id}` - Get draft by ID
- `PUT /api/drafts/{id}` - Update draft
- `DELETE /api/drafts/{id}` - Delete draft
- `POST /api/messages/send` - Send message (from draft or direct)
- `POST /api/messages/{id}/reply` - Create reply draft
- `POST /api/messages/{id}/forward` - Create forward draft

**Attachments:**
- `POST /api/attachments/upload` - Upload attachment (returns ID)
- `GET /api/attachments/{id}` - Download attachment
- `GET /api/attachments/{id}/preview` - Get attachment preview/thumbnail
- `DELETE /api/attachments/{id}` - Delete attachment
- `GET /api/messages/{id}/attachments` - List message attachments

### Provider Updates

**Gmail Provider:**
- Implement `send_message(draft)` using Gmail API
- Implement `get_attachment(attachment_id)`
- Handle attachment encoding/decoding
- Thread ID management for replies

**IMAP Provider:**
- Implement `send_message(draft)` using SMTP
- Store sent message in IMAP Sent folder
- SMTP configuration from account settings
- TLS/STARTTLS support

## Impact

### Affected Capabilities
- `email-composition` (NEW) - Compose, reply, forward, drafts
- `email-attachments` (NEW) - Upload, download, view attachments
- `smtp-sending` (NEW) - Send messages via providers
- `gmail-provider` (MODIFIED) - Add send and attachment methods
- `imap-provider` (MODIFIED) - Add SMTP sending and Sent folder handling
- `web-ui` (MODIFIED) - Compose view, attachment UI, editor integration

### Affected Code

**New:**
- `src/cairn_mail/db/drafts.py` - Draft management
- `src/cairn_mail/db/attachments.py` - Attachment storage
- `src/cairn_mail/api/routes/drafts.py` - Draft API endpoints
- `src/cairn_mail/api/routes/attachments.py` - Attachment API endpoints
- `src/cairn_mail/email/composer.py` - MIME message builder
- `src/cairn_mail/email/smtp.py` - SMTP client wrapper
- `web/src/pages/ComposePage.tsx` - Composition UI
- `web/src/components/RichTextEditor.tsx` - Editor component
- `web/src/components/AttachmentUpload.tsx` - Upload UI
- `web/src/components/AttachmentList.tsx` - Attachment display
- `alembic/versions/005_add_drafts_and_attachments.py` - Migration

**Modified:**
- `src/cairn_mail/providers/base.py` - Add send/attachment methods
- `src/cairn_mail/providers/implementations/gmail.py` - Gmail send implementation
- `src/cairn_mail/providers/implementations/imap.py` - SMTP integration
- `src/cairn_mail/db/models.py` - Add Draft and Attachment models
- `web/src/pages/MessageDetailPage.tsx` - Add reply/forward buttons
- `web/src/components/Sidebar.tsx` - Add Drafts folder
- `modules/home-manager/default.nix` - Add SMTP config options

## Breaking Changes

**None** - This is additive functionality. All existing features continue to work unchanged.

## User-Facing Changes

### Before
- Read-only email viewer
- Cannot compose or send emails
- Cannot download attachments
- Cannot reply to messages
- Must use Gmail webmail for email actions

### After
- **Full email client** capabilities
- Compose new messages with rich text
- Reply and forward with quoted text
- Upload and send attachments
- Download and view received attachments
- Save drafts with auto-save
- Send via Gmail API or SMTP
- Inline image display
- Complete email workflow in one application

## Dependencies

**Required:**
- Phase 5 (Folders) - Drafts folder, Sent folder
- Phase 6 (Provider Sync) - Send operations sync to provider

**External Libraries:**
- Rich text editor: Tiptap (MIT license, React-friendly)
- SMTP client: Python `smtplib` (built-in)
- MIME building: Python `email.mime` (built-in)
- File upload: FastAPI `UploadFile`
- Base64 encoding: Python `base64` (built-in)

## Out of Scope (Future Phases)

- Email templates and signatures
- Scheduled sending
- Read receipts
- Encryption (PGP/S/MIME)
- Calendar invitations (.ics files)
- Contact management
- Email aliases
- Undo send
- Spell check
- Link preview generation

## Security Considerations

1. **Attachment Size Limits**: Enforce per-provider limits to prevent DoS
2. **File Type Validation**: Check MIME types, block executable files
3. **SMTP Credentials**: Store encrypted in Nix secrets (sops/agenix)
4. **XSS Prevention**: Sanitize HTML in rich text editor output
5. **CSRF Protection**: FastAPI CSRF tokens for upload endpoints
6. **Attachment Storage**: Clean up orphaned attachments periodically

## Performance Considerations

1. **Attachment Storage**: Use BLOB for files <10MB, filesystem for larger (future)
2. **Auto-save Throttling**: Debounce draft saves to every 30 seconds
3. **Attachment Encoding**: Stream base64 encoding for large files
4. **SMTP Connection Pooling**: Reuse SMTP connections when possible
5. **Draft Cleanup**: Background job to delete old auto-saved drafts

## Testing Strategy

### Unit Tests
- Draft CRUD operations
- Attachment upload/download
- MIME message building
- SMTP connection handling
- Provider send methods

### Integration Tests
- End-to-end compose → send → receive flow
- Reply with thread preservation
- Forward with attachments
- Draft auto-save and resume
- Attachment size limit enforcement

### Manual Testing
- Compose and send via Gmail
- Compose and send via IMAP/SMTP
- Upload various file types
- Download attachments
- Reply to threaded conversations
- Forward messages with attachments
- Test with Fastmail, Gmail, self-hosted IMAP

## Migration Plan

### Phase 1: Database Schema (Non-Breaking)
1. Add `drafts` table via Alembic migration
2. Add `attachments` table via Alembic migration
3. No changes to existing tables
4. Deploy with feature flag disabled

### Phase 2: Backend Implementation
1. Implement draft management API
2. Implement attachment handling
3. Implement MIME message builder
4. Add provider send methods (Gmail, IMAP/SMTP)
5. Deploy backend only (no UI)

### Phase 3: Frontend Implementation
1. Add Compose page with rich text editor
2. Add attachment upload/download UI
3. Add reply/forward buttons
4. Add Drafts folder navigation
5. Enable feature flag

### Phase 4: Validation & Rollout
1. Manual testing with all providers
2. Monitor attachment storage growth
3. Monitor SMTP send success rates
4. Collect user feedback
5. Iterate on UX improvements

### Rollback Plan
- Feature flag to disable composition UI
- Database migrations are additive (no data loss on rollback)
- Provider changes are backwards compatible
- Can revert to read-only mode without data corruption
