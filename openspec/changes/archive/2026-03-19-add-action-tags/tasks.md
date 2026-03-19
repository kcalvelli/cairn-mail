## 1. Core Infrastructure

- [x] 1.1 Create `gateway_client.py` - HTTP client for mcp-gateway REST API
  - `GatewayClient` class with async httpx
  - `discover_tools()` → `GET /api/tools` (returns available servers and tools)
  - `call_tool(server, tool, arguments)` → `POST /api/tools/{server}/{tool}`
  - Configurable base URL, timeout, retry logic
  - Graceful error handling (connection refused, timeout, 4xx/5xx)

- [x] 1.2 Create `config/actions.py` - Action registry with built-in defaults
  - `ActionDefinition` dataclass (name, description, server, tool, extraction_prompt, default_args)
  - `DEFAULT_ACTIONS` dict with `add-contact` and `create-reminder`
  - `merge_actions()` function combining defaults with user-defined actions
  - Extraction prompt templates for each built-in action

- [x] 1.3 Create `action_agent.py` - Core action processing engine
  - `ActionAgent` class with `__init__(db, gateway_client, ai_classifier, config)`
  - `discover_available_actions()` - cross-reference registry with gateway tools
  - `process_actions(account_id, max_actions)` - main processing loop
  - `_extract_data(message, action_def)` - call Ollama with extraction prompt
  - `_execute_action(action_def, extracted_data)` - call mcp-gateway tool
  - `_update_status(message_id, action_name, result)` - update tags and action_log

- [x] 1.4 Add `ActionLog` model to `db/models.py`
  - Fields: id, message_id, account_id, action_name, server, tool, extracted_data, tool_result, status, error, processed_at
  - Foreign keys to messages and accounts
  - Index on (account_id, processed_at) for cleanup queries

- [x] 1.5 Add database methods for action log
  - `store_action_log(...)` - record action result
  - `get_action_log(message_id)` - get action history for a message
  - `cleanup_action_log(max_age_days)` - clean old entries
  - `get_pending_action_messages(account_id)` - find messages with action tags

## 2. Integration with Sync Engine

- [x] 2.1 Add action processing step to `sync_engine.py`
  - Initialize `ActionAgent` with gateway client and config
  - Add step after classification: `self._process_action_tags()`
  - Respect `max_actions_per_sync` config (default: 10)
  - Log action processing results in sync summary

- [x] 2.2 Update classifier integration to exclude action tags
  - Action category tags excluded from `get_tags_for_prompt()` output
  - Action tags preserved during reclassification via `preserve_tags` parameter
  - Action tags not in classifier's valid tag list

## 3. Tag System Updates

- [x] 3.1 Add action category to `config/tags.py`
  - Add `"action"` to `CATEGORY_COLORS` (amber)
  - `action_tags_from_definitions()` generates tags from action config
  - Action tags excluded from classifier prompts

- [x] 3.2 Update available tags to include action tags
  - `stats.py` available tags endpoint includes action tags from definitions
  - Action tags get category "action" for frontend grouping

## 4. Configuration

- [x] 4.1 Update `modules/home-manager/default.nix`
  - Add `programs.axios-ai-mail.actions` option set
  - Each action: `{ description, server, tool, extractionPrompt?, defaultArgs?, enabled? }`
  - Add `programs.axios-ai-mail.gateway.url` option (default: `"http://localhost:8085"`)
  - Generate action and gateway config into `config.yaml`

- [x] 4.2 Update `config/loader.py` to load action and gateway config
  - `get_gateway_config()` - parse gateway section
  - `get_actions_config()` - parse actions section and merge with defaults
  - Create `ActionDefinition` instances from config

## 5. Web UI

- [x] 5.1 Style action tags distinctively in the frontend
  - Action category tags get amber color, dashed border, bolt icon
  - `TagChip` component updated with `isActionTag` prop
  - `useActionTagNames()` hook for determining action tag status
  - Applied to MessageCard, MessageDetail, MessageDetailPage, and Sidebar

- [x] 5.2 Add action tag assignment UX
  - Action tags available in tag editor Autocomplete
  - Action tags grouped separately ("Actions" section) in tag picker via `groupBy`
  - Sorted so action tags appear after regular tags

- [x] 5.3 Add action completion toast notifications (replaces log viewer)
  - WebSocket `action_completed` event with action_name, status, message_subject
  - Frontend shows success/error toasts ("Contact Added", "Event Created", etc.)
  - Human-readable labels mapped from action names in useWebSocket.ts

## 6. API

- [x] 6.1 Add action log API endpoints
  - `GET /api/actions/log` - list recent action results (with pagination)
  - `GET /api/actions/available` - list configured action tags and their tool mappings
  - `POST /api/actions/retry/{log_id}` - retry a failed action

## 7. Database Migration

- [x] 7.1 Database migration for `action_log` table
  - No explicit migration needed - `Base.metadata.create_all()` auto-creates new tables
  - Table created automatically on first startup

## 8. Testing

- [~] 8.1–8.4 Unit and integration tests — deferred (manually verified end-to-end)
