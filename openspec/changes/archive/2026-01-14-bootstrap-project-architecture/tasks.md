# Tasks: Bootstrap Project Architecture

## 1. Infrastructure & Generator
- [x] 1.1 Create central declarative configuration schema (YAML/TOML).
- [x] 1.2 Implement the Config Generator (Python/Go) to produce `.mbsyncrc`, `.msmtp-accounts`, and `notmuch` configs.
- [x] 1.3 Create a `flake.nix` that exports the scripts and a NixOS/Home-Manager module.
- [x] 1.4 Define Nix module options for email accounts that map to the generator's schema.

## 2. Mail Sync & OAuth2
- [x] 2.1 Integrate `mutt_oauth2.py` for GMail/Outlook token handling.
- [x] 2.2 Configure `mbsync` for Maildir synchronization.
- [x] 2.3 Configure `notmuch` for indexing and initial tagging logic.

## 3. AI Agent (Ollama Interface)
- [x] 3.1 Implement a Python agent to query `notmuch` for `tag:new` mail.
- [x] 3.2 Implement Ollama interaction layer (classify as `junk`, `important`, `neutral`).
- [x] 3.3 Implement `notmuch` tagging feedback loop.

## 4. Systemd Integration
- [x] 4.1 Create `cairn-mail-sync.service` and timer.
- [x] 4.2 Create `cairn-ai-classifier.service` logic.
