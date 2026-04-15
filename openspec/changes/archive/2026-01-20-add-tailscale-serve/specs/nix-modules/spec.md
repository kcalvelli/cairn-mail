## ADDED Requirements

### Requirement: Tailscale Serve Integration
The NixOS module SHALL provide an optional `tailscaleServe` configuration block that exposes the cairn-mail web service across the user's Tailscale network via HTTPS.

The integration SHALL:
- Be disabled by default (opt-in)
- Use HTTPS port 8443 by default
- Handle Tailscale connection timing by waiting up to 60 seconds for Tailscale to reach "Running" state
- Clean up serve configuration when the service stops
- Require `services.tailscale.enable = true` via assertion

#### Scenario: User enables Tailscale Serve with defaults
- **GIVEN** the user has `services.tailscale.enable = true`
- **WHEN** the user sets `services.cairn-mail.tailscaleServe.enable = true`
- **THEN** the system creates a systemd service `cairn-mail-tailscale-serve`
- **AND** the service exposes `https://{hostname}.{tailnet}:8443` proxying to `localhost:{webPort}`

#### Scenario: User customizes HTTPS port
- **GIVEN** Tailscale Serve is enabled
- **WHEN** the user sets `tailscaleServe.httpsPort = 443`
- **THEN** the service exposes `https://{hostname}.{tailnet}:443` (default HTTPS port)

#### Scenario: Tailscale not connected at boot
- **GIVEN** Tailscale Serve is enabled
- **WHEN** the system boots and Tailscale daemon starts but hasn't connected yet
- **THEN** the serve service waits up to 60 seconds polling `tailscale status`
- **AND** starts the serve proxy once Tailscale reports "Running" state

#### Scenario: Tailscale service not enabled
- **GIVEN** `services.tailscale.enable` is not set or false
- **WHEN** the user sets `services.cairn-mail.tailscaleServe.enable = true`
- **THEN** NixOS evaluation fails with an assertion error explaining that Tailscale must be enabled

#### Scenario: Service cleanup on stop
- **GIVEN** the Tailscale Serve service is running
- **WHEN** the service is stopped (manually or system shutdown)
- **THEN** the service runs `tailscale serve --https={port} off` to clean up the serve configuration

### Requirement: System-Level Sync Service
The NixOS module SHALL provide a `sync` configuration block that runs the email sync service at the system level, replacing the previous home-manager user-level service.

The sync service SHALL:
- Be enabled by default when the main service is enabled
- Run as the configured `user`
- Use a systemd timer for periodic execution
- Support configurable sync frequency (default: 5 minutes)
- Support configurable boot delay (default: 2 minutes)
- Use `Persistent=true` to catch up after sleep/hibernate

#### Scenario: Sync service runs periodically
- **GIVEN** `services.cairn-mail.enable = true`
- **AND** `services.cairn-mail.sync.enable = true` (default)
- **WHEN** the system is running
- **THEN** the sync timer triggers `cairn-mail-sync.service` every 5 minutes (default)
- **AND** the service runs as the configured `user`

#### Scenario: User customizes sync frequency
- **GIVEN** the sync service is enabled
- **WHEN** the user sets `sync.frequency = "10m"`
- **THEN** the sync timer triggers every 10 minutes instead of 5

#### Scenario: Sync delayed after boot
- **GIVEN** the sync service is enabled
- **WHEN** the system boots
- **THEN** the first sync is delayed by 2 minutes (default `onBoot`)
- **AND** subsequent syncs occur at the configured frequency

#### Scenario: User disables sync service
- **GIVEN** `services.cairn-mail.enable = true`
- **WHEN** the user sets `services.cairn-mail.sync.enable = false`
- **THEN** no sync service or timer is created
- **AND** the user can run manual syncs via CLI

#### Scenario: Catch-up sync after sleep
- **GIVEN** the sync service is enabled with `Persistent=true`
- **WHEN** the system wakes from sleep/hibernate
- **AND** a scheduled sync was missed during sleep
- **THEN** the sync service runs immediately to catch up

## REMOVED Requirements

### Requirement: Home-Manager Sync Service
**Reason**: Sync service moved to NixOS module for consistency with web service
**Migration**: Users must move `programs.cairn-mail.sync.*` options to `services.cairn-mail.sync.*`

The home-manager module SHALL NOT define:
- `systemd.user.services.cairn-mail-sync`
- `systemd.user.timers.cairn-mail-sync`
- `programs.cairn-mail.sync` option set

#### Scenario: Home-manager module without sync
- **GIVEN** a user has `programs.cairn-mail.enable = true`
- **WHEN** the home-manager configuration is evaluated
- **THEN** no sync service or timer is created at the user level
- **AND** the `sync` option is not available in `programs.cairn-mail`
