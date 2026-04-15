# Home Manager Module Update - TODO

The existing `modules/home-manager/default.nix` needs to be updated for the v2 API-based architecture.

## Changes Needed

### 1. Account Configuration Schema

Update account options to support the new provider types:

```nix
programs.cairn-mail.accounts.<name> = {
  provider = "gmail" | "imap" | "outlook";  # NEW: explicit provider
  email = "...";
  realName = "...";

  # OAuth2 accounts (Gmail, Outlook)
  oauthTokenFile = "...";  # NEW: path to OAuth token

  # IMAP accounts (password-based)
  passwordFile = "...";    # NEW: path to IMAP password
  imap = { ... };          # KEEP: IMAP settings
  smtp = { ... };          # KEEP: SMTP settings (for sending)

  # Sync settings
  sync = {
    frequency = "5m";      # NEW: sync interval
    enableWebhooks = false;  # NEW: real-time notifications
  };

  # Label/tag settings
  labels = {
    prefix = "AI";         # NEW: label prefix (AI/Work, AI/Finance)
    colors = { ... };      # NEW: label colors (Gmail)
  };
};
```

### 2. AI Configuration

```nix
programs.cairn-mail.ai = {
  enable = true;
  model = "llama3.2";
  endpoint = "http://localhost:11434";
  temperature = 0.3;

  # Custom tag taxonomy (optional)
  tags = [
    { name = "work"; description = "..."; }
    { name = "finance"; description = "..."; }
  ];
};
```

### 3. UI Configuration

```nix
programs.cairn-mail.ui = "web";  # or "cli" for headless
programs.cairn-mail.webPort = 8080;
```

### 4. Service Generation

Generate systemd services:

```nix
systemd.user.services.cairn-mail = {
  description = "cairn-mail backend server";
  after = [ "network.target" ];
  wantedBy = [ "default.target" ];

  serviceConfig = {
    ExecStart = "${pkgs.cairn-mail}/bin/cairn-mail ...";
    Restart = "on-failure";

    # If using systemd-creds
    LoadCredential = [
      "gmail-oauth:/path/to/oauth-token"
    ];
  };
};

systemd.user.timers.cairn-mail-sync = {
  description = "Periodic email sync";
  wantedBy = [ "timers.target" ];

  timerConfig = {
    OnBootSec = "1m";
    OnUnitActiveSec = cfg.sync.frequency;
  };
};
```

### 5. Build-Time Validation

Add assertions to validate configuration at build time:

```nix
assertions = [
  {
    assertion = cfg.accounts != {};
    message = "At least one account must be configured";
  }
  {
    assertion = all (account:
      (account.provider == "gmail" || account.provider == "outlook") -> account.oauthTokenFile != null
    ) (attrValues cfg.accounts);
    message = "OAuth providers require oauthTokenFile";
  }
  {
    assertion = all (account:
      account.provider == "imap" -> (account.passwordFile != null && account.imap.host != "")
    ) (attrValues cfg.accounts);
    message = "IMAP providers require passwordFile and imap.host";
  }
];
```

### 6. Runtime Configuration Generation

Generate runtime config file that the Python application reads:

```nix
xdg.configFile."cairn-mail/config.yaml".text = lib.generators.toYAML {} {
  accounts = mapAttrs (name: account: {
    id = name;
    provider = account.provider;
    email = account.email;
    credential_file = account.oauthTokenFile or account.passwordFile;
    settings = {
      label_prefix = account.labels.prefix or "AI";
      sync_frequency = account.sync.frequency or "5m";
      ai_model = cfg.ai.model;
      ai_endpoint = cfg.ai.endpoint;
    };
  }) cfg.accounts;

  database_path = "${config.xdg.dataHome}/cairn-mail/mail.db";
};
```

### 7. Database Location

Store database in XDG data home:

```nix
home.file."${config.xdg.dataHome}/cairn-mail/.keep".text = "";
```

## Implementation Priority

1. **Basic account schema** - Get Gmail OAuth working
2. **Service generation** - Systemd units for sync
3. **IMAP support** - Password-based accounts
4. **Build-time validation** - Catch config errors early
5. **Secrets integration** - sops-nix/agenix examples

## Testing

```bash
# Build and test module
home-manager build

# Check generated config
cat ~/.config/cairn-mail/config.yaml

# Check systemd units
systemctl --user list-units | grep cairn

# Manual test
cairn-mail status
cairn-mail sync run
```
