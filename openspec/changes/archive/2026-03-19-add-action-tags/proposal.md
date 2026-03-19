# Change: Add Extensible Action Tag Framework

## Why

Users want emails to drive real-world actions beyond classification. Today, tags are passive labels for organization. Users should be able to tag an email "add contact" or "create reminder" and have the system actually perform that action using MCP tools already available through mcp-gateway. This bridges the gap between email triage and personal information management (contacts, calendar) without leaving the inbox.

## What Changes

- **New "action" tag category**: Tags in the `action` category are user-assignable markers that trigger tool calls. The AI classifier never assigns them; only users do.
- **Action agent**: A new processing step in the sync cycle that scans for messages with action tags, uses Ollama to extract structured data from the email, and calls the corresponding MCP tool via mcp-gateway's REST API.
- **mcp-gateway REST client**: A lightweight HTTP client that calls `POST /api/tools/{server}/{tool}` on the gateway to execute actions.
- **Action tag lifecycle**: Tags transition from `add-contact` (pending) to a status indicator after processing. Successfully processed action tags are removed and a completion record is stored.
- **Built-in actions**: `add-contact` (calls `dav/create_contact`) and `create-reminder` (calls `dav/create_event`) ship out of the box.
- **Extensible action registry**: Users define custom action-to-tool mappings via Nix configuration. Any MCP tool exposed through mcp-gateway can be targeted.
- **Tool discovery**: On startup, the action agent queries mcp-gateway's tool list and only activates actions whose required tools are available.

## Impact

- Affected specs: New `action-tags` capability (no existing specs modified)
- Affected code:
  - New: `action_agent.py`, `gateway_client.py`
  - Modified: `config/tags.py`, `sync_engine.py`, `ai_classifier.py`
  - Modified: `modules/home-manager/default.nix` (action config), `modules/nixos/default.nix` (gateway URL)
  - Modified: Web UI components (action tag styling, status indicators)
- **Supersedes**: `add-mcp-contacts-client` — that proposal's core use case (creating contacts from emails) is handled here via the `add-contact` action tag through mcp-gateway REST API, without the complexity of a direct MCP stdio client or AI-initiated suggestion flows.
