# Proposal: Add MCP Contacts Client Integration

> **SUPERSEDED** by [`add-action-tags`](../add-action-tags/proposal.md).
> The action tag framework provides user-initiated contact creation (and other PIM actions) via mcp-gateway REST API, covering the core use cases of this proposal with a simpler, more extensible architecture. This proposal will not be implemented.

## Summary

Add optional MCP client capability to cairn-mail, enabling integration with external contact providers (like cairn-dav's mcp-dav) for intelligent contact-aware email workflows.

## Problem

cairn-mail currently has no concept of contacts. This limits AI-powered email workflows:

- No recipient autocomplete or validation
- Cannot resolve "Email John about X" to actual email addresses
- Cannot intelligently suggest adding new contacts from incoming mail
- Cannot enrich contact data from email signatures

## Goals

1. Add optional MCP client that can connect to any MCP server providing contact tools
2. Enable Ollama to query contacts for recipient resolution and autocomplete
3. Enable Ollama to create/update contacts based on email activity
4. Zero hard dependencies - works standalone, enhanced with contacts
5. Provider agnostic - works with mcp-dav or any compatible MCP server

## Non-Goals

- Building our own contacts storage (use existing providers)
- Requiring contacts integration (must remain optional)
- Tight coupling to cairn-dav (just needs MCP protocol)

## Design

### Configuration

```nix
services.cairn-mail = {
  enable = true;

  integrations.contacts = {
    enable = mkEnableOption "MCP-based contacts integration";

    mcpCommand = mkOption {
      type = types.str;
      default = "mcp-dav";
      description = "Command to spawn MCP server providing contact tools";
      example = "/path/to/mcp-dav";
    };

    # Future: socket-based connection for long-running servers
    # mcpSocket = mkOption { ... };
  };
};
```

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      cairn-mail                               │
│                                                                  │
│  ┌────────────────┐    ┌─────────────────────────────────────┐  │
│  │  Email Tools   │    │          Ollama (AI)                 │  │
│  │  (MCP Server)  │    │                                      │  │
│  └────────────────┘    │  • Compose/reply intelligence        │  │
│                        │  • Contact-aware suggestions          │  │
│                        │  • "Add contact?" decisions           │  │
│                        └──────────────┬──────────────────────┘  │
│                                       │                          │
│                                       ▼                          │
│                        ┌─────────────────────────────────────┐  │
│                        │      MCPContactsClient              │  │
│                        │                                      │  │
│                        │  • search_contacts(query)            │  │
│                        │  • get_contact(uid/name)             │  │
│                        │  • create_contact(...)               │  │
│                        │  • update_contact(...)               │  │
│                        └──────────────┬──────────────────────┘  │
│                                       │ stdio                    │
│                                       ▼                          │
│                              ┌──────────────┐                    │
│                              │  mcp-dav     │                    │
│                              │  (spawned)   │                    │
│                              └──────────────┘                    │
└─────────────────────────────────────────────────────────────────┘
```

### MCP Client Implementation

```python
class MCPContactsClient:
    """MCP client for contact operations"""

    def __init__(self, command: str):
        self.command = command
        self.process = None
        self._initialized = False

    async def connect(self):
        """Spawn MCP server subprocess"""
        self.process = await asyncio.create_subprocess_exec(
            *shlex.split(self.command),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await self._initialize()

    async def call_tool(self, name: str, arguments: dict) -> dict:
        """Call an MCP tool and return result"""
        request = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments}
        }
        return await self._send_request(request)

    # Convenience methods
    async def search_contacts(self, query: str) -> list:
        result = await self.call_tool("search_contacts", {"query": query})
        return json.loads(result["content"][0]["text"])

    async def create_contact(self, **kwargs) -> dict:
        result = await self.call_tool("create_contact", kwargs)
        return json.loads(result["content"][0]["text"])
```

### Integration with Ollama

The Ollama AI gains new capabilities through function definitions:

```python
CONTACT_FUNCTIONS = [
    {
        "name": "lookup_contact",
        "description": "Find a contact by name or email to get their details",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Name or email to search"}
            }
        }
    },
    {
        "name": "add_contact",
        "description": "Add a new contact to the address book",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "email": {"type": "string"},
                "organization": {"type": "string"}
            }
        }
    }
]

# When Ollama calls these functions, we proxy to MCP
async def handle_ollama_function(name: str, args: dict):
    if name == "lookup_contact":
        return await contacts_client.search_contacts(args["query"])
    elif name == "add_contact":
        return await contacts_client.create_contact(
            formatted_name=args["name"],
            emails=[args["email"]],
            organization=args.get("organization"),
            addressbook="default"  # or configurable
        )
```

## Use Cases

### 1. Recipient Resolution
```
User: "Email John about the project update"

Ollama:
1. lookup_contact("John") → [{name: "John Smith", email: "john@company.com"}]
2. compose_email(to: "john@company.com", subject: "Project Update", ...)
```

### 2. Unknown Sender Detection
```
Incoming email from: jane@newstartup.com

Ollama:
1. lookup_contact("jane@newstartup.com") → []
2. Analyze email content (personal, professional context)
3. Extract info from signature: "Jane Doe, CTO at NewStartup"
4. Suggest: "Add Jane Doe to contacts?"
5. If approved: add_contact(name: "Jane Doe", email: "jane@newstartup.com", org: "NewStartup")
```

### 3. Contact Enrichment
```
Email signature contains new phone number for existing contact

Ollama:
1. lookup_contact("bob@corp.com") → [{uid: "abc-123", ...}]
2. update_contact(uid: "abc-123", phones: [...existing, {type: "WORK", number: "+1-555-NEW"}])
```

## Graceful Degradation

When contacts integration is disabled or unavailable:

```python
class EmailAssistant:
    async def resolve_recipient(self, query: str):
        if self.contacts_client:
            contacts = await self.contacts_client.search_contacts(query)
            if contacts:
                return contacts[0]["emails"][0]

        # Fallback: treat query as email if it looks like one
        if "@" in query:
            return query

        # Otherwise, ask user
        return None  # Prompt user for email address
```

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| MCP server not available | Features degraded | Graceful fallback, clear error messages |
| Slow MCP responses | Poor UX | Async operations, timeouts, caching |
| Wrong contact matched | Email sent to wrong person | Confirm before sending, show match details |
| Privacy concerns | Contact data exposure | Local only, user controls what's shared |

## Success Criteria

- [ ] MCP client successfully spawns and communicates with mcp-dav
- [ ] Ollama can resolve "Email X" queries to real email addresses
- [ ] Incoming mail triggers "add contact?" suggestions when appropriate
- [ ] Contact creation via MCP works and syncs via vdirsyncer
- [ ] Graceful degradation when contacts not configured
- [ ] Zero impact on users who don't enable contacts integration
