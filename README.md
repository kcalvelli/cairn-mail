# cairn-mail

<p align="center">
  <img src="docs/cairn-mail.png" alt="cairn-mail logo" width="200" />
</p>

**AI-powered inbox organizer for NixOS and Home Manager users.**

cairn-mail is a declarative email management system that combines direct provider integration (Gmail, IMAP) with AI classification to automatically organize your inbox. Messages are tagged, prioritized, and organized — and you bring your own LLM via any OpenAI-compatible endpoint (run Ollama or llama.cpp locally for full privacy, or route through a gateway to a hosted model).

![Desktop Dark Mode - Split Pane View](docs/screenshots/desktop-dark-split-pane.png)

> **Note:** This application is designed for users of [Cairn](https://github.com/kcalvelli/cairn), a NixOS configuration framework. The instructions below assume Cairn conventions (agenix for secrets, `~/.config/nixos_config` for configuration). Non-Cairn NixOS users may need to adapt paths and secret management approaches to their setup.

## Quick Links

- **[Quick Start Guide](docs/QUICKSTART.md)** - Get up and running in 15 minutes
- **[User Guide](docs/USER_GUIDE.md)** - Learn all features (desktop & mobile)
- **[Action Tags Guide](docs/ACTION_TAGS.md)** - Automate tasks from your inbox (contacts, calendar)
- **[Configuration Reference](docs/CONFIGURATION.md)** - All Nix options documented
- **[Architecture Overview](docs/ARCHITECTURE.md)** - System design deep-dive
- **[Development Guide](docs/DEVELOPMENT.md)** - Contributing and local development

## Features

### AI-Powered Classification
- **Automatic Tagging** - Messages tagged with categories like `work`, `finance`, `personal`, `shopping`
- **Confidence Scores** - Color-coded indicators show AI classification confidence
- **Customizable Taxonomy** - Define your own tags and categories in Nix
- **Bring Your Own LLM** - Any OpenAI-compatible endpoint works (Ollama, llama.cpp, vLLM, LiteLLM, openai-gateway, hosted APIs)

### Modern Web Interface
- **Responsive Design** - Works on desktop and mobile devices
- **Dark Mode** - System-aware theming with light/dark/auto modes
- **Split Pane View** - Preview messages without leaving the list (desktop)
- **Message Threading** - View conversation threads in context

![Desktop Light Mode - Bulk Selection](docs/screenshots/desktop-light-bulk-selection.png)

### Action Tags
- **Add Contact** - Tag an email to create a contact from the sender's info
- **Create Reminder** - Tag an email to create a calendar event from mentioned dates
- **Custom Actions** - Define your own actions that call any MCP tool
- **Toast Notifications** - Visual confirmation when actions succeed or fail
- **Requires:** [cairn-dav](https://github.com/kcalvelli/cairn-dav) + [mcp-gateway](https://github.com/kcalvelli/mcp-gateway) — see [Action Tags Guide](docs/ACTION_TAGS.md)

### Email Management
- **Multi-Account** - Manage Gmail and IMAP accounts from a single interface
- **Hidden Accounts** - Mark agent/bot accounts as `hidden` so they sync but stay out of the default UI
- **Folder Support** - Browse Inbox, Sent, Drafts, and Trash
- **Bulk Operations** - Select multiple messages for batch actions
- **Compose & Reply** - Full email composition with rich text formatting
- **Attachments** - View and download attachments
- **Adaptive Sync** - Quiet accounts back off automatically; busy ones stay current

### Mobile Experience
- **Touch-Optimized** - Swipe gestures for common actions
- **PWA Support** - Install as a standalone app
- **Material You Icons** - Adaptive theming on Android 13+
- **Offline Indicator** - Visual feedback when disconnected

#### Material You Icon Support

On Android 13+, the app icon automatically adapts to your device's color theme using [Material You](https://material.io/blog/announcing-material-you) dynamic theming. This is achieved through three icon types in the PWA manifest:

| Icon Type | Purpose | Format |
|-----------|---------|--------|
| `purpose: "any"` | Standard app icon display | PNG (192×192, 512×512) |
| `purpose: "maskable"` | Adaptive shapes (circles, squircles, etc.) | PNG with safe zone padding |
| `purpose: "monochrome"` | Material You themed icons | SVG silhouette (white on transparent) |

The monochrome icon (`icon-monochrome.svg`) is a simplified white silhouette of the logo that Android uses as a mask—the system applies your wallpaper-derived color palette automatically. This creates a cohesive home screen where all themed app icons share your personal color scheme.

<p align="center">
  <img src="docs/screenshots/mobile-light-drawer.png" alt="Mobile Light Mode - Drawer" width="300" />
  <img src="docs/screenshots/mobile-dark-message-thread.png" alt="Mobile Dark Mode - Thread View" width="300" />
</p>

### Keyboard Navigation
Full keyboard shortcut support for power users:
- `j`/`k` - Navigate messages
- `Enter` - Open message
- `r` - Reply
- `f` - Forward
- `u` - Toggle read/unread
- `#` - Delete
- `o` - Toggle split view
- `?` - Show all shortcuts

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Web UI (React)                       │
│  Material-UI • Tag Filtering • Bulk Actions • Search    │
└────────────────────┬────────────────────────────────────┘
                     │ HTTP/WebSocket
┌────────────────────▼────────────────────────────────────┐
│              FastAPI Backend (Python)                   │
│  REST API • WebSocket • Message Management • Sync       │
└──┬──────────────────────────────┬────────────────┬──────┘
   │                              │                │
   │ Gmail API / IMAP            │ /v1/chat       │ mcp-gateway
   │                              │ /completions   │
┌──▼────────────────┐  ┌─────────▼──────┐  ┌──────▼──────────┐
│  Email Providers  │  │ AI Classifier  │  │  Action Agent   │
│  • Gmail (OAuth2) │  │ • OpenAI-compat│  │  • add-contact  │
│  • IMAP (Password)│  │ • Tag/Priority │  │  • create-event │
│  • Fastmail, etc. │  │ • Bring-your-  │  │  → mcp-dav      │
│                   │  │   own LLM      │  │                 │
└───────────────────┘  └────────────────┘  └─────────────────┘
           │
           │ SQLite
           ▼
    ┌──────────────┐
    │   Database   │
    │  • Messages  │
    │  • Tags      │
    │  • Accounts  │
    └──────────────┘
```

## Installation

### Prerequisites

1. **NixOS with flakes** - Runs as system-level services
2. **An OpenAI-compatible LLM endpoint** - Any `/v1/chat/completions` provider works:
   - Local: [Ollama](https://ollama.com), [llama.cpp](https://github.com/ggerganov/llama.cpp), [vLLM](https://github.com/vllm-project/vllm)
   - Gateway/proxy: [LiteLLM](https://github.com/BerriAI/litellm), [openai-gateway](https://github.com/kcalvelli/openai-gateway)
   - Hosted: any OpenAI-compatible API

### Split Architecture

cairn-mail uses a split architecture:

| Module | Level | Purpose |
|--------|-------|---------|
| **NixOS module** | System | Web service, sync timer, Tailscale Serve |
| **Home-Manager module** | User | Email accounts, AI settings, config file |

### Add to Your Flake

```nix
{
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    home-manager.url = "github:nix-community/home-manager";
    cairn-mail.url = "github:kcalvelli/cairn-mail";
  };

  outputs = { nixpkgs, home-manager, cairn-mail, ... }: {
    nixosConfigurations.yourhost = nixpkgs.lib.nixosSystem {
      modules = [
        # 1. Apply overlay
        { nixpkgs.overlays = [ cairn-mail.overlays.default ]; }

        # 2. Import NixOS module
        cairn-mail.nixosModules.default

        # 3. Enable services
        {
          services.cairn-mail = {
            enable = true;
            port = 8080;
            user = "youruser";
          };
        }

        # 4. Home-manager for user config
        home-manager.nixosModules.home-manager
        {
          home-manager.users.youruser = { ... }: {
            imports = [ cairn-mail.homeManagerModules.default ];

            programs.cairn-mail = {
              enable = true;
              ai = {
                # Defaults to "claude-sonnet-4-20250514" via http://localhost:18789.
                # Point endpoint at any OpenAI-compatible /v1/chat/completions provider.
                model = "claude-sonnet-4-20250514";
                endpoint = "http://localhost:18789";
              };
              accounts.gmail = {
                provider = "gmail";
                email = "you@gmail.com";
                oauthTokenFile = "/path/to/token";
              };
            };
          };
        }
      ];
    };
  };
}
```

Then rebuild:

```bash
sudo nixos-rebuild switch --flake .
```

For complete setup instructions including Gmail OAuth and IMAP configuration, see the **[Quick Start Guide](docs/QUICKSTART.md)**.

## Usage

### Access the Web Interface

Once enabled, the web UI runs automatically as a systemd service:

```bash
# Check status
systemctl status cairn-mail-web.service
```

Open http://localhost:8080 in your browser.

### Sync Service

Email sync runs automatically via systemd timer:

```bash
# Check sync timer
systemctl status cairn-mail-sync.timer

# Trigger manual sync
sudo systemctl start cairn-mail-sync.service

# View sync logs
sudo journalctl -u cairn-mail-sync.service -f
```

### MCP Server for AI Assistants

cairn-mail includes an MCP (Model Context Protocol) server that allows AI assistants like Claude to automate email workflows through natural language.

**Available Tools (14):**

| Tool | Description |
|------|-------------|
| `list_accounts` | List configured email accounts (includes hidden accounts) |
| `search_emails` | Search with filters (account, folder, tags, text) |
| `read_email` | Get full email content by ID |
| `compose_email` | Create a draft email |
| `send_email` | Send a draft or compose+send in one step |
| `reply_to_email` | Create a reply draft for a thread |
| `mark_read` | Mark messages as read/unread |
| `delete_email` | Delete emails (trash or permanent) |
| `restore_email` | Restore a trashed message back to its original folder |
| `update_tags` | Set classification tags on a single message |
| `bulk_update_tags` | Set tags on many messages in one call (records DFSL feedback) |
| `delete_by_filter` | Delete every message matching a tag/folder/account filter |
| `list_tags` | Enumerate the configured tag taxonomy |
| `get_unread_count` | Unread totals, optionally scoped to one account |

**Example prompts:**
- "Send an email from my work account to joe@example.com saying I'll be late"
- "Show me unread emails tagged as important"
- "Mark all newsletters as read"

**Configuration for Claude Desktop:**

Add to your Claude Desktop config (`~/.config/claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "cairn-mail": {
      "command": "cairn-mail",
      "args": ["mcp"]
    }
  }
}
```

**CLI Commands:**

```bash
# Start MCP server manually (for testing)
cairn-mail mcp

