# AI Tagging Capability

## ADDED Requirements

### Requirement: Local LLM Classification

The system SHALL use a local LLM (via Ollama) to classify email messages and assign structured tags while preserving user privacy.

#### Scenario: Message classification

- **WHEN** a new unclassified message is queued for processing
- **THEN** the system SHALL send the message content to the local Ollama endpoint
- **AND** SHALL request a structured JSON response containing tags, priority, action required, and archive recommendation
- **AND** SHALL parse the LLM response and validate the structure
- **AND** SHALL store the classification in the database

#### Scenario: Privacy preservation

- **WHEN** classifying any message
- **THEN** the system SHALL only send message data to the local Ollama endpoint (localhost or local network)
- **AND** SHALL NOT send message content to any external cloud APIs
- **AND** SHALL NOT store full message bodies permanently (only metadata and snippets)

#### Scenario: Structured tag extraction

- **WHEN** the LLM returns a classification response
- **THEN** the response SHALL be in JSON format with the following structure:
  ```json
  {
    "tags": ["work", "finance", "urgent"],
    "priority": "high",
    "action_required": true,
    "can_archive": false
  }
  ```
- **AND** the system SHALL validate that `tags` is a list of strings
- **AND** SHALL validate that `priority` is either "high" or "normal"
- **AND** SHALL validate that `action_required` and `can_archive` are booleans

### Requirement: Tag Taxonomy

The system SHALL support a predefined taxonomy of tags that can be extended by users.

#### Scenario: Default tag categories

- **WHEN** classifying messages with default configuration
- **THEN** the system SHALL recognize these tag categories:
  - `work`: Work-related emails
  - `personal`: Personal correspondence
  - `finance`: Financial statements, bills, transactions
  - `shopping`: Receipts, order confirmations, shipping notifications
  - `travel`: Flight confirmations, hotel bookings, itineraries
  - `dev`: Developer-related (commits, PRs, build notifications)
  - `social`: Social media notifications
  - `newsletter`: Newsletters and subscriptions
  - `junk`: Promotional emails, spam

#### Scenario: Custom tag taxonomy

- **WHEN** a user defines custom tags in the configuration
- **THEN** the system SHALL include the custom tags in the prompt to the LLM
- **AND** SHALL validate that classified messages only use tags from the allowed taxonomy
- **AND** SHALL log warnings for unrecognized tags

#### Scenario: Tag normalization

- **WHEN** the LLM returns tags
- **THEN** the system SHALL normalize tags to lowercase
- **AND** SHALL remove duplicates
- **AND** SHALL trim whitespace
- **AND** SHALL reject empty or invalid tag names

### Requirement: Priority and Action Classification

The system SHALL classify messages by priority level and whether they require user action.

#### Scenario: Priority classification

- **WHEN** a message is classified
- **THEN** the system SHALL assign either "high" or "normal" priority based on:
  - Sender importance (from contacts, managers, banks)
  - Message urgency (deadlines, action required language)
  - Subject indicators (URGENT, ASAP, etc.)

#### Scenario: Action required detection

- **WHEN** a message requires user action (reply needed, payment due, form to fill, etc.)
- **THEN** the system SHALL set `action_required: true`
- **AND** SHALL apply a `todo` tag
- **AND** SHALL NOT auto-archive the message

#### Scenario: Archive recommendation

- **WHEN** a message is a receipt, newsletter, or notification with no action required
- **THEN** the system SHALL set `can_archive: true`
- **AND** the sync engine SHALL remove the inbox label when pushing to the provider
- **AND** SHALL retain the message in the database for search

### Requirement: Classification Queue Management

The system SHALL efficiently queue and process messages for classification with priority handling.

#### Scenario: Queue new messages

- **WHEN** the sync engine fetches new messages
- **THEN** the system SHALL add unclassified messages to the classification queue
- **AND** SHALL prioritize messages by date (newest first)
- **AND** SHALL skip messages that already have classifications

#### Scenario: Batch classification

- **WHEN** processing the classification queue
- **THEN** the system SHALL classify up to 10 messages concurrently (configurable)
- **AND** SHALL respect Ollama API rate limits
- **AND** SHALL process messages in order of priority

#### Scenario: Reclassification trigger

- **WHEN** a user runs the `cairn-mail reclassify` command
- **THEN** the system SHALL re-queue all messages for classification
- **AND** SHALL overwrite previous classifications
- **AND** SHALL update labels on the provider

### Requirement: User Feedback Integration

The system SHALL allow users to correct AI classifications and learn from corrections over time.

#### Scenario: Record tag correction

- **WHEN** a user manually changes tags on a message (via web UI or provider client)
- **THEN** the system SHALL detect the change during the next sync
- **AND** SHALL store the correction in the `feedback` table with original and corrected tags
- **AND** SHALL timestamp the correction

#### Scenario: Feedback report

- **WHEN** a user requests a feedback report
- **THEN** the system SHALL generate a summary of common misclassifications:
  - Tags that are frequently removed (over-tagging)
  - Tags that are frequently added (under-tagging)
  - Patterns in sender/subject that correlate with corrections

#### Scenario: Prompt improvement

- **WHEN** feedback data is available
- **THEN** the system SHOULD adjust the classification prompt to reduce common errors
- **OR** SHOULD surface feedback patterns for manual prompt tuning

