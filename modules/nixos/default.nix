# NixOS module for cairn-mail
# Provides the package via overlay and runs system-level services:
# - Web UI service
# - Sync service and timer
# - Optional Tailscale Serve integration
{ config, lib, pkgs, ... }:

with lib;

let
  cfg = config.services.cairn-mail;
in {
  options.services.cairn-mail = {
    enable = mkEnableOption "cairn-mail web service";

    package = mkOption {
      type = types.package;
      default = pkgs.cairn-mail;
      defaultText = literalExpression "pkgs.cairn-mail";
      description = "The cairn-mail package to use.";
    };

    port = mkOption {
      type = types.port;
      default = 8080;
      description = "Port for the web UI.";
    };

    user = mkOption {
      type = types.str;
      description = "User to run the service as. Config is read from this user's home.";
    };

    group = mkOption {
      type = types.str;
      default = "users";
      description = "Group to run the service as.";
    };

    openFirewall = mkOption {
      type = types.bool;
      default = false;
      description = "Open firewall port for the web UI.";
    };

    # Tailscale Serve integration
    tailscaleServe = {
      enable = mkEnableOption "Tailscale Serve to expose cairn-mail across your tailnet";

      httpsPort = mkOption {
        type = types.port;
        default = 8443;
        description = ''
          HTTPS port to expose on your tailnet.
          The service will be available at https://{hostname}.{tailnet}:{httpsPort}
        '';
        example = 443;
      };
    };

    # Sync service configuration
    sync = {
      enable = mkOption {
        type = types.bool;
        default = true;
        description = "Enable periodic email sync service.";
      };

      frequency = mkOption {
        type = types.str;
        default = "5m";
        description = "How often to sync emails (systemd timer format).";
        example = "10m";
      };

      onBoot = mkOption {
        type = types.str;
        default = "2min";
        description = "Delay before first sync after boot (systemd timer format).";
        example = "5min";
      };
    };
  };

  config = mkIf cfg.enable {
    # Assertion: Tailscale must be enabled if tailscaleServe is enabled
    assertions = [
      {
        assertion = cfg.tailscaleServe.enable -> config.services.tailscale.enable;
        message = "cairn-mail: tailscaleServe requires services.tailscale.enable = true";
      }
    ];

    # System service for the web UI
    systemd.services.cairn-mail-web = {
      description = "cairn-mail web UI";
      after = [ "network-online.target" ];
      wants = [ "network-online.target" ];
      wantedBy = [ "multi-user.target" ];

      serviceConfig = {
        Type = "simple";
        User = cfg.user;
        Group = cfg.group;
        ExecStart = "${cfg.package}/bin/cairn-mail web --port ${toString cfg.port}";
        Restart = "on-failure";
        RestartSec = "5s";

        # Read config from user's home
        Environment = [
          "PYTHONUNBUFFERED=1"
          "HOME=/home/${cfg.user}"
        ];

        # Hardening
        NoNewPrivileges = true;
        ProtectSystem = "strict";
        ProtectHome = "read-only";
        ReadWritePaths = [
          "/home/${cfg.user}/.local/share/cairn-mail"
        ];
        PrivateTmp = true;
      };
    };

    # Sync service: fetches new emails and runs AI classification
    systemd.services.cairn-mail-sync = mkIf cfg.sync.enable {
      description = "cairn-mail sync service";
      after = [ "network-online.target" ];
      wants = [ "network-online.target" ];

      serviceConfig = {
        Type = "oneshot";
        User = cfg.user;
        Group = cfg.group;
        ExecStart = "${cfg.package}/bin/cairn-mail sync run";

        # Read config from user's home
        Environment = [
          "PYTHONUNBUFFERED=1"
          "HOME=/home/${cfg.user}"
        ];

        # Hardening (same as web service)
        NoNewPrivileges = true;
        ProtectSystem = "strict";
        ProtectHome = "read-only";
        ReadWritePaths = [
          "/home/${cfg.user}/.local/share/cairn-mail"
        ];
        PrivateTmp = true;
      };
    };

    # Sync timer: triggers sync service periodically
    systemd.timers.cairn-mail-sync = mkIf cfg.sync.enable {
      description = "cairn-mail sync timer";
      wantedBy = [ "timers.target" ];

      timerConfig = {
        OnBootSec = cfg.sync.onBoot;
        OnUnitActiveSec = cfg.sync.frequency;
        Unit = "cairn-mail-sync.service";
        Persistent = true;  # Catch up after sleep/hibernate
      };
    };

    # Tailscale Serve service: exposes web UI across tailnet via HTTPS
    systemd.services.cairn-mail-tailscale-serve = mkIf cfg.tailscaleServe.enable {
      description = "cairn-mail Tailscale Serve (HTTPS proxy)";
      after = [ "network-online.target" "tailscaled.service" "cairn-mail-web.service" ];
      wants = [ "network-online.target" "tailscaled.service" ];
      requires = [ "cairn-mail-web.service" ];
      wantedBy = [ "multi-user.target" ];

      # Wait for Tailscale to be fully connected before starting serve
      script = ''
        # Wait up to 60 seconds for Tailscale to be connected
        for i in $(seq 1 60); do
          if ${pkgs.tailscale}/bin/tailscale status --json 2>/dev/null | ${pkgs.jq}/bin/jq -e '.BackendState == "Running"' >/dev/null 2>&1; then
            echo "Tailscale is connected, starting serve..."
            exec ${pkgs.tailscale}/bin/tailscale serve --bg --https=${toString cfg.tailscaleServe.httpsPort} ${toString cfg.port}
          fi
          echo "Waiting for Tailscale to connect... ($i/60)"
          sleep 1
        done
        echo "Tailscale did not connect within 60 seconds"
        exit 1
      '';

      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        # Clean up serve config on stop to prevent stale mappings
        ExecStop = "${pkgs.tailscale}/bin/tailscale serve --https=${toString cfg.tailscaleServe.httpsPort} off";
      };
    };

    # Firewall
    networking.firewall.allowedTCPPorts = mkIf cfg.openFirewall [ cfg.port ];
  };
}
