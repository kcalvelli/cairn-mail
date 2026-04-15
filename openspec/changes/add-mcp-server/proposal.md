# Change: Add MCP Server for AI Agent Email Automation

## Why

AI assistants (Claude, ChatGPT, etc.) increasingly need to interact with external tools via the Model Context Protocol (MCP). By exposing cairn-mail's email capabilities as MCP tools, users can automate email workflows through natural language commands like "Send an email from my dev account to joe@plumber.org saying I will miss my appointment."

This enables powerful automation scenarios without requiring users to learn APIs or write code.

## What Changes

- Add new `mcp` submodule to cairn-mail with MCP server implementation
- Create MCP tool definitions for core email operations
- Add CLI command `cairn-mail mcp` to start the MCP server
- Add NixOS module option to run MCP server as a service
- Bundle MCP server in existing package (no separate distribution)

### Core MCP Tools (Initial Scope)

| Tool | Description |
|------|-------------|
| `list_accounts` | List configured email accounts |
| `search_emails` | Search messages with filters (account, folder, unread, tags, text) |
| `read_email` | Get full email content by ID |
| `compose_email` | Create a draft email |
| `send_email` | Send a draft or compose+send in one step |
| `reply_to_email` | Create a reply draft for a thread |
| `mark_read` | Mark messages as read/unread |
| `delete_email` | Move messages to trash |

## Impact

- **Affected specs**: None (new capability)
- **Affected code**:
  - `src/cairn_mail/mcp/` (new module)
  - `src/cairn_mail/cli.py` (add mcp command)
  - `nix/module.nix` (add service option)
  - `pyproject.toml` (add mcp dependency)
- **Dependencies**: Adds `mcp` Python package
- **Breaking changes**: None
