# Change: Async Provider Sync Queue

## Why

Current architecture has synchronous provider sync that causes issues:

1. **Slow API responses** - User waits for provider API call (Gmail/IMAP) to complete before getting a response. This can take 500ms-2s per operation.

2. **Silent failures** - If provider sync fails, the operation appears successful locally but provider is out of sync. User has no visibility into this.

3. **No retry logic** - Failed provider syncs are lost forever. If Gmail API is temporarily down, those changes never make it to the provider.

4. **Blocking operations** - Multiple quick actions (mark several as read) queue up synchronously, making the UI feel sluggish.

**Philosophy**: Local consistency first, provider sync is best effort.

## What Changes

### 1. Pending Operations Queue

Add a database table to queue operations that need to sync to provider:

```python
class PendingOperation(Base):
    __tablename__ = "pending_operations"

    id: Mapped[str] = mapped_column(primary_key=True)  # UUID
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id"))
    operation: Mapped[str]  # "mark_read", "mark_unread", "trash", "delete"
    created_at: Mapped[datetime]
    attempts: Mapped[int] = mapped_column(default=0)
    last_attempt: Mapped[Optional[datetime]]
    last_error: Mapped[Optional[str]]
    status: Mapped[str] = mapped_column(default="pending")  # pending, completed, failed
```

### 2. API Changes

Modify write endpoints to:
1. Update local database immediately
2. Queue operation for provider sync
3. Return immediately (fast!)

```python
@router.post("/messages/{message_id}/read")
async def mark_message_read(request: Request, message_id: str, body: MarkReadRequest):
    db = request.app.state.db

    # 1. Update local database immediately
    updated_message = db.update_message_read_status(message_id, body.is_unread)

    # 2. Queue for provider sync (non-blocking)
    operation = "mark_unread" if body.is_unread else "mark_read"
    db.queue_pending_operation(message.account_id, message_id, operation)

    # 3. Return immediately
    return serialize_message(updated_message, classification)
```

### 3. Sync Engine Changes

Process pending operations during sync:

```python
def sync(self, max_messages: int = 100) -> SyncResult:
    # ... existing fetch and classify logic ...

    # Process pending operations queue
    pending = self.db.get_pending_operations(self.account_id, limit=50)
    for op in pending:
        try:
            if op.operation == "mark_read":
                self.provider.mark_as_read(op.message_id)
            elif op.operation == "mark_unread":
                self.provider.mark_as_unread(op.message_id)
            elif op.operation == "trash":
                self.provider.move_to_trash(op.message_id)
            elif op.operation == "delete":
                self.provider.delete_message(op.message_id, permanent=True)

            self.db.complete_pending_operation(op.id)
        except Exception as e:
            self.db.fail_pending_operation(op.id, str(e))
```

### 4. Retry Logic

- Max 3 attempts per operation
- Exponential backoff between attempts
- After max attempts, mark as "failed" (don't retry forever)
- Failed operations visible in UI for manual intervention

### 5. Conflict Resolution

If provider state diverges from local:
- **Local wins** for user-initiated actions (read/unread, trash)
- **Provider wins** for metadata (subject, from, labels from provider)

### 6. Operations to Queue

| Operation | Currently | Proposed |
|-----------|-----------|----------|
| mark_read | Sync | Queue |
| mark_unread | Sync | Queue |
| move_to_trash | Sync | Queue |
| permanent_delete | Sync | Queue |
| send_message | Sync | **Keep Sync** (user needs immediate feedback) |
| update_labels (AI) | During sync | Keep as-is |

## Impact

- **Affected code:**
  - `src/cairn_mail/db/models.py` - Add PendingOperation model
  - `src/cairn_mail/db/database.py` - Add queue methods
  - `src/cairn_mail/sync_engine.py` - Process queue during sync
  - `src/cairn_mail/api/routes/messages.py` - Queue instead of sync
  - `web/src/api/types.ts` - Add pending operation types (optional)

- **New dependencies:** None

- **Database migration:** Required (new table)

## Benefits

1. **Faster UI** - API calls return immediately
2. **Resilient** - Failed syncs are retried
3. **Visibility** - Failed operations are tracked
4. **Consistent** - Local state is always correct
5. **Offline-ready** - Foundation for offline support

## Trade-offs

1. **Eventual consistency** - Provider may be slightly behind local state
2. **Complexity** - More moving parts
3. **Queue management** - Need to handle failed operations

## Future Enhancements

- Background sync worker (separate from user-triggered sync)
- Real-time sync via webhooks (Gmail push notifications)
- Offline queue with IndexedDB (PWA)
