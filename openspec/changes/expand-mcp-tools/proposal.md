## Why

The MCP server currently exposes basic read/compose/delete operations, but external AI agents doing mail triage need richer tools — particularly the ability to tag messages, bulk-delete by filter, restore from trash, and query unread counts and available tags. Most of the backing API endpoints already exist; they just need MCP client methods and tool wrappers.

## What Changes

- Add `update_tags` MCP tool — set tags on a single message (API exists: `PUT /messages/{id}/tags`)
- Add `bulk_update_tags` MCP tool — set tags on multiple messages at once (needs new bulk API endpoint)
- Add `delete_by_filter` MCP tool — bulk delete messages matching tag/folder/account filters (API exists: `POST /messages/delete-all`)
- Add `restore_email` MCP tool — restore messages from trash (API exists: `POST /messages/bulk/restore`)
- Add `get_unread_count` MCP tool — quick unread count without fetching messages (API exists: `GET /messages/unread-count`)
- Add `list_tags` MCP tool — show available/active tags (API exists: `GET /tags`)
- Add corresponding `AxiosMailClient` methods for each new tool
- Add new `PUT /api/messages/bulk/tags` API endpoint for bulk tag updates

## Capabilities

### New Capabilities
- `mcp-tool-expansion`: New MCP tools for tagging, bulk deletion, restore, unread count, and tag listing — plus the bulk tags API endpoint they require

### Modified Capabilities

_(none — existing specs are unaffected; no requirement-level changes to contact-lookup, sync-engine, or documentation)_

## Impact

- **MCP layer** (`src/axios_ai_mail/mcp/tools.py`, `client.py`): 6 new tools + 6 new client methods
- **API layer** (`src/axios_ai_mail/api/routes/messages.py`): 1 new bulk tags endpoint
- **No database changes** — all operations use existing DB methods (`update_message_tags`, `move_to_trash`, `query_messages`, etc.)
- **No provider changes** — tags are local classification metadata, not synced upstream
- **No frontend changes** — these tools are MCP-only
