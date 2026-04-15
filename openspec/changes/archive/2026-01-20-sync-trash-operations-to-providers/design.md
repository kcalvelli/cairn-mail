# Design: Sync Trash Operations to Providers

## Context

Phase 5 implemented folder-based organization and bulk operations in the UI and database, but these changes were not synchronized back to email providers. Users could delete messages in cairn-mail but they would still appear in Gmail's webmail, creating confusion and inconsistency.

**Problem:** How do we sync trash operations (delete, restore, permanent delete) back to providers without sacrificing the reliability of local-first database operations?

**Constraints:**
- Providers may be offline or rate-limited
- Database operations must succeed even if provider sync fails
- Different providers have different trash semantics (Gmail uses labels, IMAP uses folders)
- IMAP folder names vary by server (Trash, Deleted, INBOX.Trash, etc.)
- Gmail doesn't have true folders, only labels

**Stakeholders:**
- End users who expect consistency across email clients
- Developers maintaining provider implementations
- System reliability (can't fail operations due to provider issues)

## Goals / Non-Goals

### Goals
- Sync all trash operations to providers (delete, restore, permanent delete, clear trash)
- Maintain database-first reliability (operations succeed locally even if provider fails)
- Provide clear error reporting when provider sync fails
- Support both Gmail (label-based) and IMAP (folder-based) providers
- Handle original folder restoration correctly
- Log all provider operations for debugging and monitoring

### Non-Goals
- Retry queue for failed operations (future enhancement)
- Real-time bidirectional sync (handled by existing sync engine)
- Conflict resolution between multiple clients (future)
- Optimistic UI updates with rollback (frontend concern)
- Batch provider operations (one-by-one is acceptable for Phase 6)

## Decisions

### Decision 1: Two-Phase Commit with Graceful Degradation

**What:** Update database first, then sync to provider. If provider fails, log and continue.

**Why:**
- Maintains local-first reliability - user operations always succeed
- Allows offline usage - changes queue naturally during next sync
- Provider outages don't block user workflows
- Aligns with existing sync engine pattern (provider is eventually consistent)

**Alternatives Considered:**
1. **Provider-first approach** - Sync to provider, then update database
   - ❌ Rejected: Blocks users when provider is offline, reduces reliability
2. **Transactional sync** - Rollback database if provider fails
   - ❌ Rejected: Complicates error handling, may cause data loss if provider flaps
3. **Retry queue** - Queue failed operations for automatic retry
   - ⏳ Future enhancement: Good for reliability but adds complexity

**Implementation:**
```python
# In API route
db.move_to_trash(message_id)  # Phase 1: Always succeeds

try:
    provider.move_to_trash(message_id)  # Phase 2: Best effort
    provider_synced = True
except Exception as e:
    logger.error(f"Provider sync failed: {e}")
    provider_synced = False

return {"status": "moved_to_trash", "provider_synced": provider_synced}
```

### Decision 2: Provider Interface Extensions via Protocol

**What:** Add `move_to_trash()`, `restore_from_trash()`, and `delete_message()` to the EmailProvider protocol.

**Why:**
- Forces all providers to implement trash operations
- Type checking ensures consistency across Gmail and IMAP implementations
- Abstract interface hides provider-specific details (labels vs folders)
- Easy to add new providers (future: Outlook, Exchange, etc.)

**Alternatives Considered:**
1. **Optional methods with hasattr() checks**
   - ❌ Rejected: No type safety, easy to forget implementations
2. **Separate TrashProvider protocol**
   - ❌ Rejected: Unnecessarily splits provider interface, harder to use
3. **Implement only in base class**
   - ❌ Rejected: Can't handle provider-specific logic (Gmail labels vs IMAP folders)

**Implementation:**
```python
class EmailProvider(Protocol):
    def move_to_trash(self, message_id: str) -> None: ...
    def restore_from_trash(self, message_id: str) -> None: ...
    def delete_message(self, message_id: str, permanent: bool = False) -> None: ...
```

### Decision 3: Gmail Label-Based Trash Semantics

**What:** Use Gmail API's label system for trash operations (add/remove TRASH label).

**Why:**
- Gmail doesn't have true folders, only labels
- TRASH is a system label, consistent across all Gmail accounts
- Allows restore to original folder by restoring original labels
- Gmail API provides modify() method for atomic label changes
- Matches Gmail's native trash behavior

**Alternatives Considered:**
1. **Use Gmail API's trash() method**
   - ❌ Rejected: Doesn't allow specifying original folder for restore
2. **Custom trash label**
   - ❌ Rejected: Doesn't integrate with Gmail's native trash UI
3. **Permanent delete only**
   - ❌ Rejected: Loses undo capability, dangerous for users

**Gmail Folder Mapping:**
- inbox -> INBOX label
- sent -> SENT label
- trash -> TRASH label
- All labels are managed via Gmail API's modify() method

### Decision 4: IMAP Folder-Based Trash with Dynamic Discovery

**What:** Use IMAP COPY/DELETE/EXPUNGE commands to move messages between folders, with folder discovery.

**Why:**
- IMAP is folder-centric, not label-centric
- Trash folder names vary by server (Trash, Deleted Items, INBOX.Trash, etc.)
- Phase 5 already implements folder discovery with LIST command
- COPY maintains message state (flags, headers), DELETE + EXPUNGE removes cleanly
- Restoring requires knowing original folder (stored in database)

**Alternatives Considered:**
1. **Hardcode "Trash" folder name**
   - ❌ Rejected: Doesn't work for all IMAP servers
2. **Use IMAP MOVE extension**
   - ⏳ Future optimization: Not all servers support MOVE, COPY+DELETE is universal
3. **Store messages in custom folder**
   - ❌ Rejected: Doesn't integrate with server's native trash

**IMAP Trash Operation Flow:**
```
Move to Trash:
  1. SELECT source folder (e.g., INBOX)
  2. COPY message to Trash folder
  3. STORE +FLAGS \Deleted on original
  4. EXPUNGE to remove from source

Restore from Trash:
  1. SELECT Trash folder
  2. COPY message to original folder (from database)
  3. STORE +FLAGS \Deleted on trash copy
  4. EXPUNGE to remove from trash

Permanent Delete:
  1. SELECT folder containing message
  2. STORE +FLAGS \Deleted
  3. EXPUNGE
```

### Decision 5: Original Folder Tracking in Database

**What:** Store original folder in `Message.original_folder` column when moving to trash.

**Why:**
- Enables proper restoration to original location (inbox, sent, etc.)
- Gmail "Undo" behavior - messages return to where they came from
- Database already has this column from Phase 5 migration
- NULL value defaults to "inbox" for backward compatibility

**Alternatives Considered:**
1. **Always restore to inbox**
   - ❌ Rejected: Loses information, annoying for sent mail
2. **Store in provider metadata**
   - ❌ Rejected: Requires provider support, not universal
3. **Infer from message properties**
   - ❌ Rejected: Unreliable, sent vs received is not always clear

**Implementation:**
```python
# On delete
message.original_folder = message.folder  # Save current location
message.folder = "trash"

# On restore
message.folder = message.original_folder or "inbox"  # Default to inbox if NULL
message.original_folder = None  # Clear saved state
```

### Decision 6: Bulk Operations Process Each Message Individually

**What:** For bulk operations, iterate through message IDs and call provider methods one-by-one.

**Why:**
- Simpler implementation, easier to debug
- Providers don't expose batch APIs (Gmail API is single-message)
- Allows partial success - some messages can succeed even if others fail
- Provides granular error reporting per message
- Database bulk operations already iterate, matches that pattern

**Alternatives Considered:**
1. **Batch provider API calls**
   - ⏳ Future optimization: Would require provider-specific batch logic
2. **Parallel execution with threading**
   - ❌ Rejected: Adds complexity, rate limits would still apply
3. **Transaction-based all-or-nothing**
   - ❌ Rejected: One failure would block all operations

**Error Handling:**
- Track successes and failures separately
- Return counts: `moved_to_trash`, `provider_synced`, `provider_failed`
- Log each failure with message ID for troubleshooting
- Continue processing remaining messages after individual failures

## Risks / Trade-offs

### Risk: Provider Sync Failures Accumulate

**Description:** If provider is offline for extended periods, many messages may be out of sync.

**Mitigation:**
- Next sync operation reconciles state by fetching server state
- Clear logging allows users to understand sync status
- Future: Implement retry queue to automatically sync on reconnect

**Trade-off:** Accepting eventual consistency for higher reliability

### Risk: Rate Limiting on Bulk Operations

**Description:** Deleting 100 messages could hit Gmail API rate limits (10 requests/second).

**Mitigation:**
- Document expected rate limits in provider implementation
- Log rate limit errors distinctly from other failures
- Return partial success status so user knows how many succeeded
- Future: Implement rate limit backoff and retry

**Trade-off:** Speed vs reliability - we choose reliability

### Risk: IMAP Folder Name Ambiguity

**Description:** Servers may have multiple trash-like folders (Trash, Deleted, INBOX.Trash).

**Mitigation:**
- Use folder discovery from Phase 5 to map canonical names
- Prefer "Trash" > "Deleted" > first trash-like folder
- Log selected folder mapping on startup for debugging
- Allow manual override in Nix configuration (future)

**Trade-off:** Heuristics may be wrong for some servers, but covers 90% case

### Risk: Database and Provider State Divergence

**Description:** Failed provider syncs create temporary inconsistency.

**Mitigation:**
- Sync engine reconciles on next fetch by comparing server state
- Provider is source of truth for message existence and folder
- Database tags/classifications are source of truth for AI metadata
- UI shows provider sync status to set expectations

**Trade-off:** Temporary inconsistency is acceptable for offline support

## Migration Plan

### Phase 1: Add Provider Methods (No Breaking Changes)
1. Add new methods to EmailProvider protocol
2. Implement in Gmail provider
3. Implement in IMAP provider
4. Add unit tests for provider methods
5. No API route changes yet - database-only operations still work

### Phase 2: Integrate with API Routes
1. Update API routes to call provider methods after database updates
2. Add provider sync status to response models
3. Update error handling and logging
4. Deploy with feature flag (optional)

### Phase 3: Validation and Monitoring
1. Manual testing with both Gmail and IMAP accounts
2. Monitor logs for provider sync failures
3. Verify consistency by checking Gmail/webmail UI
4. Collect metrics on success/failure rates

### Rollback Plan
If provider sync causes issues:
1. Feature flag to disable provider sync (keep database-only mode)
2. No data loss - database operations are unchanged
3. Redeploy previous version if needed
4. Database schema unchanged, no migration needed

## Open Questions

1. **Should we queue failed operations for retry?**
   - Decision: Not in Phase 6, defer to future enhancement
   - Rationale: Adds complexity, sync engine reconciles anyway

2. **How do we handle messages moved to trash in other clients?**
   - Decision: Sync engine fetches server state and updates database
   - Rationale: Provider is source of truth for folder location

3. **Should clear trash operate on all accounts or per-account?**
   - Decision: All accounts (current behavior)
   - Rationale: Matches user expectation when viewing unified trash

4. **Do we need provider sync status in the UI?**
   - Decision: Return in API response, but don't display prominently
   - Rationale: Most operations succeed, showing errors creates noise
   - Future: Toast notification for sync failures

5. **How do we test provider methods without live accounts?**
   - Decision: Mock provider responses in unit tests, manual testing with real accounts
   - Rationale: Integration tests require real credentials, keep in manual test plan
