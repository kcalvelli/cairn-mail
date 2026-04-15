# Design: Contact Lookup for Email Composition

## Context

cairn-mail already has:
- `GatewayClient` for calling MCP tools via mcp-gateway REST API
- mcp-dav server exposing `search_contacts` tool via the gateway
- Action tags using this infrastructure to create contacts from emails

This proposal extends that infrastructure to support **reading** contacts for recipient autocomplete in the web UI compose form.

## Goals

- Web UI provides autocomplete when typing recipients in compose form
- Works with any MCP server providing contact search (not just mcp-dav)
- Graceful fallback when contacts unavailable

## Non-Goals

- Building our own contacts database (use mcp-gateway)
- Full contact management (create/update/delete) in the compose flow
- MCP tool for AI agents (they already have direct access to mcp-dav)

## Decisions

### 1. Backend API Design

**Decision**: Server-side proxy endpoint for contact search.

```
GET /api/contacts/search?q={query}
```

Returns:
```json
{
  "contacts": [
    {"name": "John Smith", "email": "john@example.com", "organization": "Acme Corp"}
  ]
}
```

**Rationale**:
- Keeps mcp-gateway internal (no CORS, no frontend exposure)
- Reuses existing GatewayClient infrastructure

### 2. Web UI Autocomplete

**Decision**: Debounced autocomplete with Material-UI Autocomplete component.

```
User types → debounce(300ms) → GET /api/contacts/search?q=... → GatewayClient → mcp-gateway → dav/search_contacts
```

**Alternatives considered**:
- Direct mcp-gateway calls from frontend: Would require CORS config, exposes gateway
- WebSocket for realtime: Overkill for simple search

### 3. Graceful Degradation

**Decision**: When mcp-gateway or dav server unavailable:
- API endpoint returns empty results, logs warning
- Web UI autocomplete silently fails (user can still type emails manually)
- No hard failures that block email composition

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| mcp-gateway unavailable | Return empty results, allow manual entry |
| Slow contact search | 2-second timeout, debounce UI requests |
| Wrong contact matched | Show full name + email in results so user can verify |

## Open Questions

None - straightforward extension of existing infrastructure.
