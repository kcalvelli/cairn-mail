# Quick Start Guide

Get cairn-mail running in about 15 minutes.

## Prerequisites

Before you begin, ensure you have:

1. **NixOS with flakes** - This app runs as a NixOS system service
2. **An OpenAI-compatible LLM endpoint** running somewhere reachable. cairn-mail talks to any `/v1/chat/completions` provider:
   - **Local:** [Ollama](https://ollama.com) (`ollama pull llama3.2` then point `ai.endpoint` at `http://localhost:11434`), [llama.cpp](https://github.com/ggerganov/llama.cpp), [vLLM](https://github.com/vllm-project/vllm)
   - **Gateway/proxy:** [LiteLLM](https://github.com/BerriAI/litellm), [openai-gateway](https://github.com/kcalvelli/openai-gateway) (default expects this on port `18789`)
   - **Hosted:** any OpenAI-compatible API
3. **A Nix flake-based configuration** (required)

## Architecture Overview

cairn-mail uses a **split architecture**:

| Module | Level | Purpose |
|--------|-------|---------|
| **NixOS module** | System | Web service, sync timer, Tailscale Serve |
| **Home-Manager module** | User | Email accounts, AI settings, config generation |

This separation allows proper service management while keeping user configuration in home-manager.

## Step 1: Add to Your Flake

Add cairn-mail to your `flake.nix`:

```nix
{
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    home-manager.url = "github:nix-community/home-manager";
    cairn-mail.url = "github:kcalvelli/cairn-mail";
  };

  outputs = { self, nixpkgs, home-manager, cairn-mail, ... }: {
    nixosConfigurations.yourhostname = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [
        # 1. Apply overlay (adds pkgs.cairn-mail)
        { nixpkgs.overlays = [ cairn-mail.overlays.default ]; }

        # 2. Import NixOS module for system services
        cairn-mail.nixosModules.default

        # 3. Your NixOS configuration
        ./configuration.nix

        # 4. Home-manager integration
        home-manager.nixosModules.home-manager
        {
          home-manager.users.youruser = { ... }: {
            imports = [ cairn-mail.homeManagerModules.default ];
            # User config goes here (see Step 2)
          };
        }
      ];
    };
  };
}
```

## Step 2: NixOS Configuration (System Services)

In your NixOS configuration (e.g., `configuration.nix`), enable the services:

```nix
{ config, ... }:
{
  # Enable cairn-mail system services
  services.cairn-mail = {
    enable = true;
    port = 8080;
    user = "youruser";  # User whose config to read

    # Sync timer (runs periodically)
    sync = {
      enable = true;      # Default: true
      frequency = "5m";   # Default: "5m"
      onBoot = "2min";    # Default: "2min"
    };

    # Optional: Expose via Tailscale (requires services.tailscale.enable)
    # tailscaleServe = {
    #   enable = true;
    #   httpsPort = 8443;  # Access at https://hostname.tailnet:8443
    # };
  };
}
```

## Step 3: Home-Manager Configuration (User Settings)

In your home-manager configuration, set up accounts and AI settings:

```nix
{ config, ... }:
{
  programs.cairn-mail = {
    enable = true;

    # AI settings — any OpenAI-compatible /v1/chat/completions endpoint works.
    # Defaults shown below; swap in your local Ollama / llama.cpp / hosted endpoint.
    ai = {
      enable = true;
      model = "claude-sonnet-4-20250514";
      endpoint = "http://localhost:18789";
      # For local Ollama instead:
      #   model = "llama3.2";
      #   endpoint = "http://localhost:11434";
    };

    # Email accounts (see Step 4 for setup)
    accounts.personal = {
      provider = "gmail";
      email = "you@gmail.com";
      realName = "Your Name";
      oauthTokenFile = config.age.secrets.gmail-token.path;
    };
  };
}
```

## Step 4: Set Up Email Account

Choose your email provider:

### Option A: Gmail (OAuth2)

Gmail requires OAuth2 authentication. You'll need to create credentials in Google Cloud Console.

**Creating Google Cloud Credentials:**

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project named `cairn-mail`
3. Enable the **Gmail API**
4. Go to **OAuth consent screen** -> Configure as "External"
5. Go to **Credentials** -> Create **OAuth client ID**
   - Application type: **Desktop app**
   - Download the JSON file

**Encrypt the token (Cairn/agenix users):**

```bash
# Add to secrets.nix
cd ~/.config/nixos_config/secrets
echo '"gmail-personal.age".publicKeys = users ++ systems;' >> secrets.nix

# Encrypt the credentials JSON
agenix -e gmail-personal.age
# Paste your OAuth token JSON, save and exit

# Stage for git
git add gmail-personal.age
```

**Add to Nix config:**

```nix
# In your NixOS config
age.secrets.gmail-personal.file = ./secrets/gmail-personal.age;

# In your home-manager config
programs.cairn-mail.accounts.personal = {
  provider = "gmail";
  email = "you@gmail.com";
  realName = "Your Name";
  oauthTokenFile = config.age.secrets.gmail-personal.path;
};
```

### Option B: IMAP (Password-based)

For Fastmail, ProtonMail Bridge, or other IMAP servers:

**Using agenix (recommended):**

```bash
cd ~/.config/nixos_config/secrets
agenix -e fastmail-password.age
# Enter your password, save and exit
git add fastmail-password.age
```

**Add to Nix config:**

```nix
# In your NixOS config
age.secrets.fastmail-password.file = ./secrets/fastmail-password.age;

# In your home-manager config
programs.cairn-mail.accounts.work = {
  provider = "imap";
  email = "you@fastmail.com";
  realName = "Your Name";
  passwordFile = config.age.secrets.fastmail-password.path;

  imap = {
    host = "imap.fastmail.com";
    port = 993;
    tls = true;
  };

  smtp = {
    host = "smtp.fastmail.com";
    port = 465;
    tls = true;
  };
};
```

## Step 5: Rebuild and Verify

```bash
# Rebuild NixOS
sudo nixos-rebuild switch --flake .

# Check service status
systemctl status cairn-mail-web.service
systemctl status cairn-mail-sync.timer

# View logs
sudo journalctl -u cairn-mail-web.service -f
```

## Step 6: Access the Web UI

Open http://localhost:8080 in your browser.

You should see:
- Your messages in the inbox
- AI-assigned tags on each message
- Sidebar with tag filtering

![Desktop View](screenshots/desktop-dark-split-pane.png)

## Step 7: Install as PWA (Optional)

For a native app experience:

1. Open http://localhost:8080 in Chrome/Brave
2. Click the install icon in the address bar
3. Click "Install"

The app will appear in your application launcher.

## Common IMAP Server Settings

| Provider | IMAP Host | IMAP Port | SMTP Host | SMTP Port |
|----------|-----------|-----------|-----------|-----------|
| Fastmail | imap.fastmail.com | 993 | smtp.fastmail.com | 465 |
| ProtonMail | 127.0.0.1 | 1143 | 127.0.0.1 | 1025 |
| iCloud | imap.mail.me.com | 993 | smtp.mail.me.com | 587 |
| Outlook | outlook.office365.com | 993 | smtp.office365.com | 587 |
| Yahoo | imap.mail.yahoo.com | 993 | smtp.mail.yahoo.com | 465 |

> **Note:** ProtonMail requires the ProtonMail Bridge app running locally.

## Service Management

cairn-mail runs as **system-level systemd services**:

```bash
# Check service status
systemctl status cairn-mail-web.service
systemctl status cairn-mail-sync.timer
systemctl status cairn-mail-tailscale-serve.service  # if enabled

# Restart web service
sudo systemctl restart cairn-mail-web.service

# Trigger sync manually (instead of waiting for timer)
sudo systemctl start cairn-mail-sync.service

# View web service logs
sudo journalctl -u cairn-mail-web.service -f

# View sync service logs
sudo journalctl -u cairn-mail-sync.service -f
```

## Troubleshooting

### "Connection refused" on web UI

Ensure the web service is running:
```bash
systemctl status cairn-mail-web.service
```

### AI classification not working

Confirm your configured endpoint is reachable and serves an OpenAI-compatible API:

```bash
# Replace with your configured ai.endpoint
curl -s http://localhost:18789/v1/models | head

# If using local Ollama, confirm the model is pulled:
ollama list

# Tail the sync service logs — classifier errors surface here
sudo journalctl -u cairn-mail-sync.service -n 50
```

Empty responses or 404s usually mean the endpoint isn't OpenAI-compatible. Connection refused means nothing's listening on the port you configured in `ai.endpoint`.

### Messages not syncing

Check sync service logs:
```bash
sudo journalctl -u cairn-mail-sync.service -n 50
```

Trigger a manual sync:
```bash
sudo systemctl start cairn-mail-sync.service
```

### OAuth token expired (Gmail)

Re-encrypt a fresh token and rebuild:
```bash
cd ~/.config/nixos_config/secrets
agenix -e gmail-personal.age
# Paste new token, save
sudo nixos-rebuild switch --flake .
```

## Next Steps

- **[User Guide](USER_GUIDE.md)** - Learn all features
- **[Configuration Reference](CONFIGURATION.md)** - Customize AI, tags, and more
- **[Architecture](ARCHITECTURE.md)** - Understand how it works

## Full Example Configuration

Here's a complete multi-account setup:

```nix
# flake.nix
{
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    home-manager.url = "github:nix-community/home-manager";
    cairn-mail.url = "github:kcalvelli/cairn-mail";
    agenix.url = "github:ryantm/agenix";
  };

  outputs = { nixpkgs, home-manager, cairn-mail, agenix, ... }: {
    nixosConfigurations.myhost = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [
        # Overlays
        { nixpkgs.overlays = [ cairn-mail.overlays.default ]; }

        # Modules
        agenix.nixosModules.default
        cairn-mail.nixosModules.default

        # NixOS config
        ({ config, ... }: {
          # Secrets
          age.secrets.gmail-token.file = ./secrets/gmail-token.age;
          age.secrets.fastmail-password.file = ./secrets/fastmail-password.age;

          # cairn-mail system services
          services.cairn-mail = {
            enable = true;
            port = 8080;
            user = "keith";

            sync = {
              enable = true;
              frequency = "5m";
              onBoot = "2min";
            };

            # Optional: Tailscale Serve
            # tailscaleServe = {
            #   enable = true;
            #   httpsPort = 8443;
            # };
          };
        })

        # Home-manager
        home-manager.nixosModules.home-manager
        {
          home-manager.users.keith = { config, ... }: {
            imports = [ cairn-mail.homeManagerModules.default ];

            programs.cairn-mail = {
              enable = true;

              ai = {
                enable = true;
                model = "claude-sonnet-4-20250514";       # Default
                endpoint = "http://localhost:18789";      # Default (openai-gateway)
                temperature = 0.3;
                useDefaultTags = true;

                # Add custom tags
                tags = [
                  { name = "clients"; description = "Client communications"; }
                  { name = "reports"; description = "Weekly/monthly reports"; }
                ];

                labelColors = {
                  urgent = "red";
                  work = "blue";
                  finance = "green";
                  personal = "purple";
                };
              };

              # Gmail account
              accounts.gmail = {
                provider = "gmail";
                email = "you@gmail.com";
                realName = "Your Name";
                oauthTokenFile = config.age.secrets.gmail-token.path;
              };

              # Fastmail account
              accounts.fastmail = {
                provider = "imap";
                email = "you@fastmail.com";
                realName = "Your Name";
                passwordFile = config.age.secrets.fastmail-password.path;

                imap = {
                  host = "imap.fastmail.com";
                  port = 993;
                  tls = true;
                };

                smtp = {
                  host = "smtp.fastmail.com";
                  port = 465;
                  tls = true;
                };
              };
            };
          };
        }
      ];
    };
  };
}
```
