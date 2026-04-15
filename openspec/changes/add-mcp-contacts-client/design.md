# Design: MCP Contacts Client Integration

## Architectural Context

This design addresses integrating contact management into cairn-mail without creating dependencies on specific contact providers.

### System Landscape

```
┌─────────────────────────────────────────────────────────────────────┐
│                        User Environment                              │
│                                                                      │
│   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐          │
│   │ Claude Code │     │   cairn     │     │  Standalone │          │
│   │    User     │     │    User     │     │    User     │          │
│   └──────┬──────┘     └──────┬──────┘     └──────┬──────┘          │
│          │                   │                   │                  │
│          │ MCP               │                   │                  │
│          ▼                   ▼                   ▼                  │
│   ┌─────────────────────────────────────────────────────────┐      │
│   │                   cairn-mail                          │      │
│   │                                                          │      │
│   │  ┌──────────┐  ┌──────────┐  ┌───────────────────────┐  │      │
│   │  │  Email   │  │  Ollama  │  │  MCPContactsClient    │  │      │
│   │  │  Tools   │  │   (AI)   │  │  (optional)           │  │      │
│   │  └──────────┘  └────┬─────┘  └───────────┬───────────┘  │      │
│   │                     │                    │               │      │
│   │                     │    function calls  │ MCP          │      │
│   │                     └────────────────────┤               │      │
│   │                                          │               │      │
│   └──────────────────────────────────────────┼───────────────┘      │
│                                              │                      │
│                                              ▼                      │
│                                    ┌─────────────────┐              │
│                                    │    mcp-dav      │              │
│                                    │  (or any MCP    │              │
│                                    │   contacts      │              │
│                                    │   provider)     │              │
│                                    └─────────────────┘              │
└─────────────────────────────────────────────────────────────────────┘
```

## Design Decisions

### Decision 1: MCP as Integration Protocol

**Context:** We need cairn-mail to access contacts without depending on a specific provider.

**Options Considered:**
1. Direct filesystem access to VCF files
2. Import cairn-dav as flake input
3. MCP protocol for inter-process communication
4. REST API

**Decision:** Use MCP protocol

**Rationale:**
- MCP is already used by both projects for AI tool exposure
- Protocol is standardized and well-defined
- No flake dependency required
- Any MCP contacts provider works (not just cairn-dav)
- Aligns with modern AI integration patterns

### Decision 2: Subprocess-Based MCP Connection

**Context:** How should cairn-mail connect to the MCP contacts server?

**Options Considered:**
1. Subprocess (spawn on demand)
2. Unix socket (long-running server)
3. Network socket (remote server)
4. Embedded (in-process)

**Decision:** Subprocess with lazy initialization

**Rationale:**
- Simplest deployment (no separate service to manage)
- Matches how Claude Code connects to MCP servers
- Clean lifecycle (spawned when needed, terminated on exit)
- Future: can add socket support for advanced deployments

```python
class MCPContactsClient:
    def __init__(self, command: str):
        self.command = command
        self.process = None  # Lazy init

    async def ensure_connected(self):
        if self.process is None or self.process.returncode is not None:
            await self._spawn_and_initialize()
```

### Decision 3: Ollama Function Bridge

**Context:** How should Ollama's AI capabilities access contacts?

**Options Considered:**
1. Direct MCP client calls from AI prompts
2. Function calling (tool use) bridge
3. RAG with contact embeddings
4. System prompt with contact dump

**Decision:** Function calling bridge

**Rationale:**
- Ollama supports function/tool calling
- AI decides when to look up contacts (intelligent)
- Clean separation: AI logic vs. data access
- Matches how Claude Code MCP tools work

```python
# Ollama sees these functions
functions = [
    {"name": "lookup_contact", ...},
    {"name": "add_contact", ...}
]

# When Ollama calls a function, we proxy to MCP
def handle_function_call(name, args):
    if name == "lookup_contact":
        return mcp_client.search_contacts(args["query"])
```

### Decision 4: Graceful Degradation

**Context:** What happens when contacts aren't available?

**Decision:** All contact operations fail silently with sensible defaults

