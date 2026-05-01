# Changelog

All notable changes to cairn-mail. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), but with personality.

## [2.0.0] — 2026-05-01

The "stable enough to stop touching" release. Project renamed from
axios-ai-mail to cairn-mail, AI backend pivoted from Ollama-only to
OpenAI-compatible, MCP tool surface roughly doubled, and a pile of sync-engine
cleanups landed that make the thing actually behave on flaky networks.

### Renamed

- **axios-ai-mail → cairn-mail.** Project, package, config dir, systemd units,
  CLI binary — everything. The npm `axios` HTTP library is unrelated and
  stays.

### Changed

- **AI backend is now OpenAI-compatible, not Ollama-specific.** The classifier
  and the action-tag extractor both call `POST /v1/chat/completions` against
  whatever endpoint you point `ai.endpoint` at. Ollama still works (and is
  documented as one option), but so do llama.cpp, vLLM, LiteLLM, openai-gateway,
  and any hosted provider. Defaults moved to:
  - `ai.model = "claude-sonnet-4-20250514"`
  - `ai.endpoint = "http://localhost:18789"`
- **Action-tag extraction reuses the classifier's LLM endpoint** instead of
  requiring its own Ollama install. One AI configuration, one place to point
  it.

### Added

- **Six new MCP tools** for AI assistants driving the inbox: `update_tags`,
  `bulk_update_tags`, `delete_by_filter`, `restore_email`, `get_unread_count`,
  `list_tags`. Total surface is now 14 tools.
- **Hidden accounts.** Set `accounts.<name>.hidden = true` to keep an account
  syncing while excluding it from the default UI views. MCP callers still see
  it. Useful for agent/bot accounts that shouldn't clutter the inbox.
- **Action tags.** Tag a message `add-contact` or `create-reminder` and the
  next sync extracts structured data via your configured LLM and calls
  `mcp-dav` through `mcp-gateway`. Custom actions are pluggable in Nix —
  define your own server / tool / extraction prompt and you've got a new tag.
- **Adaptive sync backoff.** Quiet accounts (3+ syncs in a row with no new
  mail) downshift to every-other-cycle, then every fourth. New mail snaps them
  back to full cadence. Tracked per-account via `consecutive_empty_syncs`.
- **Stale-message purge.** After fetching from a provider, the local DB drops
  any message the provider no longer reports for that folder. The provider is
  the source of truth; the cache stays honest.
- **Ghost-account reaping.** Removing an account from home-manager config
  cascade-deletes it from the DB on the next config sync, along with all its
  messages, classifications, and pending operations.
- **Inbox-only classification.** Sent and trash folders sync but don't get
  tagged — there's no value in classifying mail you wrote or already
  discarded.
- **Tailscale Serve integration** for HTTPS exposure across your tailnet
  without port-forwarding.
- **Web Push notifications** via VAPID, with a PWA install path on Android
  and iOS.
- **Mobile recipient autocomplete** that commits free-typed addresses on
  comma, semicolon, and blur — not just Enter — so soft keyboards don't lose
  what you typed.
- **Async clear-trash** so bulk delete doesn't block the UI.

### Fixed

- **IMAP connect timeout.** Capped at 30 seconds. Stale pooled connections on
  flaky networks no longer hang the sync indefinitely.
- **`account_id` honored on `/messages/unread-count`** for proper per-account
  badges in multi-account UIs and MCP callers.
- **Hidden accounts excluded from `/tags` and `/stats`** endpoints (GUI only;
  MCP keeps full visibility).
- **OAuth refresh token expiry warning.** The CLI now flags unpublished Google
  OAuth apps, since testing-mode refresh tokens expire after 7 days.
- **LLM response parsing** strips markdown fences before JSON parsing — some
  models wrap their JSON in ```` ```json ```` blocks.

### Removed

- **Legacy v1 scripts.** `src/ai_classifier.py`, `src/reclassify.py`,
  `src/store_password.py`, `src/generate_config.py`, `src/mutt_oauth2.py`, and
  the `auth-v1` flake app. Replaced by the `cairn-mail` CLI and the
  Nix-generated `config.yaml`.
- **`ollama` Python client** from runtime dependencies in `pyproject.toml`.
  The OpenAI-compatible HTTP path is plain `requests`; the dedicated client
  isn't needed.
