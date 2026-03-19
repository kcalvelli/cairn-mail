## ADDED Requirements

### Requirement: Update tags on a single message
The MCP server SHALL provide an `update_tags` tool that sets classification tags on a single message by ID. The tool SHALL accept a message_id and a list of tags, and SHALL record the edit as DFSL feedback.

#### Scenario: Set tags on a message
- **WHEN** the agent calls `update_tags(message_id="abc123", tags=["newsletter", "low-priority"])`
- **THEN** the message's classification tags are updated to `["newsletter", "low-priority"]` and the change is recorded as DFSL feedback

#### Scenario: Message not found
- **WHEN** the agent calls `update_tags` with a non-existent message_id
- **THEN** the tool returns an error dict with a descriptive message

### Requirement: Bulk update tags on multiple messages
The MCP server SHALL provide a `bulk_update_tags` tool that sets the same classification tags on multiple messages at once. A new `PUT /api/messages/bulk/tags` API endpoint SHALL support this operation.

#### Scenario: Tag multiple messages
- **WHEN** the agent calls `bulk_update_tags(message_ids=["id1", "id2", "id3"], tags=["newsletter"])`
- **THEN** all three messages have their tags set to `["newsletter"]` and each update is recorded as DFSL feedback

#### Scenario: Partial failure
- **WHEN** some message_ids are valid and some are not
- **THEN** the tool returns a result with `updated` count, `total` count, and an `errors` list describing failures

### Requirement: Delete messages by filter
The MCP server SHALL provide a `delete_by_filter` tool that deletes (moves to trash) all messages matching a combination of tag, folder, and account filters. At least one filter parameter MUST be provided.

#### Scenario: Delete all messages with a tag
- **WHEN** the agent calls `delete_by_filter(tag="spam")`
- **THEN** all messages tagged "spam" are moved to trash and the tool returns a count of moved messages

#### Scenario: Delete with multiple filters
- **WHEN** the agent calls `delete_by_filter(tag="newsletter", account="gmail")`
- **THEN** only messages matching both the tag and account are moved to trash

#### Scenario: No filters provided
- **WHEN** the agent calls `delete_by_filter()` with no filter parameters
- **THEN** the tool returns an error requiring at least one filter

### Requirement: Restore messages from trash
The MCP server SHALL provide a `restore_email` tool that restores messages from trash back to their original folder.

#### Scenario: Restore trashed messages
- **WHEN** the agent calls `restore_email(message_ids=["id1", "id2"])`
- **THEN** the messages are restored from trash and the tool returns a count of restored messages

#### Scenario: Message not in trash
- **WHEN** the agent calls `restore_email` with a message that is not in trash
- **THEN** the tool returns an error for that message in the errors list

### Requirement: Get unread message count
The MCP server SHALL provide a `get_unread_count` tool that returns the count of unread messages, optionally filtered by account.

#### Scenario: Get total unread count
- **WHEN** the agent calls `get_unread_count()`
- **THEN** the tool returns the total unread message count across all accounts

#### Scenario: Get unread count for specific account
- **WHEN** the agent calls `get_unread_count(account="gmail")`
- **THEN** the tool returns the unread count for that account only

### Requirement: List available tags
The MCP server SHALL provide a `list_tags` tool that returns all tags currently in use and/or configured as available for classification.

#### Scenario: List tags
- **WHEN** the agent calls `list_tags()`
- **THEN** the tool returns a list of tag objects with names and message counts
