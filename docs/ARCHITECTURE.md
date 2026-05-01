# Architecture Overview

Technical deep-dive into cairn-mail's system design.

## Table of Contents

- [System Overview](#system-overview)
- [Data Flow](#data-flow)
- [Provider Abstraction](#provider-abstraction)
- [Sync Engine](#sync-engine)
- [AI Classification Pipeline](#ai-classification-pipeline)
- [Database Schema](#database-schema)
- [API Design](#api-design)
- [Real-Time Updates](#real-time-updates)
- [Configuration System](#configuration-system)

---

## System Overview

cairn-mail is a layered architecture with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────────┐
│                     Presentation Layer                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              React Web UI (TypeScript)                   │   │
│  │    Material-UI • React Query • Zustand • WebSocket       │   │
│  └─────────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────────┘
                             │ REST API / WebSocket
┌────────────────────────────▼────────────────────────────────────┐
│                      Application Layer                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              FastAPI Backend (Python)                    │   │
│  │      Routes • Business Logic • WebSocket Manager         │   │
│  └─────────────────────────────────────────────────────────┘   │
└───────┬───────────────────────┬───────────────────────┬─────────┘
        │                       │                       │
        ▼                       ▼                       ▼
┌───────────────┐    ┌──────────────────────┐    ┌─────────────────┐
│  Sync Engine  │    │   AI Classifier      │    │    Database     │
│  • Providers  │    │  • OpenAI-compat     │    │   • SQLAlchemy  │
│  • Gmail API  │    │    /v1/chat client   │    │   • SQLite FTS  │
│  • IMAP       │    │  • Tag Taxonomy      │    │   • Migrations  │
│               │    │  • Confidence        │    │                 │
└───────────────┘    └──────────────────────┘    └─────────────────┘
```

### Design Principles

1. **Declarative Configuration** - Nix module generates all runtime config
2. **Provider Abstraction** - Unified interface for different email providers
3. **Local-First Storage** - All mail metadata, tags, and state stored locally in SQLite
4. **Bring-Your-Own LLM** - AI calls go to any OpenAI-compatible endpoint you configure (run locally for full privacy, or route through a gateway to a hosted model)
5. **Idempotent Operations** - Sync and config operations are safe to repeat

---

## Data Flow

### Email Sync Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Provider  │────▶│   Parser    │────▶│  Database   │
│  (Gmail/    │     │  (Extract   │     │  (Store     │
│   IMAP)     │     │   metadata) │     │   message)  │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                               │
                                               ▼
┌─────────────┐     ┌─────────────┐     ┌──────────────────┐
│  Provider   │◀────│   Tagger    │◀────│      AI          │
│  (Update    │     │  (Apply     │     │  Classifier      │
│   labels)   │     │   tags)     │     │ (OpenAI-compat)  │
└─────────────┘     └─────────────┘     └──────────────────┘
```

### Request/Response Flow

```
Client Request
      │
      ▼
┌─────────────┐
│   FastAPI   │
│   Router    │
└──────┬──────┘
       │
       ▼
┌─────────────┐     ┌─────────────┐
│  Business   │────▶│   Database  │
│   Logic     │◀────│   Queries   │
└──────┬──────┘     └─────────────┘
       │
       ▼
┌─────────────┐
│  Response   │
│   Model     │
└──────┬──────┘
       │
       ▼
Client Response
```

---

## Provider Abstraction

### Class Hierarchy

```
BaseEmailProvider (Abstract)
├── GmailProvider
│   └── Uses Gmail API with OAuth2
├── IMAPProvider
│   └── Uses IMAP with password auth
└── (Future) OutlookProvider
    └── Will use Microsoft Graph API
```

### Provider Interface

```python
class BaseEmailProvider(ABC):
    """Abstract base class for email providers."""

    @abstractmethod
    def authenticate(self) -> bool:
        """Authenticate with the provider."""
        pass

    @abstractmethod
    def fetch_messages(
        self,
        folder: str = "INBOX",
        max_results: int = 100,
        since: datetime | None = None
    ) -> list[Message]:
        """Fetch messages from provider."""
        pass

    @abstractmethod
    def get_message(self, message_id: str) -> Message | None:
        """Get a single message by ID."""
        pass

    @abstractmethod
    def update_labels(
        self,
        message_id: str,
        add_labels: list[str],
        remove_labels: list[str]
    ) -> bool:
        """Update message labels/tags."""
        pass

    @abstractmethod
    def move_message(
        self,
        message_id: str,
        from_folder: str,
        to_folder: str
    ) -> bool:
        """Move message between folders."""
        pass

    @abstractmethod
    def send_message(self, message: OutgoingMessage) -> bool:
        """Send a new message."""
        pass
```

### Provider Factory

```python
class ProviderFactory:
    """Create provider instances from database accounts."""

    @staticmethod
    def create_from_account(account: Account) -> BaseEmailProvider:
        """Create appropriate provider based on account type."""
        if account.provider == "gmail":
            return GmailProvider(GmailConfig(...))
        elif account.provider == "imap":
            return IMAPProvider(IMAPConfig(...))
        else:
            raise ValueError(f"Unknown provider: {account.provider}")
```

### Gmail Provider

- Uses Google Gmail API via `google-api-python-client`
- OAuth2 authentication with token refresh
- Labels stored as `AI/tagname`
- Folders mapped from Gmail labels (INBOX, SENT, TRASH)

### IMAP Provider

- Uses Python's `imaplib` for IMAP4 protocol
- Password authentication (stored encrypted)
- Tags stored as IMAP KEYWORDS (`$tagname`)
- Falls back to read-only if KEYWORD not supported

---

## Sync Engine

### Sync Orchestration

```python
class SyncEngine:
    """Orchestrates the sync process."""

    async def sync_account(self, account_id: str, max_messages: int = 100):
        """Sync a single account."""

        # 1. Load config and create provider
        account = self.db.get_account(account_id)
        provider = ProviderFactory.create_from_account(account)

        # 2. Authenticate
        provider.authenticate()

        # 3. Fetch messages from all folders
        for folder in ["INBOX", "SENT", "TRASH"]:
            messages = provider.fetch_messages(folder, max_messages)

            for message in messages:
                # 4. Store in database
                self.db.upsert_message(message)

                # 5. Classify with AI
                if not message.tags:
                    classification = await self.classifier.classify(message)
                    message.tags = classification.tags
                    message.confidence = classification.confidence

                    # 6. Update provider labels
                    provider.update_labels(message.id, message.tags, [])

        # 7. Notify connected clients
        await self.websocket.broadcast({
            "type": "sync_complete",
            "account_id": account_id
        })
```

### Sync Timer

Systemd timer runs sync at configured intervals:

```
[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
Persistent=true
```

### Sync Behaviors

The sync engine includes several efficiency and resilience features beyond plain "fetch new mail":

**Adaptive backoff for quiet accounts.** Each `Account` row tracks `consecutive_empty_syncs`. After 3 syncs in a row that returned no new messages, that account is only synced every other cycle; after more empty syncs, every fourth. Any new mail resets the counter. This keeps long-tail / mostly-idle accounts from burning cycles without delaying active ones.

**Inbox-only classification.** The classifier only runs against `INBOX`. Messages in `SENT` and `TRASH` are stored and indexed, but never tagged — there's no value in classifying mail you wrote or already discarded.

**Stale-message purge.** After fetching from a provider, any local message that the provider no longer reports for that folder is deleted from the DB. The provider is treated as authoritative; the local store is a cache.

**Ghost-account reaping.** When `~/.config/cairn-mail/config.yaml` is reloaded, any DB account that no longer appears in the config is removed (cascade-deletes its messages, classifications, and pending operations). This cleans up after `nixos-rebuild switch` removes an account from your home-manager config.

**IMAP connection timeout.** IMAP connects use a 30-second socket timeout. Previously, a stale pooled connection on a flaky network could hang the sync indefinitely.

**`account_id`-scoped unread counts.** `GET /messages/unread-count` accepts an optional `account_id` query param so multi-account UIs and MCP callers can show per-account badges without pulling the whole message list.

### Async Provider Sync (Pending Operations Queue)

User actions (mark read, delete, restore) update the local database immediately for instant UI feedback. Provider synchronization happens asynchronously in the background via a pending operations queue.

```
User Action → Local DB Update (instant) → Queue Operation → Return Response
                                                ↓
                              Next Sync Cycle → Process Queue → Provider API
```

**PendingOperation Model:**

```python
class PendingOperation(Base):
    id: str                 # Unique operation ID
    account_id: str         # Account FK
    message_id: str         # Message FK
    operation: str          # mark_read, mark_unread, trash, restore, delete
    status: str             # pending, completed, failed
    attempts: int           # Retry count
    last_error: str | None  # Error message if failed
    created_at: datetime    # For ordering
```

**Queue Operations:**

| Operation | Local DB Update | Provider Action |
|-----------|----------------|-----------------|
| `mark_read` | `is_unread = False` | Remove UNREAD label / Set \\Seen flag |
| `mark_unread` | `is_unread = True` | Add UNREAD label / Clear \\Seen flag |
| `trash` | `is_trashed = True` | Move to Trash folder |
| `restore` | `is_trashed = False` | Move to Inbox |
| `delete` | Delete from DB | Permanent delete |

**Smart Deduplication:**

Opposite operations cancel each other out:
- `mark_read` + `mark_unread` on same message → both removed
- `trash` + `restore` on same message → both removed

This prevents unnecessary API calls when users toggle state rapidly.

**Processing Order:**

Pending operations are processed at the **start** of each sync cycle, before fetching new messages. This ensures user actions take priority and reduces state conflicts.

---

## AI Classification Pipeline

### Classification Flow

```
┌─────────────┐
│   Message   │
│  (subject,  │
│   sender,   │
│   snippet)  │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Prompt    │
│  Generator  │
│  (build LLM │
│   prompt)   │
└──────┬──────┘
       │
       ▼
┌──────────────────┐
│  OpenAI-compat   │
│   API Call       │
│ /v1/chat/        │
│   completions    │
└─────────┬────────┘
       │
       ▼
┌─────────────┐
│   Parser    │
│  (extract   │
│   JSON)     │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Classification│
│  (tags,     │
│  confidence,│
│   priority) │
└─────────────┘
```

### Prompt Structure

```
You are an email classifier. Analyze the email and return JSON.

Available tags: {tag_list}

Email:
From: {sender}
Subject: {subject}
Preview: {snippet}

Return JSON with:
- tags: array of 1-3 most relevant tags
- confidence: 0.0-1.0 how confident you are
- priority: "high" or "normal"
- needs_action: boolean
```

### Confidence Scoring

| Score | Meaning | UI Display |
|-------|---------|------------|
| 0.8+ | High confidence | Green dot |
| 0.5-0.8 | Medium confidence | Orange dot |
| <0.5 | Low confidence | Red dot |

### Tag Taxonomy

Default taxonomy (35 tags) organized by category:

- **Priority:** urgent, important, review
- **Work:** work, project, meeting, deadline
- **Personal:** personal, family, friends, hobby
- **Finance:** finance, invoice, payment, expense
- **Shopping:** shopping, receipt, shipping
- **Travel:** travel, booking, itinerary, flight
- **Developer:** dev, github, ci, alert
- **Marketing:** marketing, newsletter, promotion, announcement
- **Social:** social, notification, update, reminder
- **System:** junk

---

## Database Schema

### Entity Relationship

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Account   │────┐│   Message   │────┐│    Tag      │
├─────────────┤    │├─────────────┤    │├─────────────┤
│ id (PK)     │    ││ id (PK)     │    ││ id (PK)     │
│ email       │◀───┼│ account_id  │    ││ name        │
│ provider    │    ││ subject     │    ││ description │
│ settings    │    ││ sender      │◀───┤│ color       │
└─────────────┘    ││ body        │    │└─────────────┘
                   ││ folder      │    │
                   ││ is_read     │    │  ┌─────────────┐
                   ││ confidence  │    └─▶│ MessageTag  │
                   │└─────────────┘       ├─────────────┤
                   │                      │ message_id  │
                   └──────────────────────│ tag_id      │
                                          └─────────────┘
```

### Key Tables

**accounts**
```sql
CREATE TABLE accounts (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    provider TEXT NOT NULL,
    real_name TEXT,
    settings JSON,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

**messages**
```sql
CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    account_id TEXT REFERENCES accounts(id),
    provider_id TEXT NOT NULL,      -- Original provider message ID
    subject TEXT,
    sender TEXT,
    recipients TEXT,                -- JSON array
    body TEXT,
    snippet TEXT,                   -- First 200 chars
    folder TEXT DEFAULT 'INBOX',
    original_folder TEXT,           -- For restore from trash
    is_read BOOLEAN DEFAULT FALSE,
    has_attachments BOOLEAN DEFAULT FALSE,
    confidence REAL,
    priority TEXT,
    received_at TIMESTAMP,
    classified_at TIMESTAMP,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- Full-text search
CREATE VIRTUAL TABLE messages_fts USING fts5(
    subject, sender, body,
    content='messages',
    content_rowid='rowid'
);
```

**tags**
```sql
CREATE TABLE tags (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    color TEXT,
    is_default BOOLEAN DEFAULT FALSE
);
```

**message_tags**
```sql
CREATE TABLE message_tags (
    message_id TEXT REFERENCES messages(id),
    tag_id INTEGER REFERENCES tags(id),
    PRIMARY KEY (message_id, tag_id)
);
```

---

## API Design

### REST Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/messages` | List messages (with filters) |
| GET | `/api/messages/{id}` | Get single message |
| PATCH | `/api/messages/{id}` | Update message (tags, read) |
| DELETE | `/api/messages/{id}` | Move to trash |
| POST | `/api/messages/{id}/restore` | Restore from trash |
| DELETE | `/api/messages/{id}/permanent` | Permanently delete |
| GET | `/api/accounts` | List accounts |
| GET | `/api/tags` | List all tags |
| GET | `/api/stats` | Get statistics |
| POST | `/api/sync` | Trigger sync |
| POST | `/api/compose` | Send new message |
| GET | `/api/health` | Health check |

### Query Parameters

```
GET /api/messages?
  folder=INBOX&
  account=personal&
  tag=work&
  unread=true&
  search=project&
  limit=50&
  offset=0
```

### Response Format

```json
{
  "messages": [
    {
      "id": "msg_123",
      "subject": "Project Update",
      "sender": "alice@example.com",
      "snippet": "Here's the latest...",
      "folder": "INBOX",
      "is_read": false,
      "tags": [
        { "name": "work", "color": "blue" }
      ],
      "confidence": 0.92,
      "received_at": "2024-01-15T10:30:00Z"
    }
  ],
  "total": 150,
  "has_more": true
}
```

---

## Real-Time Updates

### WebSocket Protocol

```
Client                          Server
   │                               │
   │──── connect ─────────────────▶│
   │◀─── connected ────────────────│
   │                               │
   │◀─── message_created ──────────│ (new sync)
   │◀─── message_updated ──────────│ (tag change)
   │◀─── message_deleted ──────────│ (moved to trash)
   │◀─── sync_complete ────────────│ (sync finished)
   │                               │
   │──── ping ────────────────────▶│
   │◀─── pong ─────────────────────│
   │                               │
```

### Event Types

```typescript
interface WebSocketMessage {
  type: 'message_created' | 'message_updated' | 'message_deleted' | 'sync_complete';
  payload: {
    message_id?: string;
    account_id?: string;
    changes?: Record<string, unknown>;
  };
}
```

### Client Handling

```typescript
// React hook for WebSocket
function useWebSocket() {
  const queryClient = useQueryClient();

  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8080/ws');

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === 'message_created' || data.type === 'sync_complete') {
        queryClient.invalidateQueries({ queryKey: ['messages'] });
      }
    };

    return () => ws.close();
  }, []);
}
```

---

## Configuration System

### Configuration Flow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Nix Module     │────▶│   config.yaml   │────▶│   Database      │
│  (declarative)  │     │   (runtime)     │     │   (accounts)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │
        │ home-manager switch
        ▼
┌─────────────────┐
│ ~/.config/      │
│ cairn-mail/  │
│ config.yaml     │
└─────────────────┘
```

### Config Loading

```python
class ConfigLoader:
    """Load Nix-generated config and sync to database."""

    @staticmethod
    def load_config(path: Path = None) -> dict:
        """Load config.yaml (JSON format)."""
        if path is None:
            path = Path.home() / ".config/cairn-mail/config.yaml"
        return json.loads(path.read_text())

    @staticmethod
    def sync_to_database(db: Database, config: dict) -> None:
        """Create/update accounts from config."""
        for account_id, account_data in config["accounts"].items():
            db.upsert_account(
                id=account_id,
                email=account_data["email"],
                provider=account_data["provider"],
                settings=account_data["settings"]
            )
```

### Runtime Config Structure

```json
{
  "database_path": "~/.local/share/cairn-mail/mail.db",
  "accounts": {
    "personal": {
      "id": "personal",
      "provider": "gmail",
      "email": "user@gmail.com",
      "credential_file": "/run/secrets/gmail-token",
      "settings": {
        "label_prefix": "AI",
        "sync_frequency": "5m"
      }
    }
  },
  "ai": {
    "enable": true,
    "model": "claude-sonnet-4-20250514",
    "endpoint": "http://localhost:18789",
    "temperature": 0.3
  }
}
```
