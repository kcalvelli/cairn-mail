## ADDED Requirements

### Requirement: Nix Flake Delivery
The project SHALL be delivered as a Nix Flake.

#### Scenario: Run generator via flake
- **WHEN** running `nix run github:user/cairn-mail#generate`
- **THEN** it executes the config generator script

### Requirement: NixOS/Home-Manager Module
The project SHALL provide a Nix module that allows users to define email accounts and automation settings.

#### Scenario: Define account in Nix
- **WHEN** a user defines `services.cairn-mail.accounts.personal = { ... }` in their Nix configuration
- **THEN** the module correctly passes this configuration to the generator
- **AND** it sets up the necessary systemd timers and services
