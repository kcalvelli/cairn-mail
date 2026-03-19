# Action Tags Specification

## Overview

Action tags are a special category of user-assignable tags that trigger real-world actions via MCP tools exposed through mcp-gateway. When a user adds an action tag to an email, the action agent extracts relevant data using Ollama and calls the corresponding MCP tool on the next sync cycle.

---

## ADDED Requirements

### Requirement: Action Tag Category

The tag system SHALL support an "action" category whose tags trigger automated tool calls rather than serving as passive labels.

#### Scenario: Action tags are visually distinct
- **GIVEN** the tag taxonomy includes tags with category "action"
- **WHEN** action tags are displayed in the web UI
- **THEN** they are styled distinctly from classification tags (unique color, icon, or border)
- **AND** they are grouped in a separate "Actions" section in the tag picker

#### Scenario: AI classifier excludes action tags
- **GIVEN** the AI classifier is building a classification for a message
- **WHEN** it selects tags from the available taxonomy
- **THEN** tags with category "action" are excluded from the candidate set
- **AND** only users can assign action tags manually

#### Scenario: Action tags preserved during reclassification
- **GIVEN** a message has both classification tags and an action tag
- **WHEN** the message is reclassified (manually or via reclassify command)
- **THEN** action tags are preserved and not removed by the classifier

---

### Requirement: Action Registry

The system SHALL maintain a registry of action definitions that map action tag names to MCP tool calls.

#### Scenario: Built-in actions available by default
- **GIVEN** no custom action configuration is provided
- **WHEN** the action registry is loaded
- **THEN** the built-in actions "add-contact" and "create-reminder" are available
- **AND** each has a configured server, tool, and extraction prompt

#### Scenario: Custom action defined via Nix config
- **GIVEN** a user defines a custom action in their Nix configuration:
  ```nix
  programs.axios-ai-mail.actions."save-receipt" = {
    description = "Save receipt to expense tracker";
    gateway.server = "expenses";
    gateway.tool = "add_expense";
  };
  ```
- **WHEN** the action registry is loaded
- **THEN** "save-receipt" appears as an available action tag
- **AND** it is mapped to the `expenses/add_expense` MCP tool

#### Scenario: Custom action overrides built-in
- **GIVEN** a user defines an action with the same name as a built-in
- **WHEN** the action registry is loaded
- **THEN** the user's definition takes precedence
- **AND** the built-in extraction prompt and defaults are replaced

---

### Requirement: mcp-gateway Client

The system SHALL communicate with mcp-gateway via its REST API to discover and execute MCP tools.

#### Scenario: Tool discovery on startup
- **GIVEN** the action agent is initialized
- **AND** mcp-gateway is running at the configured URL
- **WHEN** the agent calls `GET /api/tools`
- **THEN** the available servers and tools are cached
- **AND** only action definitions with matching available tools are activated

#### Scenario: Tool execution
- **GIVEN** an action requires calling `dav/create_contact`
- **AND** the `dav` server is available in mcp-gateway
- **WHEN** the action agent calls `POST /api/tools/dav/create_contact` with extracted arguments
- **THEN** mcp-gateway routes the call to the mcp-dav server
- **AND** the tool result is returned to the action agent

#### Scenario: mcp-gateway unavailable
- **GIVEN** mcp-gateway is not running or unreachable
- **WHEN** the action agent attempts to discover tools
- **THEN** an error is logged
- **AND** action processing is skipped for this sync cycle
- **AND** action tags remain on messages for retry on next cycle
- **AND** email sync continues normally

#### Scenario: Tool not available
- **GIVEN** an action tag "add-contact" maps to `dav/create_contact`
- **AND** the `dav` server is not configured in mcp-gateway
- **WHEN** the action agent processes the action
- **THEN** the action is skipped with status "skipped"
- **AND** a warning is logged indicating the required tool is unavailable
- **AND** the action tag remains on the message

---

### Requirement: AI Data Extraction

The action agent SHALL use Ollama to extract structured data from email content for populating MCP tool call arguments.

#### Scenario: Extract contact details from email
- **GIVEN** a message is tagged with "add-contact"
- **AND** the email is from "jane@newcompany.com" with signature containing "Jane Doe, CTO at NewCompany"
- **WHEN** the action agent processes the action
- **THEN** Ollama is called with the email content and the contact extraction prompt
- **AND** Ollama returns structured JSON with at minimum: formatted_name, emails
- **AND** optionally: organization, title, phones (if found in the email)

#### Scenario: Extract event details from email
- **GIVEN** a message is tagged with "create-reminder"
- **AND** the email mentions "payment due by February 15, 2025"
- **WHEN** the action agent processes the action
- **THEN** Ollama is called with the email content and the event extraction prompt
- **AND** Ollama returns structured JSON with: summary, start datetime, end datetime
- **AND** the summary reflects the email context (e.g., "Payment due - Invoice #1234")

#### Scenario: Extraction fails or returns incomplete data
- **GIVEN** Ollama cannot extract the required fields from the email
- **WHEN** extraction returns incomplete or malformed JSON
- **THEN** the action is logged with status "failed" and the extraction error
- **AND** the action tag remains on the message for user review
- **AND** the action is retried on the next sync cycle (up to max retries)

