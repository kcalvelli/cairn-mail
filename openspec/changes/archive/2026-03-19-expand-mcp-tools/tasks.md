## 1. API Layer — Bulk Tags Endpoint

- [x] 1.1 Add `PUT /api/messages/bulk/tags` endpoint to `src/cairn_mail/api/routes/messages.py` accepting `{"message_ids": [...], "tags": [...]}`, iterating over messages and calling `db.update_message_tags` with `user_edited=True`

## 2. MCP Client Methods

- [x] 2.1 Add `update_tags(message_id, tags)` method to `CairnMailClient` calling `PUT /api/messages/{id}/tags`
- [x] 2.2 Add `bulk_update_tags(message_ids, tags)` method calling `PUT /api/messages/bulk/tags`
- [x] 2.3 Add `delete_by_filter(tag, folder, account_id)` method calling `POST /api/messages/delete-all`
- [x] 2.4 Add `restore_messages(message_ids)` method calling `POST /api/messages/bulk/restore`
- [x] 2.5 Add `get_unread_count(account_id)` method calling `GET /api/messages/unread-count`
- [x] 2.6 Add `list_tags(account_id)` method calling `GET /api/tags`

## 3. MCP Tool Wrappers

- [x] 3.1 Add `update_tags` tool to `register_tools` in `tools.py`
- [x] 3.2 Add `bulk_update_tags` tool to `register_tools`
- [x] 3.3 Add `delete_by_filter` tool with at-least-one-filter validation
- [x] 3.4 Add `restore_email` tool wrapping `restore_messages`
- [x] 3.5 Add `get_unread_count` tool with optional account parameter
- [x] 3.6 Add `list_tags` tool
