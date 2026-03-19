## Context

The MCP server (`src/axios_ai_mail/mcp/`) exposes email operations to external AI agents via the Model Context Protocol. It currently has 8 tools covering basic CRUD. An external agent doing mail triage needs tagging, bulk operations, and query tools that the REST API mostly already supports but the MCP layer doesn't expose.

The architecture is: **MCP tool → AxiosMailClient method → REST API endpoint → DB**. Five of the six new tools only need the first two layers (client + tool). One (`bulk_update_tags`) also needs a new API endpoint.

## Goals / Non-Goals

**Goals:**
- Expose 6 new MCP tools: `update_tags`, `bulk_update_tags`, `delete_by_filter`, `restore_email`, `get_unread_count`, `list_tags`
- Add `PUT /api/messages/bulk/tags` endpoint for bulk tag updates
- Follow existing patterns in tools.py and client.py exactly

**Non-Goals:**
- Move/archive operations (deferred)
- Smart reply exposure (external agent is smarter)
- Frontend changes
- Database schema changes

## Decisions

### 1. Bulk tags endpoint design: single endpoint with message_ids + tags

The new `PUT /api/messages/bulk/tags` endpoint accepts `{"message_ids": [...], "tags": [...]}` and applies the same tag set to all listed messages. This matches the existing bulk patterns (`POST /api/messages/bulk/read`, `POST /api/messages/bulk/delete`).

**Alternative considered**: Per-message tag mapping (`{message_id: tags}`). Rejected because the primary use case is an agent classifying a batch of messages the same way (e.g., tagging 20 newsletters). The single-message `update_tags` tool handles individual cases.

### 2. delete_by_filter: require at least one filter parameter

The `delete_by_filter` tool wraps `POST /messages/delete-all` which accepts tag, folder, and account filters. We require at least one filter to be provided — calling it with no filters would delete everything, which is too dangerous for an agent tool.

### 3. Tag operations record DFSL feedback

Both `update_tags` and `bulk_update_tags` pass `user_edited=True` to the DB layer, so tag corrections from the external agent feed back into the DFSL (Dynamic Few-Shot Learning) system, just like manual tag edits in the GUI.

### 4. Use PUT for bulk tags endpoint

Following the existing `PUT /messages/{id}/tags` pattern. The bulk variant is `PUT /api/messages/bulk/tags`.

## Risks / Trade-offs

- **[Bulk tag updates are not atomic]** → Each message is updated individually in a loop, same as other bulk endpoints. A partial failure returns both success count and error list. Acceptable for the use case.
- **[No rate limiting on MCP tools]** → An aggressive agent could hammer the API. Mitigation: this is a local-only tool used by a single agent, not a public API.
