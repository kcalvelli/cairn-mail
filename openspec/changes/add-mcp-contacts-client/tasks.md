# Tasks: Add MCP Contacts Client Integration

## Phase 1: MCP Client Foundation

- [ ] **1.1** Create `MCPClient` base class
  - Spawn subprocess with command
  - JSON-RPC communication over stdio
  - Request/response handling with IDs
  - Connection lifecycle (connect, disconnect, reconnect)
  - Timeout handling

- [ ] **1.2** Create `MCPContactsClient` extending base
  - Initialize MCP protocol handshake
  - Implement `search_contacts(query)` convenience method
  - Implement `get_contact(uid/name)` convenience method
  - Implement `create_contact(...)` convenience method
  - Implement `update_contact(...)` convenience method
  - Parse MCP tool results to Python dicts

- [ ] **1.3** Add connection management
  - Lazy connection (connect on first use)
  - Connection health checks
  - Graceful shutdown on exit
  - Error handling for unavailable server

## Phase 2: NixOS/Home-Manager Module

- [ ] **2.1** Add module options
  - `integrations.contacts.enable` (default: false)
  - `integrations.contacts.mcpCommand` (default: "mcp-dav")
  - `integrations.contacts.addressbook` (default addressbook for new contacts)
  - `integrations.contacts.autoAdd` (auto-add contacts or prompt)

- [ ] **2.2** Wire configuration to Python server
  - Pass MCP command via environment variable or config file
  - Initialize MCPContactsClient when enabled
  - Handle missing/invalid configuration gracefully

## Phase 3: Ollama Integration

- [ ] **3.1** Define contact function schemas for Ollama
  - `lookup_contact` - search for contacts
  - `add_contact` - create new contact
  - `update_contact` - modify existing contact

- [ ] **3.2** Implement function handlers
  - Route Ollama function calls to MCPContactsClient
  - Transform results for Ollama consumption
  - Handle errors gracefully

- [ ] **3.3** Update system prompts
  - Inform AI about contact capabilities when enabled
  - Guide AI on when to suggest adding contacts
  - Include contact lookup in email composition workflow

## Phase 4: Email Workflow Integration

- [ ] **4.1** Recipient resolution
  - Before composing, resolve names to emails via contacts
  - Handle multiple matches (prompt user)
  - Handle no matches (ask for email or search again)

- [ ] **4.2** Incoming mail contact detection
  - Check if sender is known contact
  - Extract contact info from email signature
  - AI decides if contact should be suggested
  - Present suggestion to user

- [ ] **4.3** Contact enrichment
  - Detect new info in signatures (phone, title changes)
  - Suggest updates to existing contacts
  - Track what info came from which email

## Phase 5: Testing & Documentation

- [ ] **5.1** Unit tests
  - MCP client protocol handling
  - Function call routing
  - Graceful degradation

- [ ] **5.2** Integration tests
  - Test with actual mcp-dav server
  - Full workflow: search → compose → send
  - Full workflow: receive → detect → add contact

- [ ] **5.3** Documentation
  - Configuration guide for standalone users
  - Configuration guide for cairn users
  - Troubleshooting (MCP server not found, etc.)

## Dependencies

- Phase 2 depends on Phase 1
- Phase 3 depends on Phase 1
- Phase 4 depends on Phases 2 and 3
- Phase 5 depends on Phase 4

## Verification Checklist

- [ ] `nix flake check` passes
- [ ] MCP client connects to mcp-dav successfully
- [ ] Contact search works via Ollama function call
- [ ] Contact creation works via Ollama function call
- [ ] Graceful fallback when contacts not configured
- [ ] No regression for users without contacts integration
- [ ] Documentation complete for standalone users
