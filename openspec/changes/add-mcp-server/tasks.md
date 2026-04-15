# Tasks: Add MCP Server

## 1. Dependencies and Setup

- [x] 1.1 Add `mcp` package to `pyproject.toml` dependencies
- [x] 1.2 Update Nix flake to include MCP dependency
- [x] 1.3 Create `src/cairn_mail/mcp/` module directory with `__init__.py`

## 2. HTTP Client Wrapper

- [x] 2.1 Create `mcp/client.py` with `CairnMailClient` class
- [x] 2.2 Implement `list_accounts()` method (GET /api/accounts)
- [x] 2.3 Implement `search_messages()` method (GET /api/messages with filters)
- [x] 2.4 Implement `get_message()` method (GET /api/messages/{id})
- [x] 2.5 Implement `get_message_body()` method (GET /api/messages/{id}/body)
- [x] 2.6 Implement `create_draft()` method (POST /api/drafts)
- [x] 2.7 Implement `send_draft()` method (POST /api/send)
- [x] 2.8 Implement `mark_read()` method (POST /api/messages/bulk/read)
- [x] 2.9 Implement `delete_messages()` method (POST /api/messages/bulk/delete)
- [x] 2.10 Add connection error handling with user-friendly messages

## 3. MCP Server Core

- [x] 3.1 Create `mcp/server.py` with MCP server initialization
- [x] 3.2 Configure stdio transport via FastMCP
- [x] 3.3 Add server metadata (name, version)

## 4. MCP Tool Implementations

- [x] 4.1 Create `mcp/tools.py` with tool registration
- [x] 4.2 Implement `list_accounts` tool
- [x] 4.3 Implement `search_emails` tool with filter parameters
- [x] 4.4 Implement `read_email` tool
- [x] 4.5 Implement `compose_email` tool with account resolution
- [x] 4.6 Implement `send_email` tool (draft or inline compose)
- [x] 4.7 Implement `reply_to_email` tool
- [x] 4.8 Implement `mark_read` tool (single and bulk)
- [x] 4.9 Implement `delete_email` tool (trash and permanent)

## 5. Account Resolution

- [x] 5.1 Create `mcp/utils.py` with account resolution helper
- [x] 5.2 Implement exact match by ID
- [x] 5.3 Implement exact match by name
- [x] 5.4 Implement partial match detection with error message
- [x] 5.5 Handle single-account default selection

## 6. CLI Integration

- [x] 6.1 Add `mcp` subcommand to CLI in `cli/mcp.py`
- [x] 6.2 Add `--api-url` option with default `http://localhost:8080`
- [x] 6.3 Wire CLI to start MCP server
- [x] 6.4 Add `mcp info` subcommand to show available tools

## 7. Testing

- [ ] 7.1 Create `tests/test_mcp_client.py` with client unit tests
- [ ] 7.2 Create `tests/test_mcp_tools.py` with tool unit tests
- [ ] 7.3 Create `tests/test_mcp_account_resolution.py` for account lookup tests
- [ ] 7.4 Add integration test with mock API responses

## 8. Documentation

- [x] 8.1 Add MCP section to README with usage examples
- [x] 8.2 Document MCP server configuration for AI assistants (Claude Desktop)
- [x] 8.3 Add tool reference with parameter descriptions

## 9. Validation

- [ ] 9.1 Test MCP server startup via CLI
- [ ] 9.2 Test tool discovery from AI assistant
- [ ] 9.3 End-to-end test: "Send an email" workflow
