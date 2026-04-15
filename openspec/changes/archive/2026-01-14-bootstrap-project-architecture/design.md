# Design: cairn-mail Architecture

## Context
Standard email clients often require highly manual configuration across multiple tools (`isync`, `msmtp`, `notmuch`). `cairn-mail` centralizes this into a declarative model and adds local intelligence via LLMs.

## Goals
- Single source of truth for email accounts.
- Automated, local-only AI classification.
- TUI-friendly, reproducible setup.

## Technical Decisions

### 1. Configuration Generator
A Python script (`generate_configs.py`) will ingest a consolidated `accounts.yaml` and output the required dotfiles. This ensures that changes to an account (e.g., a password update or a new folder) propagate across all tools simultaneously.

### 2. Synchronization Flow
- **Retrieval**: `mbsync` pulls mail to local Maildir.
- **Indexing**: `notmuch new` indexes and initially tags mail as `new`.
- **Classification**: The AI agent queries `notmuch tag:new`, processes the content via Ollama, and applies semantic tags (`important`, `junk`).
- **Cleanup**: The `new` tag is removed once processed.

### 3. AI Agent Logic
The agent will prioritize headers (Subject, From) and the first 1KB of the body to minimize token usage and latency with local LLMs.
Classification Prompt:
> "Classify this email as 'junk', 'important', or 'neutral' based on its content. Output exactly one word."

### 4. Security
Passwords and OAuth tokens will not be stored in the declarative config. Instead, the generator will reference `pass` or `gpg` identifiers (e.g., `Pass: accounts/gmail/token`).

## Risks / Trade-offs
- **Local LLM Performance**: Running LLMs during sync might impact CPU; mitigated by running classification as a separate service after sync completes.
- **IMAP/OAuth2 Complexity**: Handled by mature scripts (`mutt_oauth2.py`) to reduce maintenance burden.
