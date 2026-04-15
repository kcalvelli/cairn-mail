# Implementation Progress

## Phase 1: Core Infrastructure (MVP) - IN PROGRESS

### ✅ Completed Components

1. **Python Project Structure**
   - Created `pyproject.toml` with all dependencies
   - Organized code into `cairn_mail` package
   - Set up black, ruff, mypy for code quality

2. **Database Layer** (`src/cairn_mail/db/`)
   - SQLAlchemy models: Account, Message, Classification, Feedback
   - Database abstraction with context managers
   - SQLite with WAL mode, foreign keys, optimizations
   - Full CRUD operations for all entities

3. **Credential Storage** (`src/cairn_mail/credentials.py`)
   - Support for sops-nix decrypted secrets
   - Support for agenix decrypted secrets
   - Support for systemd LoadCredential
   - OAuth token loading and refresh/write-back
   - IMAP password loading
   - File permission validation
   - Secret manager auto-detection

4. **Email Provider Abstraction** (`src/cairn_mail/providers/`)
   - `EmailProvider` protocol interface
   - `BaseEmailProvider` abstract base class
   - `Message` and `Classification` data classes
   - `ProviderRegistry` for dynamic provider loading
   - Label mapping utilities

5. **Gmail Provider** (`src/cairn_mail/providers/implementations/gmail.py`)
   - OAuth2 authentication with automatic token refresh
   - Message fetching with date filtering
   - Gmail API label management (create, list, update)
   - Two-way label sync
   - Configurable label prefix and colors

6. **AI Classifier** (`src/cairn_mail/ai_classifier.py`)
   - Ollama integration for local LLM
   - Structured JSON output parsing
   - Configurable tag taxonomy
   - Priority detection (high/normal)
   - Action required detection (todo)
   - Archive recommendation
   - Tag normalization and validation
   - Batch classification support

7. **Sync Engine** (`src/cairn_mail/sync_engine.py`)
   - Orchestrates fetch → classify → label pipeline
   - Incremental sync (only new messages since last sync)
   - Two-way label sync to provider
   - Reclassification of existing messages
   - Detailed sync statistics (SyncResult)
   - Error isolation (one message failure doesn't stop sync)

8. **CLI Tools** (`src/cairn_mail/cli/`)
   - `cairn-mail auth setup gmail` - OAuth2 setup wizard
   - `cairn-mail sync run` - Manual sync trigger
   - `cairn-mail sync reclassify` - Reclassify all messages
   - `cairn-mail status` - Show sync state and statistics
   - Rich terminal UI with tables, panels, colors
   - Comprehensive error handling and logging

### 🚧 In Progress

9. **NixOS Module** (`modules/home-manager.nix`)
   - Need to update for new configuration schema
   - Add declarative account definitions
   - Integrate with sops-nix/agenix/systemd-creds
   - Generate systemd services for sync

### 📋 TODO

- [ ] Update flake.nix for new Python package structure
- [ ] Write tests for core components
- [ ] Add IMAP provider implementation
- [ ] Add Outlook/Microsoft Graph provider implementation
- [ ] Build web UI (FastAPI + React)
- [ ] Add REST API server
- [ ] Implement WebSocket real-time updates
- [ ] Documentation (user guide, API docs)

## Architecture Overview

```
User Configuration (home.nix)
         ↓
    NixOS Module
         ↓
   Systemd Services
         ↓
┌──────────────────────────────────┐
│     cairn-mail Backend        │
├──────────────────────────────────┤
│  ┌────────────────────────────┐  │
│  │    CLI Tools (Typer)       │  │
│  │  - auth, sync, status      │  │
│  └────────────────────────────┘  │
│                                  │
│  ┌────────────────────────────┐  │
│  │    Sync Engine             │  │
│  │  - Orchestration           │  │
│  └────────────────────────────┘  │
│                                  │
│  ┌────────────────────────────┐  │
│  │    Email Providers         │  │
│  │  - Gmail (✓)               │  │
│  │  - IMAP (TODO)             │  │
│  │  - Outlook (TODO)          │  │
│  └────────────────────────────┘  │
│                                  │
│  ┌────────────────────────────┐  │
│  │    AI Classifier           │  │
│  │  - Ollama integration      │  │
│  │  - Local LLM processing    │  │
│  └────────────────────────────┘  │
│                                  │
│  ┌────────────────────────────┐  │
│  │    Database (SQLite)       │  │
│  │  - Messages, Accounts      │  │
│  │  - Classifications         │  │
│  │  - Feedback                │  │
│  └────────────────────────────┘  │
│                                  │
│  ┌────────────────────────────┐  │
│  │  Credential Storage        │  │
│  │  - sops-nix/agenix/        │  │
│  │    systemd-creds           │  │
│  └────────────────────────────┘  │
└──────────────────────────────────┘
         ↕
    Gmail API / IMAP
         ↕
   Email Providers
```

## Data Flow

1. **Sync Trigger** (timer or manual)
2. **Fetch Messages** from provider (Gmail API)
3. **Store** message metadata in SQLite
4. **Classify** unclassified messages using Ollama
5. **Store** classifications in database
6. **Push Labels** back to provider
7. **Update** sync timestamp

## Configuration Example

```nix
programs.cairn-mail = {
  enable = true;

  accounts = {
    personal = {
      provider = "gmail";
      email = "you@gmail.com";
      oauthTokenFile = config.sops.secrets."email/gmail-oauth".path;

      sync.frequency = "5m";
      labels.prefix = "AI";
    };

    work = {
      provider = "imap";
      email = "you@fastmail.com";
      passwordFile = config.sops.secrets."email/fastmail-password".path;

      imap.host = "imap.fastmail.com";
      smtp.host = "smtp.fastmail.com";
    };
  };

  ai = {
    model = "llama3.2";
    endpoint = "http://localhost:11434";
  };
};
```

## Testing

### Manual Testing

```bash
# Set up development environment
nix develop

# Install package in development mode
pip install -e .

# Run OAuth setup
cairn-mail auth setup gmail --output /tmp/gmail-token.json

# Test sync (requires valid credentials)
cairn-mail sync run --account personal --max 10

# Check status
cairn-mail status

# Reclassify messages
cairn-mail sync reclassify personal --max 50
```

### Unit Testing (TODO)

```bash
pytest tests/
pytest --cov=cairn_mail tests/
```

## Next Steps

1. Update NixOS module for declarative configuration
2. Update flake.nix to build the new Python package
3. Test end-to-end flow with real Gmail account
4. Add IMAP provider for Fastmail/self-hosted
5. Begin Phase 2 (Web UI)
