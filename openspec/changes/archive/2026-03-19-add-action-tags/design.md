## Context

axios-ai-mail has a mature tagging system (35 default tags, custom tags, DFSL feedback) and a sync engine that runs every 5 minutes. The broader axios ecosystem includes mcp-gateway (aggregates MCP servers over REST) and mcp-dav (exposes CalDAV/CardDAV as MCP tools). axios-ai-chat already demonstrates the pattern of an agent calling MCP tools via the gateway to take real-world actions.

The action tag framework gives users a simple, familiar interface (tagging) that triggers powerful backend automation (MCP tool calls) without requiring them to interact with AI chat or learn new UIs.

## Goals / Non-Goals

- **Goals**:
  - Users can tag an email to trigger a real-world action (create contact, calendar event, etc.)
  - Actions are processed automatically on the next sync cycle (fire-and-forget)
  - Ollama extracts structured data from email content to populate tool call arguments
  - Any MCP tool available through mcp-gateway can be targeted
  - Built-in actions for common PIM workflows (contacts, calendar)
  - Clear visual feedback in the UI showing action status

- **Non-Goals**:
  - Building a full workflow engine (no multi-step chains, no conditionals)
  - Replacing axios-ai-chat as the primary AI agent interface
  - Direct MCP stdio client (we use mcp-gateway REST API instead)
  - AI-initiated actions (only users assign action tags; AI suggestions are a separate concern in `add-mcp-contacts-client`)
  - Real-time action execution (actions process on sync cycle, not instantly)

## Decisions

### Decision 1: Action tags use the existing tag infrastructure with an "action" category

Action tags are regular tags (stored in the `classifications.tags` JSON list) but belong to the `action` category. This means:
- No database schema changes required
- Existing tag UI components work with minimal modification
- The `merge_tags()` function handles action tags like any other custom tag
- Action tags get a distinctive color via `CATEGORY_COLORS["action"]`

**Alternatives considered**:
- Separate `actions` table: More structured but adds schema complexity and doesn't leverage existing tag infrastructure.
- Special prefix in tag name (e.g., `action:add-contact`): Works but complicates display and filtering. The category field already provides this semantic.

### Decision 2: mcp-gateway REST API as the integration point

The action agent calls `POST /api/tools/{server}/{tool}` on mcp-gateway rather than spawning MCP server subprocesses directly.

**Why**:
- mcp-gateway already manages MCP server lifecycle and handles stdio communication
- REST API is simpler to implement (just HTTP calls vs. JSON-RPC over stdio)
- Tool discovery via `GET /api/tools` is trivial
- Consistent with how axios-ai-chat connects to MCP tools
- No new process management or connection pooling needed
- Works across machines via Tailscale

**Alternatives considered**:
- Direct stdio MCP client (as in `add-mcp-contacts-client`): More coupling, subprocess lifecycle complexity, doesn't support remote servers.
- MCP Streamable HTTP transport: Would work but mcp-gateway's REST API is simpler and already proven.

### Decision 3: Ollama extracts structured data per-action

Each action definition includes an extraction prompt template. When processing an action tag, the action agent sends the email content + extraction prompt to Ollama and receives structured JSON that maps to MCP tool arguments.

**Why**:
- Reuses existing Ollama infrastructure (same endpoint, same model)
- Different actions need different data extracted (contact fields vs. event fields)
- LLM handles messy real-world email formatting (signatures, reply chains, etc.)
- Extraction prompts are customizable per-action

### Decision 4: Fire-and-forget with status feedback via tag mutation

When a user adds an action tag and saves, that's the confirmation. No preview, no approval dialog. On the next sync cycle, the action is processed and the tag is removed. A completion record is stored in a new `action_log` table for audit/status.

**Why**:
- Matches the existing async sync pattern (pending operations queue)
- Minimal UI changes (no new dialogs or workflows)
- Users who want to verify can check the action log or the target system (contacts, calendar)

**Tag lifecycle**:
```
User adds "add-contact" tag → saved to classifications
  ↓
Next sync: action agent finds message with action tag
  ↓
Ollama extracts data → mcp-gateway creates contact
  ↓
Success: "add-contact" tag removed, action_log entry created
Failure: "add-contact" tag kept, action_log entry with error
```

### Decision 5: Action registry with defaults + user customization

Built-in actions ship in `config/actions.py`. Users extend via Nix config:

```nix
programs.axios-ai-mail.actions = {
  "add-contact" = {
    description = "Create a contact from this email's sender";
    gateway.server = "dav";
    gateway.tool = "create_contact";
  };
  "create-reminder" = {
    description = "Create a calendar reminder from this email";
    gateway.server = "dav";
    gateway.tool = "create_event";
  };
  # Custom user action:
  "save-receipt" = {
    description = "Save receipt details to expense tracker";
    gateway.server = "expenses";
    gateway.tool = "add_expense";
  };
};
```

## Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                         axios-ai-mail                                  │
│                                                                        │
│  ┌─────────────┐   ┌──────────────────────────────────────────────┐  │
│  │  Web UI      │   │  Sync Engine (runs every 5 min)              │  │
│  │             │   │                                              │  │
│  │  User adds  │   │  1. Process pending operations               │  │
│  │  "add-      │   │  2. Fetch new messages                       │  │
│  │   contact"  │   │  3. Classify unclassified messages           │  │
│  │  tag        │   │  4. Push AI labels to provider               │  │
│  │             │   │  5. *** Process action tags (NEW) ***        │  │
│  └──────┬──────┘   └────────────────────┬─────────────────────────┘  │
│         │                               │                             │
│         │  PUT /api/messages/{id}/tags   │                             │
│         ▼                               ▼                             │
│  ┌─────────────┐              ┌──────────────────┐                   │
│  │  Database    │◄─────────── │  Action Agent     │                   │
│  │             │              │                  │                   │
│  │ messages    │              │  For each action │                   │
│  │ classifi-   │              │  tag found:      │                   │
│  │ cations     │              │                  │                   │
│  │ action_log  │              │  1. Read email   │                   │
│  └─────────────┘              │  2. Call Ollama  │                   │
│                               │  3. Call gateway │                   │
│                               │  4. Update tags  │                   │
│                               └────────┬─────────┘                   │
│                                        │                              │
│                               ┌────────▼─────────┐                   │
│                               │  Ollama (local)   │                   │
│                               │                  │                   │
│                               │  Extract:        │                   │
│                               │  - Contact info  │                   │
│                               │  - Event details │                   │
│                               │  - Custom fields │                   │
│                               └──────────────────┘                   │
│                                        │                              │
└────────────────────────────────────────┼──────────────────────────────┘
                                         │ HTTP
                                         ▼
                               ┌──────────────────┐
                               │  mcp-gateway      │
                               │                  │
                               │  POST /api/tools │
                               │  /{server}/{tool}│
                               └────────┬─────────┘
                                        │ stdio
                            ┌───────────┼───────────┐
                            ▼           ▼           ▼
                      ┌──────────┐ ┌────────┐ ┌──────────┐
                      │ mcp-dav  │ │ mail   │ │ custom   │
                      │          │ │        │ │ server   │
                      │ contacts │ │ email  │ │          │
                      │ calendar │ │ ops    │ │ ...      │
                      └──────────┘ └────────┘ └──────────┘
```

## Data Model

### New: `action_log` table

```python
class ActionLog(Base):
    __tablename__ = "action_log"

    id: Mapped[str]              # UUID
    message_id: Mapped[str]      # FK to messages
    account_id: Mapped[str]      # FK to accounts
    action_name: Mapped[str]     # e.g., "add-contact"
    server: Mapped[str]          # e.g., "dav"
    tool: Mapped[str]            # e.g., "create_contact"
    extracted_data: Mapped[dict] # JSON - what Ollama extracted
    tool_result: Mapped[dict]    # JSON - what the MCP tool returned
    status: Mapped[str]          # "success", "failed", "skipped"
    error: Mapped[str | None]    # Error message if failed
    processed_at: Mapped[datetime]
```

### Action Definition Schema

```python
@dataclass
class ActionDefinition:
    name: str                    # "add-contact"
    description: str             # Human-readable
    server: str                  # mcp-gateway server ID
    tool: str                    # MCP tool name
    extraction_prompt: str       # Prompt template for Ollama
    default_args: dict           # Static args (e.g., addressbook="Personal")
    enabled: bool = True
```

## Risks / Trade-offs

| Risk | Impact | Mitigation |
|------|--------|------------|
| mcp-gateway unavailable | Actions silently fail | Retry on next sync; action tags stay until successful. Action log records failures. |
| Ollama extracts wrong data | Wrong contact/event created | Action log stores extracted data for audit. Users can check target system. |
| User accidentally adds action tag | Unintended action executed | Action tags are visually distinct (category color). Could add undo window in future. |
| mcp-gateway URL changes | Actions break | Configurable via Nix; defaults to well-known Tailscale hostname. |
| Too many action tags queued | Slow sync cycle | Process max N actions per sync cycle (configurable, default 10). |

## Migration Plan

- No breaking changes; purely additive.
- Action tags are new tags in the "action" category; existing tags unaffected.
- New `action_log` table created via migration.
- mcp-gateway URL is optional config; action agent is a no-op if not configured.

## Open Questions

- Should there be a maximum retry count for failed actions before giving up? (Suggest: 3 attempts, then mark as `skipped` and keep the tag so user notices.)
- Should action results be surfaced in the web UI (e.g., a notification or action log viewer)? (Suggest: start with action log table, add UI later.)
- ~~Should the `add-mcp-contacts-client` proposal be updated to reference this framework?~~ **Resolved**: `add-mcp-contacts-client` is superseded by this proposal. Its core use case (contact creation from emails) is covered by the `add-contact` action tag.