### Requirement: Model Configuration

The system SHALL allow users to configure which LLM model to use for classification and adjust model parameters.

#### Scenario: Model selection

- **WHEN** a user specifies a model in the configuration (e.g., `llama3.2`, `mistral`)
- **THEN** the system SHALL use that model for all classifications
- **AND** SHALL validate that the model is available in Ollama before starting
- **AND** SHALL log an error if the model is not found

#### Scenario: Model parameters

- **WHEN** sending classification requests to Ollama
- **THEN** the system SHALL set the following parameters:
  - `format: "json"` (enforce JSON output)
  - `temperature: 0.3` (lower temperature for more deterministic results)
  - `stream: false` (wait for complete response)
- **AND** SHALL allow users to override these parameters in configuration

#### Scenario: Fallback model

- **WHEN** the configured model fails to respond or is unavailable
- **THEN** the system SHOULD attempt to use a fallback model (e.g., `llama3` if `llama3.2` fails)
- **OR** SHALL log an error and skip classification if no fallback is configured

### Requirement: Confidence Scoring

The system SHALL provide confidence scores for classifications to help users identify uncertain classifications.

#### Scenario: Extract confidence from LLM

- **WHEN** the LLM supports confidence scoring in its response
- **THEN** the system SHALL extract the confidence value (0.0 to 1.0)
- **AND** SHALL store the confidence in the database

#### Scenario: Low confidence handling

- **WHEN** a classification has low confidence (< 0.6)
- **THEN** the system SHALL flag the message for user review
- **AND** SHALL NOT auto-archive low-confidence messages
- **AND** SHOULD display a confidence indicator in the web UI

### Requirement: Classification Performance

The system SHALL classify messages efficiently with acceptable latency and throughput.

#### Scenario: Classification latency

- **WHEN** classifying a single message
- **THEN** the system SHALL complete classification within 5 seconds (average)
- **AND** SHALL timeout after 30 seconds if the LLM does not respond

#### Scenario: Batch throughput

- **WHEN** classifying a batch of 100 messages
- **THEN** the system SHALL process at least 20 messages per minute (3 seconds per message)
- **AND** SHALL log performance metrics (messages/minute, average latency)

#### Scenario: Ollama unavailable

- **WHEN** the Ollama endpoint is unreachable
- **THEN** the system SHALL log a warning
- **AND** SHALL retry classification with exponential backoff
- **AND** SHALL NOT block sync operations (leave messages unclassified)

### Requirement: Prompt Engineering

The system SHALL use a well-designed prompt to guide the LLM toward accurate and consistent classifications.

#### Scenario: Prompt structure

- **WHEN** building the classification prompt
- **THEN** the system SHALL include:
  - Message subject, sender, recipients, and snippet
  - Available tag taxonomy with descriptions
  - Examples of each tag category (few-shot learning)
  - Instructions for priority and action detection
  - JSON schema for the expected response

#### Scenario: Context limit handling

- **WHEN** a message body exceeds the LLM's context limit (typically 4096 tokens)
- **THEN** the system SHALL truncate the body to fit within the limit
- **AND** SHALL prioritize the beginning of the message (subject, headers, first paragraphs)
- **AND** SHALL include the snippet in the prompt even if the full body is truncated

### Requirement: Tag-to-Label Mapping

The system SHALL map AI-generated tags to provider-specific labels for two-way sync.

#### Scenario: Gmail label creation

- **WHEN** an AI tag needs to be applied to a Gmail message
- **THEN** the system SHALL map the tag to a Gmail label (e.g., `work` → `AI/Work`)
- **AND** SHALL create the label if it doesn't exist
- **AND** SHALL set the label color based on configuration

#### Scenario: Outlook category mapping

- **WHEN** an AI tag needs to be applied to an Outlook message
- **THEN** the system SHALL map the tag to an Outlook category (e.g., `work` → `Work (AI)`)
- **AND** SHALL create the category if it doesn't exist

#### Scenario: IMAP keyword mapping

- **WHEN** an AI tag needs to be applied to an IMAP message
- **THEN** the system SHALL map the tag to an IMAP keyword (e.g., `work` → `$AI_Work`)
- **AND** SHALL use the KEYWORD extension if supported by the server
- **OR** SHALL fall back to custom flags if KEYWORD is unavailable

### Requirement: Classification Persistence

The system SHALL persist all classifications with timestamps for auditability and reclassification.

#### Scenario: Store classification

- **WHEN** a message is successfully classified
- **THEN** the system SHALL insert a record in the `classifications` table with:
  - `message_id`: The message identifier
  - `tags`: JSON array of assigned tags
  - `priority`: Priority level ("high" or "normal")
  - `todo`: Boolean indicating action required
  - `can_archive`: Boolean indicating archive recommendation
  - `classified_at`: Timestamp of classification
  - `model`: Name of the LLM model used

#### Scenario: Retrieve classification

- **WHEN** the web UI or API requests a message's classification
- **THEN** the system SHALL query the `classifications` table by `message_id`
- **AND** SHALL return the full classification record including tags and metadata

#### Scenario: Overwrite classification

- **WHEN** reclassifying a message that already has a classification
- **THEN** the system SHALL update the existing `classifications` record
- **AND** SHALL preserve the original classification in an audit log or `feedback` table
- **AND** SHALL update the `classified_at` timestamp
