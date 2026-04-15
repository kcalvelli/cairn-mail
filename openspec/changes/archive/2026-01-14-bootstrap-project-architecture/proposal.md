# Change: Bootstrap Project Architecture

## Why
To establish the foundational architecture for `cairn-mail`, providing a declarative configuration system, automated mail synchronization, and local AI-driven classification.

## What Changes
- **Configuration**: Define a central YAML/TOML spec and a generator for `mbsync`, `msmtp`, and `notmuch` configs.
- **Nix Integration**: Provide a `flake.nix` and a NixOS/Home-Manager module for declarative account definition.
- **Sync/Send**: Implement `mbsync` (isync) for retrieval and `msmtp` for sending, with OAuth2 support.
- **Indexing**: Utilize `notmuch` for email indexing and tagging.
- **AI Classification**: Build a Python-based agent interfacing with Ollama for automated mail tagging.
- **Automation**: Systemd units for background sync and AI classification loops.

## Impact
- **Affected Specs**: `config-generator`, `mail-sync`, `ai-classifier` (all NEW).
- **Architecture**: Move from manual dotfile management to a "Source of Truth" configuration model.
