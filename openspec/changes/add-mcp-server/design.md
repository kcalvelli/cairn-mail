# Design: MCP Server for Email Automation

## Context

cairn-mail has a comprehensive REST API with 60+ endpoints. AI assistants using MCP (Model Context Protocol) need a standardized way to invoke these capabilities. MCP provides a JSON-RPC based protocol for tool discovery and invocation.

**Constraints:**
- Must work with local-only deployment (no cloud auth)
- Should reuse existing API logic, not duplicate it
- Must be bundled in the existing package
- CLI-first invocation (stdio transport for MCP)

## Goals / Non-Goals

**Goals:**
- Expose core email operations as MCP tools
- Enable natural language email automation
- Zero configuration for local use
- Integrate with NixOS module system

**Non-Goals:**
- Remote/authenticated MCP access (future consideration)
- Real-time streaming/WebSocket via MCP
- Exposing all 60+ endpoints (start minimal)

## Architecture

### Transport Mode

MCP supports multiple transports. We'll use **stdio** (standard input/output) as the primary transport:

```
┌─────────────────┐      stdio       ┌──────────────────┐
│   AI Assistant  │◄───────────────►│  MCP Server      │
│   (Claude, etc) │   JSON-RPC      │  (subprocess)    │
└─────────────────┘                  └────────┬─────────┘
                                              │
                                              │ HTTP localhost
                                              ▼
                                     ┌──────────────────┐
                                     │  cairn-mail   │
                                     │  Web API         │
                                     │  (FastAPI)       │
                                     └──────────────────┘
```

The MCP server runs as a subprocess of the AI assistant, communicating via stdio. It then calls the existing cairn-mail REST API over localhost.

### Alternative Considered: Direct Database Access

**Option:** MCP server directly accesses SQLite/business logic without going through HTTP.

**Rejected because:**
- Duplicates business logic already in API routes
- Creates two codepaths to maintain
- Loses benefits of existing error handling, validation
- HTTP overhead is negligible for local requests

### Module Structure

```
src/cairn_mail/
├── mcp/
│   ├── __init__.py
│   ├── server.py       # MCP server implementation
│   ├── tools.py        # Tool definitions and handlers
│   └── client.py       # HTTP client for API calls
```

## Decisions

### Decision 1: HTTP Client Wrapper

Create a thin HTTP client that calls the localhost API:

```python
class CairnMailClient:
    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url

    async def list_accounts(self) -> list[Account]:
        # GET /api/accounts
        ...

    async def search_messages(self, **filters) -> list[Message]:
        # GET /api/messages with query params
        ...
```

**Rationale:** Decouples MCP logic from API implementation. If API changes, only client wrapper needs updates.

### Decision 2: Tool Granularity

Provide **action-oriented** tools rather than raw CRUD operations:

| Instead of | Provide |
|------------|---------|
| `POST /drafts` + `POST /send` | `send_email(to, subject, body, account?)` |
| `GET /accounts` + `GET /messages` | `search_emails(query, account_name?)` |

**Rationale:** AI agents work better with higher-level actions. The MCP server handles the multi-step orchestration internally.

### Decision 3: Account Resolution

Accept both account ID and human-readable account name:

```python
@tool
async def send_email(
    to: str,
    subject: str,
    body: str,
    account: str = None,  # "dev" or "abc123-uuid"
):
    # Resolve "dev" → account_id via GET /accounts
    ...
```

**Rationale:** Users say "from my dev account" not "from account abc123-def456". The MCP server handles the lookup.

### Decision 4: MCP SDK

Use the official `mcp` Python package:

```toml
# pyproject.toml
dependencies = [
    ...
    "mcp>=1.0.0",
]
```

**Rationale:** Official SDK handles JSON-RPC transport, tool registration, and protocol compliance.

## Tool Definitions

### list_accounts

```python
@server.tool()
async def list_accounts() -> list[dict]:
    """List all configured email accounts.

    Returns account names, emails, and providers.
    Use the account name or ID in other tools.
    """
```

### search_emails

```python
@server.tool()
async def search_emails(
    query: str = None,
    account: str = None,
    folder: str = "inbox",
    unread_only: bool = False,
    tag: str = None,
    limit: int = 20,
) -> list[dict]:
    """Search for emails with optional filters.

    Args:
        query: Text to search in subject/body/sender
        account: Account name or ID (optional, searches all if omitted)
        folder: Folder to search (inbox, sent, trash)
        unread_only: Only return unread messages
        tag: Filter by classification tag
        limit: Maximum results (default 20)
    """
```

### read_email

```python
@server.tool()
async def read_email(message_id: str) -> dict:
    """Get the full content of an email by ID.

    Returns subject, sender, recipients, date, body (text and HTML),
    and attachment info.
    """
```

### compose_email

```python
@server.tool()
async def compose_email(
    to: str | list[str],
    subject: str,
    body: str,
    account: str = None,
    cc: str | list[str] = None,
    bcc: str | list[str] = None,
) -> dict:
    """Create a draft email (does not send).

    Returns the draft ID for later sending or editing.
    """
```

### send_email

```python
@server.tool()
async def send_email(
    draft_id: str = None,
    # OR compose inline:
    to: str | list[str] = None,
    subject: str = None,
    body: str = None,
    account: str = None,
) -> dict:
    """Send an email.

    Either provide a draft_id to send an existing draft,
    or provide to/subject/body to compose and send in one step.
    """
```

### reply_to_email

```python
@server.tool()
async def reply_to_email(
    message_id: str,
    body: str,
    reply_all: bool = False,
) -> dict:
    """Create a reply draft for an email.

    Returns the draft ID. Use send_email to actually send it.
    """
```

### mark_read

```python
@server.tool()
async def mark_read(
    message_ids: str | list[str],
    unread: bool = False,
) -> dict:
    """Mark messages as read or unread.

    Args:
        message_ids: Single ID or list of IDs
        unread: If True, mark as unread instead of read
    """
```

### delete_email

```python
@server.tool()
async def delete_email(
    message_ids: str | list[str],
    permanent: bool = False,
) -> dict:
    """Delete emails (move to trash).

    Args:
        message_ids: Single ID or list of IDs
        permanent: If True, permanently delete (skip trash)
    """
```

## CLI Integration

```bash
# Start MCP server (stdio mode for AI assistants)
cairn-mail mcp

# With custom API URL
cairn-mail mcp --api-url http://localhost:9000
```

## NixOS Integration

```nix
services.cairn-mail = {
  enable = true;

  # Optional: Enable MCP server as systemd socket-activated service
  mcp.enable = true;  # Future consideration for remote access
};
```

For local use, no service is needed—AI assistants spawn the MCP server as a subprocess.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| API must be running for MCP to work | Document prerequisite; MCP server returns clear error if API unreachable |
| Account name collisions | Return error with suggestions if ambiguous |
| Large email bodies in responses | Truncate body in search results; full body only in read_email |

## Migration Plan

No migration needed—this is purely additive.

## Open Questions

1. **Should we support SSE transport for real-time notifications?** Deferred to future iteration.
2. **Should compose_email auto-send or always create draft?** Current design: always draft, explicit send.