---

### Requirement: Action Processing in Sync Cycle

The sync engine SHALL process action tags as a step in each sync cycle, after classification.

#### Scenario: Successful action execution
- **GIVEN** a message has the "add-contact" action tag
- **AND** mcp-gateway is available with the `dav/create_contact` tool
- **WHEN** the sync cycle runs
- **THEN** the action agent extracts contact data via Ollama
- **AND** calls `dav/create_contact` via mcp-gateway with the extracted data
- **AND** the "add-contact" tag is removed from the message
- **AND** an entry is created in the `action_log` table with status "success"

#### Scenario: Action execution fails
- **GIVEN** a message has the "create-reminder" action tag
- **AND** the mcp-gateway tool call returns an error
- **WHEN** the sync cycle runs
- **THEN** the "create-reminder" tag remains on the message
- **AND** an entry is created in the `action_log` table with status "failed" and the error
- **AND** the action will be retried on the next sync cycle

#### Scenario: Max retries exceeded
- **GIVEN** a message has an action tag that has failed 3 consecutive times
- **WHEN** the sync cycle runs
- **THEN** the action is marked as "skipped" in the action_log
- **AND** the action tag remains on the message (so the user notices)
- **AND** no further retry attempts are made for this message+action combination

#### Scenario: Multiple action tags on one message
- **GIVEN** a message has both "add-contact" and "create-reminder" tags
- **WHEN** the sync cycle runs
- **THEN** both actions are processed independently
- **AND** each action succeeds or fails on its own
- **AND** each has its own action_log entry

#### Scenario: Rate limiting
- **GIVEN** 20 messages have action tags pending
- **AND** `max_actions_per_sync` is configured as 10
- **WHEN** the sync cycle runs
- **THEN** only 10 actions are processed (oldest first)
- **AND** the remaining 10 are deferred to the next sync cycle

---

### Requirement: Action Log

The system SHALL maintain an audit log of all action executions for status tracking and debugging.

#### Scenario: Successful action logged
- **GIVEN** an action tag is successfully processed
- **WHEN** the action completes
- **THEN** an `action_log` entry is created with:
  - message_id, account_id, action_name
  - server and tool that were called
  - extracted_data (what Ollama extracted)
  - tool_result (what the MCP tool returned)
  - status = "success"
  - processed_at timestamp

#### Scenario: Failed action logged
- **GIVEN** an action tag processing fails at any step
- **WHEN** the failure is recorded
- **THEN** an `action_log` entry is created with:
  - status = "failed"
  - error message describing the failure
  - extracted_data (if extraction succeeded before the failure)

#### Scenario: Action log cleanup
- **GIVEN** action log entries older than 90 days exist
- **WHEN** the sync cycle performs cleanup
- **THEN** entries older than 90 days are deleted
- **AND** recent entries are preserved

---

### Requirement: Action Tag Configuration

Users SHALL be able to define custom action tags via Nix configuration that map to any MCP tool available through mcp-gateway.

#### Scenario: Minimal custom action
- **GIVEN** a user adds to their Nix config:
  ```nix
  programs.axios-ai-mail.actions."flag-important" = {
    description = "Forward to manager";
    gateway.server = "mail";
    gateway.tool = "send_email";
  };
  ```
- **WHEN** the configuration is applied
- **THEN** "flag-important" appears as an action tag in the UI
- **AND** when applied to a message, it triggers the `mail/send_email` tool

#### Scenario: Action with default arguments
- **GIVEN** an action definition includes `defaultArgs`:
  ```nix
  programs.axios-ai-mail.actions."add-contact" = {
    gateway.server = "dav";
    gateway.tool = "create_contact";
    defaultArgs = { addressbook = "Family"; };
  };
  ```
- **WHEN** the action is processed
- **THEN** the `addressbook` field is set to "Family" in the tool call
- **AND** Ollama-extracted fields are merged with (but do not override) default args

#### Scenario: Gateway URL configuration
- **GIVEN** the user configures:
  ```nix
  programs.axios-ai-mail.gateway.url = "http://mcp-gateway.tailnet:8085";
  ```
- **WHEN** the action agent connects to mcp-gateway
- **THEN** it uses the configured URL instead of the default

---

### Requirement: Action API Endpoints

The system SHALL expose REST API endpoints for querying action status and configuration.

#### Scenario: List available actions
- **GIVEN** the action registry has 3 configured actions
- **AND** mcp-gateway has tools available for 2 of them
- **WHEN** `GET /api/actions/available` is called
- **THEN** all 3 actions are returned
- **AND** each includes an `available` boolean indicating tool availability

#### Scenario: Query action log
- **GIVEN** multiple actions have been processed
- **WHEN** `GET /api/actions/log` is called with pagination parameters
- **THEN** action log entries are returned sorted by processed_at descending
- **AND** each entry includes message subject, action name, status, and timestamp

#### Scenario: Retry failed action
- **GIVEN** an action log entry with status "failed" or "skipped"
- **WHEN** `POST /api/actions/retry/{log_id}` is called
- **THEN** the action tag is re-added to the message
- **AND** the retry counter is reset
- **AND** the action will be processed on the next sync cycle
