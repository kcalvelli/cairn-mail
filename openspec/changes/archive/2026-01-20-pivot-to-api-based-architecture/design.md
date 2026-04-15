# Design: API-Based Architecture with Two-Way Sync

## Context

This is a complete architectural pivot from a local Maildir+notmuch system to a cloud-connected API-based system. The goal is to make cairn-mail practical for real-world use by enabling two-way sync with email providers and offering modern UI options.

**Key Stakeholders:**
- End users who want AI email organization without leaving their normal email client
- Privacy-conscious users who want local AI processing (not cloud LLMs)
- Developers maintaining the codebase
- NixOS/Home Manager users who expect declarative configuration

**Constraints:**
- Must maintain privacy-first AI (local Ollama, no cloud LLMs)
- Must work with Gmail, IMAP, and Outlook.com at minimum
- Must be accessible to non-technical users (easier than current notmuch setup)
- Should leverage NixOS ecosystem but not require it

## Goals / Non-Goals

### Goals
- Two-way synchronization: AI tags appear in user's normal email client
- Modern, intuitive UI that doesn't require terminal expertise
- Support for major email providers (Gmail, Outlook.com, standard IMAP)
- Local AI processing for privacy
- Real-time or near-real-time classification of new emails
- Mobile-friendly (tags visible in mobile email apps)

