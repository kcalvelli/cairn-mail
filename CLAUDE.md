# Deployment Workflow

**IMPORTANT: Do NOT manually start the application with `./result/bin/cairn-mail` or `nix build` commands!**

This project runs as **system-level systemd services** managed by the NixOS module. The correct workflow is:

## After making changes:

1. Commit and push to GitHub:
   ```bash
   git add -A && git commit -m "message" && git push
   ```

2. Update the flake and rebuild NixOS (run from `~/.config/nixos_config`):
   ```bash
   cd ~/.config/nixos_config && nix flake update cairn-mail && sudo nixos-rebuild switch --flake .
   ```

3. The systemd service will restart automatically if the package changed.

## Service management:

```bash
# Check service status
systemctl status cairn-mail-web.service
systemctl status cairn-mail-sync.timer
systemctl status cairn-mail-tailscale-serve.service  # if enabled

# Restart web service manually if needed
sudo systemctl restart cairn-mail-web.service

# Trigger a sync manually (instead of waiting for timer)
sudo systemctl start cairn-mail-sync.service

# View web service logs
sudo journalctl -u cairn-mail-web.service -f

# View sync service logs (where pending operations are processed)
sudo journalctl -u cairn-mail-sync.service -f

# Check Tailscale Serve status
tailscale serve status
```

## Why not manual execution?

- Manual execution bypasses systemd and won't pick up changes on rebuild
- Creates confusion with multiple instances from different Nix store paths
- Loses systemd's restart-on-failure and logging benefits

# NixOS/Home-Manager Integration

Split architecture for proper Nix dependency tracking:
- **NixOS module**: System services (web, sync timer, tailscale-serve)
- **Home-manager module**: User config only (accounts, AI settings, generates config.yaml)

## Usage in your NixOS flake:

```nix
{
  inputs.cairn-mail.url = "github:kcalvelli/cairn-mail";

  outputs = { nixpkgs, cairn-mail, ... }: {
    nixosConfigurations.myhost = nixpkgs.lib.nixosSystem {
      modules = [
        # 1. Apply overlay (adds pkgs.cairn-mail)
        { nixpkgs.overlays = [ cairn-mail.overlays.default ]; }

        # 2. Import NixOS module for web service
        cairn-mail.nixosModules.default

        # 3. Enable the service
        {
          services.cairn-mail = {
            enable = true;
            port = 8080;
            user = "keith";  # Reads config from this user's home

            # Optional: Expose via Tailscale (requires services.tailscale.enable)
            tailscaleServe = {
              enable = true;
              httpsPort = 8443;  # Access at https://hostname.tailnet:8443
            };

            # Optional: Configure sync timer (defaults shown)
            sync = {
              enable = true;
              frequency = "5m";   # How often to sync
              onBoot = "2min";    # Delay after boot before first sync
            };
          };
        }

        # 4. Home-manager for user config (accounts, AI settings)
        {
          home-manager.users.keith = { ... }: {
            imports = [ cairn-mail.homeManagerModules.default ];

            programs.cairn-mail = {
              enable = true;
              accounts.gmail = {
                provider = "gmail";
                email = "user@gmail.com";
                oauthTokenFile = "/run/agenix/gmail-token";
              };
              ai.model = "mistral";
            };
          };
        }
      ];
    };
  };
}
```

## Key Points:

1. **Overlay required**: Adds `pkgs.cairn-mail` - proper dependency tracking
2. **NixOS module**: System services (web, sync timer, optional tailscale-serve)
3. **Home-manager module**: User-specific config only (accounts, AI settings)
4. **Tailscale Serve**: Optional HTTPS exposure across your tailnet (no port forwarding needed)
5. **Sync timer**: Runs in background, configurable frequency