**Rationale:**
- Users without contacts integration shouldn't see errors
- Email functionality must never break due to contacts
- AI can adapt (ask for email directly if lookup fails)

```python
async def resolve_recipient(self, name_or_email: str) -> str:
    # Try contact lookup
    if self.contacts_client:
        try:
            contacts = await self.contacts_client.search_contacts(name_or_email)
            if contacts:
                return contacts[0]["emails"][0]
        except Exception:
            pass  # Fall through to direct use

    # Fallback: use as-is if it looks like email
    if "@" in name_or_email:
        return name_or_email

    # Last resort: need user input
    return None
```

### Decision 5: Configuration Over Convention

**Context:** How do users configure the contacts integration?

**Decision:** Explicit NixOS module options

**Rationale:**
- Clear opt-in (not enabled by default)
- Flexible command specification
- Works for standalone and cairn users
- Self-documenting through module options

```nix
services.cairn-mail.integrations.contacts = {
  enable = true;  # Explicit opt-in
  mcpCommand = "mcp-dav";  # Configurable
  defaultAddressbook = "Personal";  # Where to create contacts
};
```

## Component Design

### MCPClient (Base)

```python
class MCPClient:
    """Generic MCP client for subprocess communication"""

    async def connect(self) -> None
    async def disconnect(self) -> None
    async def call_tool(self, name: str, arguments: dict) -> dict
    async def list_tools(self) -> list

    # Internal
    async def _send_request(self, request: dict) -> dict
    async def _read_response(self) -> dict
```

### MCPContactsClient

```python
class MCPContactsClient(MCPClient):
    """Specialized client for contact operations"""

    # High-level contact operations
    async def search_contacts(self, query: str) -> list[dict]
    async def get_contact(self, uid: str = None, name: str = None) -> dict
    async def create_contact(self, **fields) -> dict
    async def update_contact(self, uid: str, **fields) -> dict

    # Checks
    def has_tool(self, name: str) -> bool
```

### OllamaFunctionBridge

```python
class OllamaFunctionBridge:
    """Routes Ollama function calls to appropriate handlers"""

    def __init__(self, contacts_client: MCPContactsClient = None):
        self.contacts = contacts_client

    def get_functions(self) -> list[dict]:
        """Return function definitions for Ollama"""
        functions = [...]
        if self.contacts:
            functions.extend(CONTACT_FUNCTIONS)
        return functions

    async def handle_call(self, name: str, args: dict) -> Any:
        """Execute function and return result"""
        if name == "lookup_contact":
            return await self.contacts.search_contacts(args["query"])
        # ... etc
```

## Data Flow

### Email Composition with Contact Resolution

```
User: "Email John about tomorrow's meeting"
                │
                ▼
┌─────────────────────────────────────────┐
│              Ollama                      │
│                                          │
│  1. Parse intent: compose email          │
│  2. Recipient "John" needs resolution    │
│  3. Call function: lookup_contact        │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│         OllamaFunctionBridge             │
│                                          │
│  Route to: contacts_client.search        │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│          MCPContactsClient               │
│                                          │
│  MCP call: tools/call                    │
│  Tool: search_contacts                   │
│  Args: {"query": "John"}                 │
└────────────────┬────────────────────────┘
                 │ stdio
                 ▼
┌─────────────────────────────────────────┐
│              mcp-dav                     │
│                                          │
│  Search contacts → [{                    │
│    "formatted_name": "John Smith",       │
│    "emails": ["john@company.com"]        │
│  }]                                      │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│              Ollama                      │
│                                          │
│  4. Resolved: john@company.com           │
│  5. Compose email with resolved address  │
│  6. Return draft to user                 │
└─────────────────────────────────────────┘
```

## Security Considerations

1. **No credential sharing**: MCP servers handle their own auth
2. **Local only**: No network exposure by default
3. **User consent**: Contact creation requires user approval
4. **Subprocess isolation**: MCP server runs in separate process

## Future Considerations

1. **Socket connection**: For long-running MCP servers
2. **Multiple providers**: Connect to multiple contact sources
3. **Caching**: Cache frequent contact lookups
4. **Calendar integration**: Same pattern for calendar access