# With custom API URL
cairn-mail mcp --api-url http://localhost:9000

# Show available tools
cairn-mail mcp info
```

> **Note:** The web service must be running for the MCP server to work.

## Screenshots

### Desktop Interface

| Dark Mode (Split Pane) | Light Mode (Bulk Selection) |
|------------------------|----------------------------|
| ![Dark Split Pane](docs/screenshots/desktop-dark-split-pane.png) | ![Light Bulk Selection](docs/screenshots/desktop-light-bulk-selection.png) |

| Compose Window | Statistics Dashboard |
|----------------|---------------------|
| ![Compose](docs/screenshots/desktop-dark-compose.png) | ![Statistics](docs/screenshots/desktop-dark-statistics.png) |

### Settings & Configuration

| Tag Taxonomy | Maintenance |
|--------------|-------------|
| ![Tags](docs/screenshots/desktop-dark-settings-tags.png) | ![Maintenance](docs/screenshots/desktop-dark-settings-maintenance.png) |

## Product Scope

**cairn-mail is an inbox organizer, not a spam filter.**

### What This Product Does
- Classifies legitimate mail that reached your inbox
- Organizes messages with AI-powered tags
- Identifies low-priority promotional content ("junk" tag)
- Helps you prioritize what matters

### What This Product Doesn't Do
- Does not filter spam - your email provider does this
- Does not sync spam folders - intentionally excluded
- Does not replace SpamAssassin/provider filters

## Roadmap

### Completed

- [x] AI-powered classification with confidence scores
- [x] Dark mode with system preference detection
- [x] PWA support (installable as desktop/mobile app)
- [x] Offline status indicator
- [x] Email composition and sending
- [x] Attachments view and download
- [x] Account maintenance CLI
- [x] Keyboard shortcuts in web UI
- [x] Mobile-responsive design with touch gestures
- [x] Message threading
- [x] Real-time sync via WebSockets
- [x] Bulk operations with undo
- [x] AI-generated quick replies
- [x] MCP server for AI assistant integration
- [x] Action tags — calendar and contact integration via MCP

### Planned

- [ ] Outlook/Office365 provider
- [ ] User feedback loop for AI improvement

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

This project follows a [Code of Ethics](CODE_OF_ETHICS.md) rooted in principles of mutual respect and dignity.

## License

MIT License - see LICENSE file for details.

## Credits

Built with:
- [FastAPI](https://fastapi.tiangolo.com/) - Backend framework
- [React](https://react.dev/) - Frontend framework
- [Material-UI](https://mui.com/) - UI components
- [SQLAlchemy](https://www.sqlalchemy.org/) - Database ORM
- [React Query](https://tanstack.com/query) - Data fetching
- [Zustand](https://zustand-demo.pmnd.rs/) - State management

Bring-your-own LLM via any OpenAI-compatible endpoint — works well with [Ollama](https://ollama.com/), [llama.cpp](https://github.com/ggerganov/llama.cpp), and gateway proxies like [LiteLLM](https://github.com/BerriAI/litellm).

Integrates with:
- [cairn-dav](https://github.com/kcalvelli/cairn-dav) - CalDAV/CardDAV sync with MCP server
- [mcp-gateway](https://github.com/kcalvelli/mcp-gateway) - REST API gateway for MCP servers

---

**cairn-mail** - Organize your inbox with AI, locally.
