# Action Tags

Action tags let you trigger real-world actions from your inbox. Tag an email with `add-contact` or `create-reminder`, and cairn-mail will automatically extract the relevant data and create the contact or calendar event for you.

## How It Works

```
1. You add an action tag to an email        (e.g., "add-contact")
   ↓
2. Next sync cycle runs                     (every 5 min, or trigger manually)
   ↓
3. Ollama extracts structured data          (name, email, phone from signature)
   ↓
4. MCP tool is called via mcp-gateway       (creates contact in your addressbook)
   ↓
5. Tag is removed and you get a toast       ("Contact Added" ✓)
```

If something goes wrong, the tag stays on the message and retries next sync (up to 3 attempts). You'll see an error toast like "Couldn't add contact" so you know to check the logs.

## Built-in Actions

| Tag | What It Does | MCP Tool |
|-----|-------------|----------|
| `add-contact` | Creates a contact from the email sender's info (name, email, org, phone from signature) | `mcp-dav/create_contact` |
| `create-reminder` | Creates a calendar event from dates, deadlines, or events mentioned in the email | `mcp-dav/create_event` |

Both actions use Ollama to intelligently extract data from the email content and headers. The extraction runs at low temperature (0.1) for consistent, structured output.

## Prerequisites

Action tags require three external services running alongside cairn-mail:

### 1. Ollama

Local LLM runtime used for extracting structured data from emails.

