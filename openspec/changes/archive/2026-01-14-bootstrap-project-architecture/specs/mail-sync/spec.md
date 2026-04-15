## ADDED Requirements

### Requirement: IMAP Synchronization
The system SHALL synchronize remote IMAP accounts to local Maildir storage using `mbsync`.

#### Scenario: Sync new mail
- **WHEN** the `cairn-mail-sync.service` triggers
- **THEN** it runs `mbsync -a`
- **AND** it runs `notmuch new` to update the local index

### Requirement: OAuth2 Authentication
The system SHALL support OAuth2 authentication for providers like GMail and Outlook.

#### Scenario: Authenticate with GMail
- **WHEN** the sync process starts for a GMail account
- **THEN** it uses `mutt_oauth2.py` to retrieve the current token
- **AND** it successfully authenticates the IMAP session

> **Implementation Note (NixOS)**:
> Native `XOAUTH2` support in `mbsync` on NixOS requires the `cyrus-sasl-xoauth2` plugin. The Nix module MUST inject this plugin into the `SASL_PATH` environment variable for `mbsync` to successfully negotiate authentication with GMail/Outlook.
