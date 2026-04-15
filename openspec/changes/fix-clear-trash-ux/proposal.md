# Change: Fix Clear Trash User Experience

## Why

The current clear trash functionality blocks the entire UI while permanently deleting messages. Based on journal log analysis, each message takes approximately 1 second to delete from the provider (IMAP/Gmail), meaning clearing 20+ messages can lock the user out of the application for 20+ seconds. Additionally, the UI provides no progress feedback and simply shows "Trash cleared successfully" regardless of whether provider sync succeeded or failed.

## What Changes

- **Async trash clearing**: Clear trash will use the existing `PendingOperation` queue instead of synchronous deletion
- **Immediate UI response**: Database deletion happens immediately, pending operations queue handles provider sync
- **Progress visibility**: Add a toast notification with count of messages queued for deletion
- **Error handling**: Provider sync failures are handled by the existing pending operations retry mechanism

## Impact

- Affected specs: `sync-engine` (extending pending operations to support `permanent_delete`)
- Affected code:
  - `src/cairn_mail/api/routes/messages.py` - `clear_trash` endpoint
  - `src/cairn_mail/sync_engine.py` - process `permanent_delete` pending operations
  - `web/src/components/MessageList.tsx` - update confirmation dialog feedback
  - `web/src/hooks/useMessages.ts` - update `useClearTrash` success handling