### Non-Goals
- Replacing the user's email client (we enhance, not replace)
- Supporting every obscure email provider in MVP
- Offline-first email reading (emails stay on the provider)
- Enterprise features like shared mailboxes or delegation (initial version)
- End-to-end encryption of email content (provider's responsibility)

## System Architecture

### High-Level Components

```
┌─────────────────────────────────────────────────────────────┐
│                         User Layer                          │
├─────────────┬───────────────────┬───────────────────────────┤
│  Gmail Web  │  Outlook Mobile   │  Thunderbird Desktop      │
│             │                   │                           │
│  (sees AI   │  (sees AI         │  (sees AI labels via      │
│   labels)   │   categories)     │   IMAP sync)              │
└──────┬──────┴─────────┬─────────┴──────────┬────────────────┘
       │                │                    │
       │                │                    │
┌──────▼────────────────▼────────────────────▼────────────────┐
│                  Email Providers                            │
├────────────┬──────────────────┬──────────────────────────────┤
│ Gmail API  │  MS Graph API    │  IMAP w/ Extensions          │
│            │                  │                              │
│ (OAuth2)   │  (OAuth2)        │  (username/password or OAuth)│
└──────┬─────┴────────┬─────────┴──────────┬──────────────────┘
       │              │                    │
       │              │                    │
       │         API Calls (fetch/update)  │
       │              │                    │
┌──────▼──────────────▼────────────────────▼──────────────────┐
│              cairn-mail Backend                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │          Email Provider Abstraction Layer            │   │
│  │  (Unified interface for Gmail/IMAP/Outlook)          │   │
│  └───────────────────┬──────────────────────────────────┘   │
│                      │                                       │
│  ┌───────────────────▼──────────────────────────────────┐   │
│  │          Sync Engine                                 │   │
│  │  - Fetch new/changed messages                        │   │
│  │  - Track sync state (last sync, message IDs)         │   │
│  │  - Queue messages for classification                 │   │
│  │  - Push label/category updates back to provider      │   │
│  └───────────────────┬──────────────────────────────────┘   │
│                      │                                       │
│  ┌───────────────────▼──────────────────────────────────┐   │
│  │          AI Classification Engine                    │   │
│  │  - Calls local Ollama API                            │   │
│  │  - Extracts structured tags from LLM response        │   │
│  │  - Maps AI tags to provider label format             │   │
│  │  - Handles user feedback for tag corrections         │   │
│  └───────────────────┬──────────────────────────────────┘   │
│                      │                                       │
│  ┌───────────────────▼──────────────────────────────────┐   │
│  │          SQLite Database                             │   │
│  │  - Message metadata (ID, subject, sender, date)      │   │
│  │  - AI tags and classification timestamps             │   │
│  │  - Sync state (per-account cursors)                  │   │
│  │  - User feedback (tag corrections, preferences)      │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │          REST API Server                             │   │
│  │  - GET /messages (list with filters)                 │   │
│  │  - POST /classify (manual trigger)                   │   │
│  │  - PUT /tags (user corrections)                      │   │
│  │  - WebSocket /events (real-time updates)             │   │
│  └───────────────────┬──────────────────────────────────┘   │
└──────────────────────┼──────────────────────────────────────┘
                       │
         ┌─────────────┴─────────────┐
         │                           │
┌────────▼────────┐        ┌─────────▼──────────┐
│   Web UI        │        │  CLI Tool          │
│  (React SPA)    │        │  (Python/Rust)     │
│                 │        │                    │
│  - Message list │        │  - Manual sync     │
│  - Tag filters  │        │  - Reclassify      │
│  - Settings     │        │  - OAuth setup     │
└─────────────────┘        └────────────────────┘
```

### Data Flow: Email Classification

1. **Trigger**: Timer fires (every 5 minutes) or webhook received
2. **Fetch**: Sync Engine calls provider API to get new/changed messages
3. **Queue**: Messages without AI tags are queued for classification
4. **Classify**: AI Engine sends message to Ollama, receives structured tags
5. **Map**: Tags are converted to provider-specific format (Gmail labels, Outlook categories)
6. **Update**: Sync Engine pushes label updates back to provider via API
7. **Store**: Metadata and tags are saved to SQLite
8. **Notify**: WebSocket event sent to connected clients (web UI updates in real-time)

### Data Flow: User Feedback

1. **User corrects tag** in web UI or provider client (e.g., removes "Finance" label)
2. **Webhook or next poll** detects label change
3. **Sync Engine** records the correction in SQLite
4. **AI Engine** uses feedback to improve future classifications (optional ML feedback loop)

## Technical Decisions

### Decision: Use SQLite for Local State

**Rationale:**
- Fast, embedded, serverless database
- ACID transactions for sync state consistency
- Full-text search capability (FTS5) for local message search
- Zero-configuration for users
- Single file, easy to backup/reset

**Alternatives Considered:**
- PostgreSQL: Overkill, requires separate server, complex setup
- JSON files: No transaction support, hard to query efficiently
- Redis: In-memory only, persistence is complex, another service to manage

### Decision: Abstract Provider Interface

**Rationale:**
Create a unified interface that all providers implement:

```python
class EmailProvider(Protocol):
    def fetch_messages(self, since: datetime) -> List[Message]:
        """Fetch new/changed messages since last sync."""

    def update_labels(self, message_id: str, labels: Set[str]) -> None:
        """Apply labels/categories to a message."""

    def create_label(self, name: str, color: Optional[str]) -> str:
        """Create a new label/category if it doesn't exist."""

    def get_label_mapping(self) -> Dict[str, str]:
        """Map AI tag names to provider label IDs."""
```

This allows swapping providers without changing classification logic.

**Implementation Strategy:**
- `GmailProvider` uses Gmail API
- `OutlookProvider` uses Microsoft Graph API
- `ImapProvider` uses imaplib with extension detection

### Decision: Web Application as Default UI

**Rationale:**
- **Accessibility**: Works on any device with a browser (desktop, tablet, mobile)
- **Development Speed**: Single codebase, well-established tooling
- **Security**: Runs on `localhost`, no exposed network ports
- **Familiarity**: Users understand web interfaces

**Alternatives Considered:**
- Browser Extension: Limited to specific browsers, complex permissions model, hard to debug
- Desktop App (Electron): Larger bundle size, more complex distribution, still uses web tech
- Terminal UI: Defeats the purpose of this pivot (accessibility)

**Technology Choices:**
- **Frontend**: React with TypeScript (modern, well-documented, large ecosystem)
- **Backend**: FastAPI (Python) or Actix-web (Rust)
  - Python: Easier integration with existing AI classifier code, faster iteration
  - Rust: Better performance, type safety, but steeper learning curve
  - **Decision: Start with Python/FastAPI**, migrate to Rust if performance becomes an issue
- **Real-time**: WebSockets for live updates (Server-Sent Events as fallback)

### Decision: OAuth2 with User-Managed Apps

**Rationale:**
- **Privacy**: User controls their own OAuth app, cairn-mail never sees credentials
- **Rate Limits**: User gets their own quota (10k requests/day for Gmail)
- **Security**: No shared secrets, better isolation

**Trade-off**: Slightly more complex initial setup (must create OAuth app in Google Cloud Console)

**Mitigation**: Provide detailed documentation with screenshots and a helper CLI tool:
```bash
cairn-mail auth setup gmail
# Walks through OAuth app creation step-by-step
# Generates config snippet to paste into home.nix
```

### Decision: Secure Credential Storage

**Rationale:**
OAuth tokens and IMAP passwords are sensitive credentials that must be stored securely, not in plain text in the Nix store.

**Implementation Options** (support all three):

1. **sops-nix** (recommended for secrets in git):
   ```nix
   sops.secrets."email/gmail-oauth" = {
     owner = config.users.users.myuser.name;
   };

   programs.cairn-mail.accounts.personal = {
     provider = "gmail";
     oauthTokenFile = config.sops.secrets."email/gmail-oauth".path;
   };
   ```

2. **agenix** (simpler, age-encrypted):
   ```nix
   age.secrets.gmail-oauth.file = ./secrets/gmail-oauth.age;

   programs.cairn-mail.accounts.personal = {
     provider = "gmail";
     oauthTokenFile = config.age.secrets.gmail-oauth.path;
   };
   ```

3. **systemd-creds** (no external dependencies):
   ```nix
   programs.cairn-mail.accounts.personal = {
     provider = "gmail";
     oauthTokenFile = "/run/credentials/cairn-mail.service/gmail-oauth";
   };

   systemd.services.cairn-mail = {
     serviceConfig.LoadCredential = [
       "gmail-oauth:/path/to/oauth-token"
     ];
   };
   ```

**For IMAP passwords** (non-OAuth2 providers like Fastmail):
```nix
# Using sops-nix
sops.secrets."email/fastmail-password" = {};

programs.cairn-mail.accounts.work = {
  provider = "imap";
  email = "me@fastmail.com";
  passwordFile = config.sops.secrets."email/fastmail-password".path;
  imap.host = "imap.fastmail.com";
  smtp.host = "smtp.fastmail.com";
};
```

**Security Properties:**
- Secrets never stored in Nix store (which is world-readable)
- Decrypted only at runtime by systemd
- Proper file permissions (600, owned by service user)
- Support for password rotation without config changes

### Decision: Tag Mapping Strategy

AI tags must map to provider-specific concepts:

| AI Tag         | Gmail Label      | Outlook Category | IMAP Keyword      |
|----------------|------------------|------------------|-------------------|
| `work`         | `AI/Work`        | `Work (AI)`      | `$AI_Work`        |
| `finance`      | `AI/Finance`     | `Finance (AI)`   | `$AI_Finance`     |
| `todo`         | `AI/ToDo`        | `To-Do (AI)`     | `$AI_Todo`        |
| `prio-high`    | `AI/Priority`    | `Important`      | `$Flagged`        |

**Color Coding (Gmail):**
- `AI/Work`: Blue
- `AI/Finance`: Green
- `AI/ToDo`: Orange
- `AI/Priority`: Red

### Decision: Sync Strategy

**Polling-Based with Optional Webhooks:**
- **Default**: Poll every 5 minutes (configurable)
- **Gmail**: Optionally use Gmail Pub/Sub for real-time notifications
- **Outlook**: Optionally use Microsoft Graph change notifications
- **IMAP**: IDLE extension if supported, fallback to polling

**Incremental Sync:**
- Track `lastSyncTimestamp` per account in SQLite
- Gmail: Use `historyId` to fetch only changes since last sync
- Outlook: Use `deltaLink` for incremental queries
- IMAP: Use UIDNEXT and CHANGEDSINCE extension

### Decision: AI Classifier Adaptation

Keep the core classification logic from the current implementation:
- Structured JSON output from Ollama
- Tags: `work`, `finance`, `personal`, `dev`, `travel`, `shopping`, etc.
- Priority: `high`, `normal`
- Action required: `todo` tag
- Can archive: boolean

**Changes needed:**
1. Accept message as JSON input (instead of reading Maildir file):
   ```json
   {
     "id": "msg123",
     "subject": "Q4 Budget Review",
     "from": "boss@company.com",
     "to": "me@work.com",
     "date": "2026-01-15T10:30:00Z",
     "body": "Please review the attached...",
     "snippet": "Please review the attached..."
   }
   ```

2. Return tags as structured output:
   ```json
   {
     "tags": ["work", "finance"],
     "priority": "high",
     "todo": true,
     "can_archive": false
   }
   ```

3. No direct notmuch manipulation - Sync Engine handles label updates

## Component Specifications

### Email Provider Abstraction Layer

**Module**: `src/providers/base.py`

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List, Set, Dict, Optional

@dataclass
class Message:
    id: str
    thread_id: str
    subject: str
    from_email: str
    to_emails: List[str]
    date: datetime
    snippet: str  # First ~200 chars of body
    body_text: Optional[str]  # Full plain text body
    labels: Set[str]  # Current labels/categories
    is_unread: bool

class EmailProvider(ABC):
    @abstractmethod
    def authenticate(self) -> None:
        """Authenticate with the provider using OAuth2 or credentials."""

    @abstractmethod
    def fetch_messages(self, since: Optional[datetime] = None,
                      max_results: int = 100) -> List[Message]:
        """Fetch new/changed messages."""

    @abstractmethod
    def update_labels(self, message_id: str,
                     add_labels: Set[str],
                     remove_labels: Set[str]) -> None:
        """Update labels/categories on a message."""

    @abstractmethod
    def create_label(self, name: str,
                    color: Optional[str] = None) -> str:
        """Create a label/category (idempotent). Returns label ID."""

    @abstractmethod
    def list_labels(self) -> Dict[str, str]:
        """Get all labels. Returns {name: label_id}."""
```

**Implementations**:
- `src/providers/gmail.py` - GmailProvider using Gmail API
- `src/providers/outlook.py` - OutlookProvider using Microsoft Graph
- `src/providers/imap.py` - ImapProvider using imaplib

### Sync Engine

**Module**: `src/sync_engine.py`

```python
class SyncEngine:
    def __init__(self, provider: EmailProvider, db: Database,
                 ai_classifier: AIClassifier):
        self.provider = provider
        self.db = db
        self.ai_classifier = ai_classifier

    def sync(self) -> SyncResult:
        """Main sync loop."""
        # 1. Fetch new messages from provider
        last_sync = self.db.get_last_sync_time()
        messages = self.provider.fetch_messages(since=last_sync)

        # 2. Classify new messages
        for msg in messages:
            if not self.db.has_classification(msg.id):
                tags = self.ai_classifier.classify(msg)
                self.db.store_classification(msg.id, tags)

                # 3. Push AI tags back to provider
                label_names = self.map_tags_to_labels(tags)
                self.provider.update_labels(msg.id,
                                           add_labels=label_names,
                                           remove_labels=set())

        # 4. Update sync state
        self.db.update_last_sync_time(datetime.now())

        return SyncResult(processed=len(messages))
```

### AI Classifier

**Module**: `src/ai_classifier.py` (adapted from current implementation)

```python
class AIClassifier:
    def __init__(self, ollama_endpoint: str, model: str):
        self.ollama_endpoint = ollama_endpoint
        self.model = model

    def classify(self, message: Message) -> Classification:
        """Classify a message and return structured tags."""
        prompt = self._build_prompt(message)

        response = requests.post(f"{self.ollama_endpoint}/api/generate", json={
            "model": self.model,
            "prompt": prompt,
            "format": "json",
            "stream": False
        })

        result = response.json()
        classification = json.loads(result["response"])

        return Classification(
            tags=set(classification.get("tags", [])),
            priority=classification.get("priority", "normal"),
            todo=classification.get("action_required", False),
            can_archive=classification.get("can_archive", False)
        )
```

### REST API Server

**Module**: `src/api_server.py`

```python
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

@app.get("/api/messages")
async def list_messages(
    account: str,
    label: Optional[str] = None,
    limit: int = 50
):
    """List messages with optional label filter."""
    db = get_database()
    messages = db.query_messages(account, label, limit)
    return {"messages": messages}

@app.post("/api/sync")
async def trigger_sync(account: str):
    """Manually trigger sync for an account."""
    engine = get_sync_engine(account)
    result = engine.sync()
    return result

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time updates."""
    await websocket.accept()
    # Subscribe to sync events and push to client
```

### Web UI

**Framework**: React with TypeScript

**Key Components**:
- `MessageList`: Display messages with AI tags
- `TagFilter`: Sidebar with tag-based filtering
- `Settings`: Account management, AI preferences
- `Dashboard`: Overview of inbox, todo count, recent activity

**State Management**: React Query for server state, Zustand for client state

## Data Model (SQLite Schema)

```sql
-- Accounts configured by the user
CREATE TABLE accounts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    provider TEXT NOT NULL,  -- 'gmail', 'outlook', 'imap'
    last_sync TIMESTAMP,
    oauth_token TEXT,  -- Encrypted
    settings JSON
);

-- Message metadata (NOT full email bodies)
CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    thread_id TEXT,
    subject TEXT,
    from_email TEXT,
    to_emails TEXT,  -- JSON array
    date TIMESTAMP,
    snippet TEXT,
    is_unread BOOLEAN,
    provider_labels TEXT,  -- JSON array of current labels on provider
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);

-- AI classifications
CREATE TABLE classifications (
    message_id TEXT PRIMARY KEY,
    tags TEXT NOT NULL,  -- JSON array of AI tags
    priority TEXT,  -- 'high', 'normal'
    todo BOOLEAN,
    can_archive BOOLEAN,
    classified_at TIMESTAMP,
    model TEXT,  -- Which LLM model was used
    FOREIGN KEY (message_id) REFERENCES messages(id)
);

-- User feedback for improving classifications
CREATE TABLE feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL,
    original_tags TEXT,  -- JSON array
    corrected_tags TEXT,  -- JSON array
    corrected_at TIMESTAMP,
    FOREIGN KEY (message_id) REFERENCES messages(id)
);

-- Full-text search index
CREATE VIRTUAL TABLE messages_fts USING fts5(
    subject,
    from_email,
    snippet,
    content=messages
);
```

## Deployment Model

### NixOS/Home Manager Module (Declarative Configuration)

The module maintains the declarative configuration style from v1, but with provider-specific options:

```nix
programs.cairn-mail = {
  enable = true;

  # UI mode
  ui = "web";  # or "cli" for headless
  webPort = 8080;

  # AI settings
  ai = {
    enable = true;
    model = "llama3.2";
    endpoint = "http://localhost:11434";
    temperature = 0.3;  # Lower = more deterministic

    # Custom tag taxonomy (optional)
    tags = [
      { name = "work"; description = "Work-related emails"; }
      { name = "finance"; description = "Bills, transactions, statements"; }
      { name = "personal"; description = "Personal correspondence"; }
      { name = "dev"; description = "Developer notifications (GitHub, CI/CD)"; }
      # ... add custom tags
    ];
  };

  # Email accounts (declarative, supports multiple)
  accounts = {
    # Gmail with OAuth2
    personal = {
      provider = "gmail";
      email = "you@gmail.com";
      realName = "Your Name";

      # Secure OAuth token storage (choose one method)
      oauthTokenFile = config.sops.secrets."email/gmail-oauth".path;
      # OR: config.age.secrets.gmail-oauth.path
      # OR: "/run/credentials/cairn-mail.service/gmail-oauth"

      sync = {
        frequency = "5m";
        enableWebhooks = true;  # Use Gmail Pub/Sub for real-time
      };

      labels = {
        prefix = "AI";  # Creates labels like "AI/Work"
        colors = {
          work = "blue";
          finance = "green";
          todo = "orange";
          priority = "red";
        };
      };
    };

    # IMAP with password (Fastmail, self-hosted, etc.)
    work = {
      provider = "imap";
      email = "me@fastmail.com";
      realName = "Your Name";

      # Secure password storage
      passwordFile = config.sops.secrets."email/fastmail-password".path;

      imap = {
        host = "imap.fastmail.com";
        port = 993;
        tls = true;
      };

      smtp = {
        host = "smtp.fastmail.com";
        port = 465;
        tls = true;
      };

      sync = {
        frequency = "10m";  # IMAP can be less frequent
      };

      # IMAP keyword mapping for tags
      keywords = {
        work = "$AI_Work";
        finance = "$AI_Finance";
        # ...
      };
    };

    # Outlook.com with OAuth2
    outlook = {
      provider = "outlook";
      email = "you@outlook.com";
      realName = "Your Name";

      oauthTokenFile = config.sops.secrets."email/outlook-oauth".path;

      sync = {
        frequency = "5m";
        enableWebhooks = true;  # Use Microsoft Graph notifications
      };

      # Outlook categories mapping
      categories = {
        work = "Work (AI)";
        finance = "Finance (AI)";
        # ...
      };
    };
  };
};
```

### Secrets Management Setup Examples

#### Using sops-nix

1. **Install sops-nix** in your flake:
```nix
{
  inputs = {
    sops-nix.url = "github:Mic92/sops-nix";
    cairn-mail.url = "github:kcalvelli/cairn-mail";
  };
}
```

2. **Create encrypted secrets**:
```bash
# Create .sops.yaml with your age key
sops secrets/email.yaml
```

3. **Add to secrets/email.yaml**:
```yaml
gmail-oauth: |
  {
    "access_token": "ya29.xxx",
    "refresh_token": "1//xxx",
    "client_id": "xxx.apps.googleusercontent.com",
    "client_secret": "xxx"
  }

fastmail-password: "your-app-specific-password"
```

4. **Reference in config**:
```nix
sops.secrets."email/gmail-oauth" = {
  sopsFile = ./secrets/email.yaml;
  owner = config.users.users.myuser.name;
};

programs.cairn-mail.accounts.personal.oauthTokenFile =
  config.sops.secrets."email/gmail-oauth".path;
```

#### Using agenix

```nix
age.secrets.gmail-oauth = {
  file = ./secrets/gmail-oauth.age;
  owner = "myuser";
};

programs.cairn-mail.accounts.personal.oauthTokenFile =
  config.age.secrets.gmail-oauth.path;
```

#### Using systemd-creds (no external tools)

```nix
systemd.services.cairn-mail = {
  serviceConfig.LoadCredential = [
    "gmail-oauth:${config.users.users.myuser.home}/.secrets/gmail-oauth"
  ];
};

programs.cairn-mail.accounts.personal.oauthTokenFile =
  "/run/credentials/cairn-mail.service/gmail-oauth";
```

### Systemd Services

```
cairn-mail.service       # Main backend server
cairn-mail-sync.timer    # Periodic sync trigger
cairn-mail-sync.service  # Sync execution
```

### Docker (for non-NixOS users)

```yaml
# docker-compose.yml
services:
  cairn-mail:
    image: cairn-mail:latest
    ports:
      - "8080:8080"
    volumes:
      - ./config:/config
      - ./data:/data
    environment:
      - OLLAMA_ENDPOINT=http://ollama:11434

  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
```

## Initial Setup Flow

1. **Add cairn-mail to flake inputs**:
```nix
{
  inputs.cairn-mail.url = "github:kcalvelli/cairn-mail";
}
```

2. **Set up secrets** (choose sops-nix, agenix, or systemd-creds)

3. **Configure accounts declaratively** in home.nix

4. **Run OAuth setup for Gmail/Outlook**:
```bash
cairn-mail auth setup gmail
# Follow prompts, save token to secrets file
```

5. **Activate configuration**:
```bash
home-manager switch
```

6. **Access web UI**:
```bash
# Service starts automatically
open http://localhost:8080
```

7. **Verify sync**:
```bash
cairn-mail status
# Shows last sync time, message counts, errors
```

AI tags appear as labels in Gmail/Outlook within minutes!

## Risks & Mitigations

### Risk: API Rate Limits

**Gmail API**: 10,000 quota units/day (free tier)
- 1 message fetch = 5 units
- 1 label update = 5 units
- ~1000 messages/day maximum

**Mitigation**:
- Batch operations (fetch 100 messages at once)
- Smart polling (only sync when webhooks fire)
- Local caching to reduce redundant API calls
- Document paid tier for heavy users (1 billion units/day)

### Risk: OAuth Token Expiry

Tokens can expire or be revoked.

**Mitigation**:
- Automatic token refresh using refresh tokens
- User notification if manual re-auth needed
- Graceful degradation (stop sync, don't crash)

### Risk: Provider API Changes

Gmail/Outlook APIs can change without notice.

**Mitigation**:
- Abstract interface layer isolates provider-specific code
- Pin API versions in requests
- Automated tests against live APIs (optional)
- Community reports issues via GitHub

### Risk: SQLite Corruption

Database file could be corrupted.

**Mitigation**:
- WAL mode for concurrent access
- Automatic backups before schema migrations
- Easy reset: delete DB, resync from provider

### Risk: Privacy Concerns

Users might worry about OAuth tokens being stored locally.

**Mitigation**:
- Encrypt tokens at rest (using system keychain or age)
- Document exactly what data is stored locally
- Emphasize that emails never leave the provider (only metadata cached)
- Open source code for full transparency

## Open Questions

1. **Should we support multiple accounts in MVP?**
   - Recommendation: Yes, it's a common use case (personal + work)

2. **How should we handle very large mailboxes (100k+ messages)?**
   - Recommendation: Only classify messages from last 30 days by default, provide `reclassify --all` for historical

3. **Should AI tags be namespaced (AI/Work) or flat (Work)?**
   - Recommendation: Namespaced to avoid conflicts with user's existing labels

4. **Should we build a mobile app?**
   - Recommendation: Not in MVP. Tags visible in native Gmail/Outlook apps is sufficient.

5. **How should we handle email threading?**
   - Recommendation: Classify each message individually, but UI can group by thread

## Success Metrics

- **Setup Time**: <10 minutes from clone to first AI-tagged email
- **Sync Latency**: Tags appear in Gmail/Outlook within 1 minute of classification
- **API Efficiency**: <500 API calls/day for typical user (50 emails/day)
- **UI Performance**: Message list loads in <200ms
- **User Satisfaction**: 80%+ of users prefer v2 over v1 in feedback survey
