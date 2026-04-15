# Change: Sync Trash Operations to Providers

## Why

Phase 5 implemented comprehensive folder and bulk operations in the web UI, including:
- Move messages to trash
- Restore messages from trash
- Permanently delete selected messages
- Clear all trash

However, **these operations only update the local SQLite database**. They do not sync back to the email provider (Gmail, IMAP), creating a critical inconsistency between the cairn-mail UI and the actual email server state.

**User Impact:**
- Messages deleted in cairn-mail still appear in Gmail/webmail
- Messages restored in cairn-mail remain in Trash on the provider
- Permanent deletes don't remove messages from provider servers
- Clear Trash operation leaves messages on server, wasting quota
- No offline support - changes don't propagate when reconnected

This violates user expectations that email operations are immediately reflected on the server. Users may believe they've deleted sensitive emails when they haven't, or that they've cleared space when quota remains consumed.

## What Changes

### Provider Interface Extensions

Add new methods to the `EmailProvider` protocol and `BaseEmailProvider` class:

```python
def move_to_trash(self, message_id: str) -> None:
    """Move a message to the provider's Trash/Deleted folder."""

def restore_from_trash(self, message_id: str) -> None:
    """Move a message from Trash back to its original folder."""

def delete_message(self, message_id: str, permanent: bool = False) -> None:
    """Delete a message (soft or permanent)."""
```

### Gmail Provider Implementation

- `move_to_trash()`: Add TRASH label, remove INBOX label
- `restore_from_trash()`: Remove TRASH label, add INBOX label (or restore original_folder)
- `delete_message()`: Use Gmail API's `trash()` for soft delete, `delete()` for permanent

### IMAP Provider Implementation

- `move_to_trash()`: COPY to Trash folder, mark original as \Deleted, EXPUNGE
- `restore_from_trash()`: COPY back to original folder (stored in db), delete from Trash
- `delete_message()`: Already implemented! Just needs integration

### API Route Updates

Update all trash-related endpoints to sync to provider after database update:

1. `DELETE /api/messages/{id}` - Call `provider.move_to_trash()`
2. `POST /api/messages/bulk/delete` - Call `provider.move_to_trash()` for each
3. `POST /api/messages/{id}/restore` - Call `provider.restore_from_trash()`
4. `POST /api/messages/bulk/restore` - Call `provider.restore_from_trash()` for each
5. `POST /api/messages/bulk/permanent-delete` - Call `provider.delete_message(permanent=True)`
6. `POST /api/messages/clear-trash` - Call `provider.delete_message(permanent=True)` for all

### Error Handling Strategy

**Two-phase commit approach:**
1. Update database first (current behavior)
2. Attempt provider sync
3. If provider sync fails:
   - Log error with message ID and operation
   - Return partial success response to user
   - Queue for retry on next sync (future enhancement)
   - Continue processing remaining messages in bulk operations

**Graceful degradation:**
- Operations succeed even if provider is offline
- UI shows warning when provider sync fails
- Next sync operation reconciles state differences

### Original Folder Tracking

To properly restore messages, we need to track their original folder:

- Database already has `original_folder` column on Message model
- When moving to trash, store current `folder` in `original_folder`
- When restoring, move back to `original_folder` (default to "inbox" if NULL)
- This enables Gmail "Undo" behavior - messages return to their original location

## Impact

### Affected Capabilities
- `email-trash-management` (NEW) - Trash lifecycle and provider sync
- `gmail-provider` (MODIFIED) - Add trash operation methods
- `imap-provider` (MODIFIED) - Add restore method, integrate existing delete

### Affected Code

**Modified:**
- `src/cairn_mail/providers/base.py` - Add methods to EmailProvider protocol
- `src/cairn_mail/providers/implementations/gmail.py` - Implement trash methods
- `src/cairn_mail/providers/implementations/imap.py` - Add restore_from_trash method
- `src/cairn_mail/api/routes/messages.py` - Integrate provider calls in all trash endpoints
- `src/cairn_mail/api/models.py` - Add error details to response models

**Existing behavior:**
- Database operations remain unchanged (local-first design)
- Sync engine continues to use existing provider methods
- Web UI requires no changes (server-side only)

## Breaking Changes

**None** - This is additive functionality that enhances existing operations.

The two-phase commit approach ensures operations succeed locally even if provider sync fails, maintaining current reliability while adding synchronization.

## User-Facing Changes

### Before
- Delete message → only removed from cairn-mail database
- Message still appears in Gmail/webmail inbox
- Restore → only updates local database
- Clear Trash → server quota unchanged
- Confusing inconsistency between UI and provider

### After
- Delete message → moved to Trash in both database AND provider
- Message appears in Trash folder in Gmail/webmail
- Restore → message returns to original folder on provider
- Clear Trash → server quota freed, messages gone everywhere
- Consistent state across all email clients
- Operations work offline and sync when reconnected

## Dependencies

Requires Phase 5 (Folders and Bulk Operations) to be complete:
- Database schema includes `folder` and `original_folder` columns
- Bulk operation endpoints exist
- IMAP folder discovery working
- Message ID format includes folder context

## Out of Scope (Future)

- Retry queue for failed provider syncs
- Optimistic UI updates with rollback
- Batch provider operations (currently one-by-one)
- Conflict resolution for simultaneous edits in multiple clients
- Move to arbitrary folders (Archive, Spam) - only Trash in Phase 6