- **Website:** [ollama.com](https://ollama.com)
- **GitHub:** [github.com/ollama/ollama](https://github.com/ollama/ollama)
- Pull a model: `ollama pull llama3.2`

### 2. cairn-dav (includes mcp-dav)

Provides CalDAV/CardDAV sync and the MCP server that action tags call to create contacts and calendar events. mcp-dav is a component within the cairn-dav project.

- **GitHub:** [github.com/kcalvelli/cairn-dav](https://github.com/kcalvelli/cairn-dav)
- Provides: vdirsyncer integration, khal (calendar CLI), khard (contacts CLI), and the mcp-dav MCP server
- Must be configured with your CalDAV/CardDAV provider (Google, Fastmail, Nextcloud, etc.)

### 3. mcp-gateway

REST API gateway that exposes MCP servers (like mcp-dav) over HTTP. Action tags call tools through this gateway.

- **GitHub:** [github.com/kcalvelli/mcp-gateway](https://github.com/kcalvelli/mcp-gateway)
- Default URL: `http://localhost:8085`
- Must be configured with mcp-dav as a registered server

### Architecture

```
cairn-mail                    mcp-gateway                 mcp-dav
┌──────────────┐   HTTP POST    ┌─────────────┐   MCP      ┌───────────────┐
│ Action Agent │ ──────────────→│ REST API    │ ─────────→ │ create_contact│
│              │  /api/tools/   │ :8085       │            │ create_event  │
│ Ollama ←─────│  mcp-dav/     └─────────────┘            │ list_contacts │
│ (extraction) │  create_contact                           └───────┬───────┘
└──────────────┘                                                   │
                                                            vdirsyncer
                                                           ┌───────▼───────┐
                                                           │ Google Cal    │
                                                           │ Google Contacts│
                                                           │ Fastmail, etc.│
                                                           └───────────────┘
```

## Configuration

Action tags are configured in the Home-Manager module under `programs.cairn-mail`.

### Minimal Setup

```nix
programs.cairn-mail = {
  enable = true;

  gateway = {
    enable = true;
    url = "http://localhost:8085";          # mcp-gateway URL
    addressbook = "google/default";         # vdirsyncer addressbook name
    calendar = "kc.calvelli@gmail.com";     # vdirsyncer calendar name
  };

  # ... accounts, ai, etc.
};
```

That's it. The two built-in actions (`add-contact` and `create-reminder`) are automatically available when the gateway is enabled.

### Finding Your Addressbook and Calendar Names

The `addressbook` and `calendar` values must match your vdirsyncer configuration. To find them:

```bash
# List configured calendars
vdirsyncer discover

# Or check your vdirsyncer storage directories
ls ~/.calendars/       # Calendar names are directory names
ls ~/.contacts/        # Addressbook names are directory names (may include subpath)
```

> **Tip:** Calendar names often match your email address (e.g., `kc.calvelli@gmail.com`). Addressbook names may include a subpath like `google/default` depending on your vdirsyncer configuration.

### Gateway Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `gateway.enable` | boolean | `false` | Enable action tag processing |
| `gateway.url` | string | `"http://localhost:8085"` | mcp-gateway REST API URL |
| `gateway.addressbook` | string | *required* | vdirsyncer addressbook name for `add-contact` |
| `gateway.calendar` | string | *required* | vdirsyncer calendar name for `create-reminder` |

> **Note:** `addressbook` and `calendar` are required when `gateway.enable = true`. The build will fail with an assertion error if they are not set.

## Using Action Tags

### Adding Tags in the UI

1. Open a message in the web UI
2. Click the tag editor (pencil icon next to tags)
3. Action tags appear in a separate **"Actions"** group with an amber color
4. Select `add-contact` or `create-reminder`
5. The tag appears on the message with a distinctive dashed amber border and bolt icon

### What Happens Next

- On the next sync cycle (every 5 minutes by default), the action agent processes the tag
- You can also trigger sync manually from the UI sync button
- On **success**: the tag is removed and you see a green toast ("Contact Added" or "Event Created")
- On **failure**: you see a red toast ("Couldn't add contact" or "Couldn't create event"), the tag remains, and the action retries on the next sync (up to 3 attempts)

### Monitoring

```bash
# View action processing in real-time
sudo journalctl -u cairn-mail-web.service -f | grep -i action

# Check action log via API
curl http://localhost:8080/api/actions/log | python3 -m json.tool

# See available actions and their status
curl http://localhost:8080/api/actions/available | python3 -m json.tool

# Retry a failed action
curl -X POST http://localhost:8080/api/actions/retry/{log_id}
```

## Custom Actions

You can define your own action tags that call any MCP tool available through mcp-gateway.

### Example: Custom Action

```nix
programs.cairn-mail = {
  gateway.enable = true;
  gateway.url = "http://localhost:8085";
  gateway.addressbook = "google/default";
  gateway.calendar = "personal";

  actions = {
    # Custom action targeting a hypothetical expenses MCP server
    "save-receipt" = {
      description = "Save receipt to expense tracker";
      server = "expenses";          # MCP server ID in mcp-gateway
      tool = "add_expense";         # MCP tool name
      defaultArgs = {
        currency = "USD";
        category = "receipts";
      };
      extractionPrompt = ''
        Analyze this email and extract expense details.

        EMAIL CONTENT:
        Subject: {subject}
        From: {from_email}
        Date: {date}
        Body:
        {body}

        Return ONLY a JSON object:
        {{
          "description": "What was purchased",
          "amount": "123.45",
          "vendor": "Store name",
          "date": "2026-01-15"
        }}
      '';
    };
  };
};
```

### Overriding Built-in Actions

You can customize the built-in actions without replacing them entirely:

```nix
actions = {
  "add-contact" = {
    description = "Create a contact from email sender";
    server = "mcp-dav";
    tool = "create_contact";
    defaultArgs = {
      organization = "My Company";    # Always set this org
    };
  };
};
```

### Action Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `description` | string | `""` | Human-readable description shown in the UI |
| `server` | string | *required* | MCP server ID in mcp-gateway |
| `tool` | string | *required* | MCP tool name to call |
| `extractionPrompt` | string or null | `null` | Custom Ollama prompt (null = use built-in) |
| `defaultArgs` | attrset | `{}` | Static arguments merged with extracted data |
| `enabled` | boolean | `true` | Enable/disable this action |

### Extraction Prompt Variables

Custom extraction prompts can use these template variables:

| Variable | Description |
|----------|-------------|
| `{subject}` | Email subject line |
| `{from_email}` | Sender email address |
| `{to_emails}` | Recipient email addresses |
| `{date}` | Email date |
| `{body}` | Email body text (truncated to 3000 chars) |
| `{current_date}` | Today's date (e.g., "2026-01-29 Thursday") |

> **Important:** Use double braces `{{` and `}}` for literal braces in JSON examples within your prompt, since single braces are interpreted as template variables.

## Troubleshooting

### Action tag stays on message (not processing)

1. **Is the gateway enabled?** Check `gateway.enable = true` in your Nix config
2. **Is mcp-gateway running?** `curl http://localhost:8085/api/tools` should return a list of tools
3. **Is the tool available?** Check `curl http://localhost:8080/api/actions/available` — actions show as `"available": true` when the gateway has the required tool
4. **Max retries exceeded?** After 3 failures, the action is skipped. Use the retry endpoint to reset: `curl -X POST http://localhost:8080/api/actions/retry/{log_id}`

### "Couldn't add contact" / "Couldn't create event"

Check the action log for the specific error:

```bash
curl http://localhost:8080/api/actions/log?limit=5 | python3 -m json.tool
```

Common errors:
- **"Calendar not found: ..."** — Your `gateway.calendar` doesn't match a vdirsyncer calendar name. Run `vdirsyncer discover` to find the correct name.
- **"day is out of range for month"** — The LLM extracted an invalid date. The action will auto-fix most date issues, but edge cases can occur. Retry the action.
- **"Cannot connect to mcp-gateway"** — mcp-gateway is not running or the URL is wrong.
- **"Validation error"** — The extracted data is missing required fields. Check the `extracted_data` in the action log.

### Sync runs but no actions processed

The sync log should show `actions=X/Y` in the SyncResult. If it shows `actions=0/0`:
- Verify the message actually has an action tag (check in the UI)
- Make sure `gateway.enable = true` is set
- Check that the sync is running through the web service (UI-triggered sync), not just the CLI timer

### vdirsyncer sync

After action tags create contacts or calendar events locally, they need to be synced to your remote provider (Google, etc.) via vdirsyncer:

```bash
vdirsyncer sync
```

This can be automated via the cairn-dav systemd timer if you have it configured.
