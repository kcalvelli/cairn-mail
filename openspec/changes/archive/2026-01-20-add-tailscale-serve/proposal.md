# Change: Expand NixOS Module with Tailscale Serve and Sync Service

## Why
1. **Tailscale Serve**: Users currently need to manually configure Tailscale Serve to expose cairn-mail across their tailnet. This involves writing custom systemd services with timing workarounds. Since cairn is opinionated and assumes Tailscale-centric infrastructure, this should be built-in.

2. **Sync Service Migration**: The sync service is currently in the home-manager module (user-level) while the web service is in the NixOS module (system-level). This inconsistency is confusing - both services run on behalf of the same user and read from the same config file. Consolidating both in the NixOS module simplifies the architecture.

## What Changes

### Tailscale Serve Integration
- Add `tailscaleServe` option set to the NixOS module
- Configure HTTPS port exposure via Tailscale Serve with proper service ordering
- Handle the timing race condition where `tailscale serve` fails if Tailscale isn't fully connected
- Add assertion to ensure `services.tailscale.enable` is true

### Sync Service Migration
- Add `sync` option set to the NixOS module
- Move `cairn-mail-sync.service` and `cairn-mail-sync.timer` from home-manager to NixOS
- Remove sync service/timer from home-manager module
- Both services (web + sync) now managed together at system level

## Impact
- Affected specs: `nix-modules` (new capability)
- Affected code:
  - `modules/nixos/default.nix` (add tailscaleServe + sync)
  - `modules/home-manager/default.nix` (remove sync service/timer)
- **BREAKING**: Users with `programs.cairn-mail.sync` in home-manager need to move to `services.cairn-mail.sync`

## Example Usage

```nix
# NixOS module (system-level)
services.cairn-mail = {
  enable = true;
  port = 8080;
  user = "keith";

  # Tailscale Serve integration
  tailscaleServe = {
    enable = true;
    httpsPort = 8443;  # https://hostname.tailnet:8443
  };

  # Sync service (moved from home-manager)
  sync = {
    enable = true;      # default: true
    frequency = "5m";   # default: "5m"
    onBoot = "2min";    # default: "2min"
  };
};

# Home-manager module (user-level) - unchanged
programs.cairn-mail = {
  enable = true;
  accounts = { ... };   # Still here
  ai = { ... };         # Still here
  # sync = { ... };     # REMOVED - now in NixOS module
};
```

## Migration Path
Users upgrading from previous versions:
1. Move `programs.cairn-mail.sync.*` options to `services.cairn-mail.sync.*`
2. Remove any manual Tailscale Serve systemd services
3. Add `tailscaleServe.enable = true` if exposing via Tailscale
