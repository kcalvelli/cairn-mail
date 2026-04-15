# Contacts Integration Specification

## Overview

This spec defines the optional MCP-based contacts integration for cairn-mail, enabling contact-aware email workflows through any compatible MCP contacts provider.

---

## ADDED Requirements

### Requirement: MCP Client Connection

cairn-mail MUST be able to connect to an external MCP server providing contact tools.

#### Scenario: Successful connection to mcp-dav

**Given** contacts integration is enabled
**And** `mcpCommand` is set to "mcp-dav"
**And** mcp-dav is available in PATH
**When** cairn-mail starts
**Then** an MCP client connection is established
**And** the MCP initialize handshake completes successfully
**And** contact tools are available for use

#### Scenario: MCP server not found

**Given** contacts integration is enabled
**And** `mcpCommand` is set to "nonexistent-command"
**When** cairn-mail attempts to connect
**Then** an error is logged
**And** contacts features are disabled
**And** email features continue to work normally

#### Scenario: MCP server crashes mid-session

**Given** an active MCP client connection exists
**When** the MCP server process terminates unexpectedly
**Then** subsequent contact operations return graceful errors
**And** email features continue to work normally
**And** reconnection is attempted on next contact operation

---

### Requirement: Contact Search

cairn-mail MUST be able to search contacts via MCP when integration is enabled.

#### Scenario: Search contacts by name

**Given** contacts integration is enabled and connected
**When** the AI calls `lookup_contact` with query "John"
**Then** the MCP `search_contacts` tool is called with `{"query": "John"}`
**And** matching contacts are returned to the AI

#### Scenario: Search contacts by email

**Given** contacts integration is enabled and connected
**When** the AI calls `lookup_contact` with query "john@example.com"
**Then** the MCP `search_contacts` tool is called
**And** matching contacts (if any) are returned to the AI

#### Scenario: No contacts found

**Given** contacts integration is enabled and connected
**When** the AI searches for a non-existent contact
**Then** an empty result is returned
**And** the AI can handle this gracefully (ask user for email, etc.)

#### Scenario: Search when integration disabled

**Given** contacts integration is NOT enabled
**When** code attempts to search contacts
**Then** the operation returns empty results immediately
**And** no error is raised

---

### Requirement: Contact Creation

cairn-mail MUST be able to create contacts via MCP when integration is enabled.

#### Scenario: Create contact from email

**Given** contacts integration is enabled and connected
**And** a configured default addressbook "Personal"
**When** the AI calls `add_contact` with:
```json
{
  "name": "Jane Doe",
  "email": "jane@example.com",
  "organization": "Example Corp"
}
```
**Then** the MCP `create_contact` tool is called with:
```json
{
  "formatted_name": "Jane Doe",
  "emails": ["jane@example.com"],
  "organization": "Example Corp",
  "addressbook": "Personal"
}
```
**And** the created contact is returned to the AI
**And** the response includes sync reminder

#### Scenario: Create contact when integration disabled

**Given** contacts integration is NOT enabled
**When** code attempts to create a contact
**Then** the operation fails gracefully
**And** an appropriate message is returned

---

### Requirement: Recipient Resolution

cairn-mail MUST resolve natural language recipient references to email addresses when contacts integration is enabled.

#### Scenario: Resolve "Email John" to email address

**Given** contacts integration is enabled
**And** a contact "John Smith" exists with email "john@company.com"
**When** the user says "Email John about the meeting"
**Then** the AI searches contacts for "John"
**And** resolves recipient to "john@company.com"
**And** proceeds with email composition

#### Scenario: Multiple contacts match

**Given** contacts integration is enabled
**And** contacts "John Smith" and "John Doe" both exist
**When** the user says "Email John"
**Then** the AI presents both options to the user
**And** waits for user selection before proceeding

#### Scenario: No contact matches, input looks like email

**Given** contacts integration is enabled
**And** no contact matches "newperson@example.com"
**When** the user provides "newperson@example.com" as recipient
**Then** the email address is used directly
**And** no error is raised

---

### Requirement: Intelligent Contact Suggestions

cairn-mail MUST offer to suggest adding unknown senders as contacts when the AI determines it is appropriate.

#### Scenario: Personal email from unknown sender

**Given** contacts integration is enabled
**And** an incoming email from "jane@newcompany.com"
**And** no contact exists for this email
**And** the email content is personal/professional (not automated)
**When** the AI processes the incoming email
**Then** the AI MAY suggest adding the sender as a contact
**And** the suggestion includes extracted info (name, organization from signature)

#### Scenario: Newsletter from unknown sender

**Given** contacts integration is enabled
**And** an incoming email from "newsletter@marketing.com"
**And** the email is identified as automated/newsletter
**When** the AI processes the incoming email
**Then** the AI does NOT suggest adding as a contact

#### Scenario: User approves contact suggestion

**Given** the AI has suggested adding a contact
**When** the user approves the suggestion
**Then** the contact is created via MCP `create_contact`
**And** confirmation is shown to the user

---

## Configuration Schema

```nix
options.services.cairn-mail.integrations.contacts = {
  enable = mkEnableOption "MCP-based contacts integration";

  mcpCommand = mkOption {
    type = types.str;
    default = "mcp-dav";
    description = ''
      Command to spawn MCP server providing contact tools.
      The server must implement: search_contacts, get_contact,
      create_contact, update_contact, delete_contact.
    '';
    example = literalExpression ''
      "''${pkgs.mcp-dav}/bin/mcp-dav"
    '';
  };

  defaultAddressbook = mkOption {
    type = types.str;
    default = "default";
    description = "Default addressbook for new contacts";
  };

  autoSuggestContacts = mkOption {
    type = types.bool;
    default = true;
    description = "Automatically suggest adding unknown senders as contacts";
  };
};
```

---

## Cross-References

- **cairn-dav mcp-dav**: Primary contacts provider implementing required MCP tools
- **MCP Protocol**: JSON-RPC over stdio, protocol version 2024-11-05
- **Ollama Function Calling**: Integration point for AI-driven contact operations

---

## Implementation Notes

### MCP Tool Requirements

The configured MCP server MUST implement these tools:

| Tool | Purpose | Required |
|------|---------|----------|
| `search_contacts` | Find contacts by query | Yes |
| `get_contact` | Get single contact details | Yes |
| `create_contact` | Create new contact | Yes |
| `update_contact` | Modify existing contact | Optional |
| `delete_contact` | Remove contact | Optional |

### Error Handling

All MCP operations should fail gracefully:

```python
async def safe_search_contacts(query: str) -> list:
    try:
        if not contacts_client:
            return []
        return await contacts_client.search_contacts(query)
    except MCPConnectionError:
        log.warning("Contacts unavailable, continuing without")
        return []
    except MCPTimeoutError:
        log.warning("Contact search timed out")
        return []
```

### Ollama Function Definitions

```python
CONTACT_FUNCTIONS = [
    {
        "name": "lookup_contact",
        "description": "Search for a contact by name, email, or organization. Use this to find email addresses before composing emails.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Name, email, or organization to search for"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "add_contact",
        "description": "Add a new contact to the address book. Use when the user wants to save a new contact from an email.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Full name of the contact"
                },
                "email": {
                    "type": "string",
                    "description": "Email address"
                },
                "organization": {
                    "type": "string",
                    "description": "Company or organization (optional)"
                },
                "title": {
                    "type": "string",
                    "description": "Job title (optional)"
                }
            },
            "required": ["name", "email"]
        }
    }
]
```
