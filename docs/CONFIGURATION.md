# Configuration Reference

Complete reference for all cairn-mail Nix configuration options.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [NixOS Module (System Services)](#nixos-module-system-services)
  - [Basic Options](#basic-options)
  - [Sync Timer](#sync-timer)
  - [Tailscale Serve](#tailscale-serve)
- [Home-Manager Module (User Config)](#home-manager-module-user-config)
  - [Account Configuration](#account-configuration)
  - [AI Configuration](#ai-configuration)
  - [Sync Settings](#sync-settings)
  - [Gateway & Action Tags](#gateway--action-tags)
- [AI Model Recommendations](#ai-model-recommendations)
- [Custom Tags](#custom-tags)
- [Example Configurations](#example-configurations)

---

## Architecture Overview

cairn-mail uses a **split architecture** with two separate Nix modules:

| Module | Namespace | Level | Purpose |
|--------|-----------|-------|---------|
| **NixOS** | `services.cairn-mail` | System | Web service, sync timer, Tailscale Serve |
| **Home-Manager** | `programs.cairn-mail` | User | Email accounts, AI settings, config file |

**Why split?**
- System services need root to bind ports and run reliably
- User config (accounts, AI preferences) belongs in home-manager
- Proper Nix dependency tracking via overlay

**Required components:**
1. **Overlay** - Adds `pkgs.cairn-mail` to nixpkgs
2. **NixOS module** - Runs systemd services
3. **Home-Manager module** - Generates user config file

---

## NixOS Module (System Services)

Namespace: `services.cairn-mail`

### Basic Options

```nix
services.cairn-mail = {
  enable = true;
  package = pkgs.cairn-mail;  # Default from overlay
  port = 8080;
  user = "youruser";
  group = "users";
  openFirewall = false;
};
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enable` | boolean | `false` | Enable cairn-mail services |
| `package` | package | `pkgs.cairn-mail` | Package to use |
| `port` | port | `8080` | Web UI port |
| `user` | string | *required* | User to run as (reads config from their home) |
| `group` | string | `"users"` | Group to run as |
| `openFirewall` | boolean | `false` | Open firewall port for web UI |

### Sync Timer

Configures the periodic email sync service.

```nix
services.cairn-mail.sync = {
  enable = true;       # Default: true
  frequency = "5m";    # Default: "5m"
  onBoot = "2min";     # Default: "2min"
};
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enable` | boolean | `true` | Enable periodic sync |
| `frequency` | string | `"5m"` | Sync interval (systemd timer format) |
| `onBoot` | string | `"2min"` | Delay before first sync after boot |

**Frequency format** (systemd timer):
- `5m` - Every 5 minutes
- `1h` - Every hour
- `30s` - Every 30 seconds
- `1d` - Daily

**Systemd units created:**
- `cairn-mail-sync.service` - Oneshot sync job
- `cairn-mail-sync.timer` - Periodic trigger

### Tailscale Serve

Exposes the web UI across your Tailscale network via HTTPS.

```nix
services.cairn-mail.tailscaleServe = {
  enable = true;
  httpsPort = 8443;  # Access at https://hostname.tailnet:8443
};
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enable` | boolean | `false` | Enable Tailscale Serve |
| `httpsPort` | port | `8443` | HTTPS port on your tailnet |

**Requirements:**
- `services.tailscale.enable = true` must be set
- Tailscale must be connected before service starts (handled automatically)

**Access URL:** `https://{machine-name}.{tailnet-name}:{httpsPort}`

Example: `https://myserver.tail12345.ts.net:8443`

---

## Home-Manager Module (User Config)

Namespace: `programs.cairn-mail`

### Quick Reference

```nix
programs.cairn-mail = {
  enable = true;

  accounts = { };    # Email accounts (see below)
  ai = { };          # AI classification settings
  sync = { };        # Sync behavior settings
};
```

### Account Configuration

#### Gmail (OAuth2)

```nix
accounts.personal = {
  provider = "gmail";
  email = "you@gmail.com";
  realName = "Your Name";
  oauthTokenFile = config.age.secrets.gmail-token.path;

  # Optional per-account settings
  labels = {
    prefix = "AI";           # Label prefix (default: "AI")
    colors = { };            # Color overrides
  };

  sync = {
    enableWebhooks = false;  # Gmail push notifications (experimental)
  };
};
```

#### IMAP (Password)

```nix
accounts.work = {
  provider = "imap";
  email = "you@fastmail.com";
  realName = "Your Name";
  passwordFile = config.age.secrets.fastmail-password.path;

  imap = {
    host = "imap.fastmail.com";
    port = 993;              # Default: 993
    tls = true;              # Default: true
  };

  smtp = {
    host = "smtp.fastmail.com";
    port = 465;              # Default: 465
    tls = true;              # Default: true
  };
};
```

#### Account Options Reference

| Option | Type | Required | Description |
|--------|------|----------|-------------|
| `provider` | `"gmail"` \| `"imap"` \| `"outlook"` | Yes | Provider type |
| `email` | string | Yes | Email address |
| `realName` | string | No | Display name for sent mail |
| `oauthTokenFile` | path | Gmail/Outlook | OAuth token file path |
| `passwordFile` | path | IMAP | Password file path |
| `imap` | submodule | IMAP | IMAP server settings |
| `smtp` | submodule | No | SMTP server settings (for sending) |
| `labels.prefix` | string | No | AI label prefix (default: "AI") |
| `labels.colors` | attrset | No | Per-account color overrides |
| `sync.enableWebhooks` | boolean | No | Enable push notifications |
| `hidden` | boolean | No | Hide account from default UI views (default: `false`) |

#### Hidden Accounts

Set `hidden = true` to keep an account out of the default web UI without disabling it. The account still syncs on schedule and is fully accessible via the MCP server, but it's excluded from `GET /accounts` and `GET /messages` unless the caller explicitly opts in (`include_hidden=true` or an explicit `account_id` filter).

This is useful for agent/bot accounts you don't want cluttering your inbox view:

```nix
accounts.bot = {
  provider = "imap";
  email = "ci-alerts@example.com";
  passwordFile = config.age.secrets.bot-password.path;
  hidden = true;            # Stays out of the UI; MCP/agents still see it
  imap = { host = "..."; port = 993; tls = true; };
};
```

### AI Configuration

cairn-mail talks to any **OpenAI-compatible `/v1/chat/completions` endpoint**. The defaults below assume an [openai-gateway](https://github.com/kcalvelli/openai-gateway) on `localhost:18789`, but Ollama, llama.cpp, vLLM, LiteLLM, or a hosted API all work the same way.

```nix
ai = {
  enable = true;                              # Default: true
  model = "claude-sonnet-4-20250514";         # Any model the endpoint exposes
  endpoint = "http://localhost:18789";        # Any OpenAI-compatible /v1 endpoint
  temperature = 0.3;                          # LLM temperature (0.0-1.0)

  # Tag taxonomy
  useDefaultTags = true;                      # Use built-in 35-tag taxonomy
  tags = [];                                  # Additional custom tags
  excludeTags = [];                           # Tags to remove from defaults

  # Label styling
  labelPrefix = "AI";                         # Prefix for provider labels
  labelColors = {};                           # Tag color overrides
};
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enable` | boolean | `true` | Enable AI classification |
| `model` | string | `"claude-sonnet-4-20250514"` | Model name your endpoint exposes |
| `endpoint` | string | `"http://localhost:18789"` | OpenAI-compatible API base URL |
| `temperature` | float | `0.3` | LLM temperature (0.0-1.0) |
| `useDefaultTags` | boolean | `true` | Use built-in tag taxonomy |
| `tags` | list | `[]` | Additional custom tags |
| `excludeTags` | list | `[]` | Tags to exclude from defaults |
| `labelPrefix` | string | `"AI"` | Prefix for provider labels |
| `labelColors` | attrset | `{}` | Tag color overrides |

**Pointing at local Ollama instead:**

```nix
ai = {
  model = "llama3.2";
  endpoint = "http://localhost:11434";
};
```

**Temperature guidelines:**
- `0.1-0.3` - Highly deterministic, best for classification
- `0.4-0.6` - More varied responses
- `0.7+` - Not recommended for classification

### Sync Settings

```nix
sync = {
  maxMessagesPerSync = 100;  # Max messages per batch
  enableWebhooks = false;    # Real-time push (experimental)
};
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `maxMessagesPerSync` | integer | `100` | Max messages per sync batch |
| `enableWebhooks` | boolean | `false` | Enable real-time webhooks |

> **Note:** Sync *timing* (`frequency`, `onBoot`) is configured in the NixOS module, not here.

### Gateway & Action Tags

Action tags let you trigger real-world actions from emails (create contacts, calendar events, etc.) via [mcp-gateway](https://github.com/kcalvelli/mcp-gateway) and [cairn-dav](https://github.com/kcalvelli/cairn-dav). See the full [Action Tags Guide](ACTION_TAGS.md) for setup and usage.

```nix
gateway = {
  enable = true;
  url = "http://localhost:8085";
  addressbook = "google/default";
  calendar = "kc.calvelli@gmail.com";
};
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `gateway.enable` | boolean | `false` | Enable action tag processing via mcp-gateway |
| `gateway.url` | string | `"http://localhost:8085"` | mcp-gateway REST API URL |
| `gateway.addressbook` | string | *required*\* | vdirsyncer addressbook name for `add-contact` |
| `gateway.calendar` | string | *required*\* | vdirsyncer calendar name for `create-reminder` |

\* Required when `gateway.enable = true`.

```nix
# Optional: override built-in actions or add custom ones
actions = {
  "save-receipt" = {
    description = "Save receipt to expense tracker";
    server = "expenses";
    tool = "add_expense";
    defaultArgs = { currency = "USD"; };
  };
};
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `actions.<name>.description` | string | `""` | Human-readable description |
| `actions.<name>.server` | string | *required* | MCP server ID in mcp-gateway |
| `actions.<name>.tool` | string | *required* | MCP tool name to call |
| `actions.<name>.extractionPrompt` | string or null | `null` | Custom LLM extraction prompt (uses `ai.endpoint`) |
| `actions.<name>.defaultArgs` | attrset | `{}` | Static arguments for the tool |
| `actions.<name>.enabled` | boolean | `true` | Enable/disable this action |

---

## AI Model Recommendations

cairn-mail's classification job is small: a few hundred tokens of prompt, a JSON object back. Almost any modern instruction-tuned model handles it. Pick whatever your endpoint exposes; the defaults are tuned conservatively (`temperature = 0.3`).

### Local Models (Ollama)

If you're running Ollama locally, these are reasonable starting points:

| Use Case | Model | VRAM | Notes |
|----------|-------|------|-------|
| **Balanced** | `llama3.2` | 4GB | Solid default for tagging |
| **Low VRAM** | `qwen2.5:3b` | 2GB | Faster, slightly less accurate |
| **CPU-only / fastest** | `qwen2.5:1.5b` | <2GB | Works without a GPU |
| **Maximum quality** | `llama3.1:8b` | 8GB | Diminishing returns for tagging |

### Hosted / Gateway Models

When routing through a gateway (LiteLLM, openai-gateway, etc.), pick whatever your provider exposes. Anthropic Claude Sonnet 4, OpenAI GPT-4-class, and Mistral all work. Choose based on cost-per-message and latency rather than raw quality — classification rarely needs the largest model.

---

## Custom Tags

### Default Tag Taxonomy

When `useDefaultTags = true` (default), you get 35 tags across these categories:

| Category | Tags |
|----------|------|
| **Priority** | `urgent`, `important`, `review` |
| **Work** | `work`, `project`, `meeting`, `deadline` |
| **Personal** | `personal`, `family`, `friends`, `hobby` |
| **Finance** | `finance`, `invoice`, `payment`, `expense` |
| **Shopping** | `shopping`, `receipt`, `shipping` |
| **Travel** | `travel`, `booking`, `itinerary`, `flight` |
| **Developer** | `dev`, `github`, `ci`, `alert` |
| **Marketing** | `marketing`, `newsletter`, `promotion`, `announcement` |
| **Social** | `social`, `notification`, `update`, `reminder` |
| **System** | `junk` |

### Adding Custom Tags

Extend the defaults with your own tags:

```nix
ai = {
  useDefaultTags = true;  # Keep defaults
  tags = [
    { name = "clients"; description = "Client communications and support"; }
    { name = "reports"; description = "Weekly and monthly reports"; }
    { name = "urgent-client"; description = "Time-sensitive client issues"; }
  ];
};
```

### Excluding Default Tags

Remove tags you don't want:

```nix
ai = {
  useDefaultTags = true;
  excludeTags = [ "social" "newsletter" "hobby" ];
};
```

### Replacing All Tags

Use only your custom taxonomy:

```nix
ai = {
  useDefaultTags = false;
  tags = [
    { name = "work"; description = "Work-related emails"; }
    { name = "personal"; description = "Personal correspondence"; }
    { name = "bills"; description = "Bills and payments"; }
    { name = "junk"; description = "Promotional and marketing"; }
  ];
};
```

### Label Colors

Override colors for specific tags:

```nix
ai.labelColors = {
  urgent = "red";
  important = "red";
  work = "blue";
  finance = "green";
  personal = "purple";
  shopping = "yellow";
  travel = "magenta";
  dev = "cyan";
  newsletter = "gray";
  junk = "brown";
};
```

**Gmail color options:** `red`, `orange`, `yellow`, `green`, `teal`, `blue`, `purple`, `gray`, `brown`, `pink`

> **Note:** Default tags already have sensible category-based colors. Override only if needed.

---

## Example Configurations

### Minimal Setup

```nix
# NixOS module
services.cairn-mail = {
  enable = true;
  port = 8080;
  user = "keith";
};

# Home-manager module
programs.cairn-mail = {
  enable = true;

  accounts.gmail = {
    provider = "gmail";
    email = "you@gmail.com";
    oauthTokenFile = config.age.secrets.gmail.path;
  };
};
```

### Full Production Setup

```nix
# NixOS module
services.cairn-mail = {
  enable = true;
  port = 8080;
  user = "keith";

  sync = {
    enable = true;
    frequency = "5m";
    onBoot = "2min";
  };

  tailscaleServe = {
    enable = true;
    httpsPort = 8443;
  };
};

# Home-manager module
programs.cairn-mail = {
  enable = true;

  ai = {
    enable = true;
    model = "claude-sonnet-4-20250514";
    endpoint = "http://localhost:18789";
    temperature = 0.3;
    useDefaultTags = true;

    tags = [
      { name = "clients"; description = "Client communications"; }
      { name = "invoices"; description = "Invoices to process"; }
    ];

    labelColors = {
      urgent = "red";
      important = "red";
      work = "blue";
      finance = "green";
      clients = "blue";
      invoices = "green";
    };
  };

  sync = {
    maxMessagesPerSync = 100;
  };

  accounts.gmail = {
    provider = "gmail";
    email = "personal@gmail.com";
    realName = "Your Name";
    oauthTokenFile = config.age.secrets.gmail-token.path;
  };

  accounts.work = {
    provider = "imap";
    email = "work@fastmail.com";
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
```

### Low-Resource Setup (local Ollama)

For systems with limited RAM/VRAM running a local LLM:

```nix
programs.cairn-mail = {
  enable = true;

  ai = {
    model = "qwen2.5:1.5b";              # Smallest model
    endpoint = "http://localhost:11434"; # Local Ollama
    temperature = 0.2;                   # More deterministic
    useDefaultTags = false;              # Fewer tags = faster

    tags = [
      { name = "work"; description = "Work emails"; }
      { name = "personal"; description = "Personal emails"; }
      { name = "finance"; description = "Financial emails"; }
      { name = "junk"; description = "Spam and promotions"; }
    ];
  };

  sync = {
    maxMessagesPerSync = 25;  # Smaller batches
  };
};
```

---

## Service Management

### Systemd Services

```bash
# Web service
systemctl status cairn-mail-web.service
sudo systemctl restart cairn-mail-web.service
sudo journalctl -u cairn-mail-web.service -f

# Sync timer
systemctl status cairn-mail-sync.timer
systemctl list-timers cairn-mail-sync.timer

# Trigger manual sync
sudo systemctl start cairn-mail-sync.service
sudo journalctl -u cairn-mail-sync.service -f

# Tailscale Serve (if enabled)
systemctl status cairn-mail-tailscale-serve.service
tailscale serve status
```

### Disabling Automatic Sync

To disable the timer but keep manual sync available:

```nix
services.cairn-mail.sync.enable = false;
```

You can still trigger syncs manually:
```bash
sudo systemctl start cairn-mail-sync.service
```
