# NixOS Module Testing Guide

## Overview

This guide walks through testing the newly implemented Home Manager module for cairn-mail v2.

## Current Status

✅ Module implemented at `modules/home-manager/default.nix`
✅ User configuration updated in `~/.config/nixos_config/keith.nix`
⏳ Ready for testing

## Test Plan

### Step 1: Apply Home Manager Configuration

```bash
# From your NixOS config directory
cd ~/.config/nixos_config
home-manager switch --flake .#keith@desktop
```

**Expected outcome:**
- Build should succeed
- No validation errors
- New systemd services installed

### Step 2: Verify Generated Configuration

```bash
# Check generated runtime config
cat ~/.config/cairn-mail/config.yaml
```

**Expected content:**
```yaml
{
  "database_path": "/home/keith/.local/share/cairn-mail/mail.db",
  "accounts": {
    "personal": {
      "id": "personal",
      "provider": "gmail",
      "email": "kc.calvelli@gmail.com",
      "real_name": "Keith Calvelli",
      "credential_file": "/home/keith/gmail-oauth-token.json",
      "settings": {
        "label_prefix": "AI",
        "label_colors": { ... },
        "sync_frequency": "5m",
        "enable_webhooks": false,
        "ai_model": "llama3.2",
        "ai_endpoint": "http://localhost:11434",
        "ai_temperature": 0.3
      }
    }
  },
  "ai": {
    "enable": true,
    "model": "llama3.2",
    "endpoint": "http://localhost:11434",
    "temperature": 0.3,
    "tags": [ ... ]
  },
  "ui": {
    "enable": false,
    "type": "cli",
    "port": 8080
  }
}
```

### Step 3: Verify Systemd Services

```bash
# Check timer is installed and enabled
systemctl --user list-timers | grep cairn-mail

# Check service status
systemctl --user status cairn-mail-sync.service
systemctl --user status cairn-mail-sync.timer

# Verify timer configuration
systemctl --user cat cairn-mail-sync.timer
```

**Expected output:**
- Timer shows in list with next activation time
- Service exists (inactive until timer triggers)
- Timer configured with:
  - OnBootSec=2min
  - OnUnitActiveSec=5min
  - Persistent=true

### Step 4: Manually Test Sync Service

```bash
# Start sync service manually
systemctl --user start cairn-mail-sync.service

# Watch logs in real-time
journalctl --user -u cairn-mail-sync.service -f
```

**Expected outcome:**
- Service runs successfully
- Fetches messages from Gmail
- Classifies with Ollama
- Updates labels
- Completes without errors

### Step 5: Verify Database Integration

```bash
# Run status command
cairn-mail status
```

**Expected output:**
- Shows "personal" account
- Email: kc.calvelli@gmail.com
- Provider: gmail
- Last sync timestamp
- Message counts
- Classification statistics

### Step 6: Enable Automatic Sync

```bash
# Enable and start the timer
systemctl --user enable cairn-mail-sync.timer
systemctl --user start cairn-mail-sync.timer

# Verify it's running
systemctl --user list-timers | grep cairn-mail
```

**Expected outcome:**
- Timer shows "NEXT" activation time
- Service will run automatically every 5 minutes

### Step 7: Monitor Automatic Sync

```bash
# Watch for automatic sync executions
journalctl --user -u cairn-mail-sync.service -f
```

Wait for the timer to trigger (should happen within 2 minutes after boot, then every 5 minutes).

## Validation Checklist

- [ ] home-manager switch completes successfully
- [ ] Config file generated at `~/.config/cairn-mail/config.yaml`
- [ ] Config contains correct account settings
- [ ] Systemd timer installed and enabled
- [ ] Systemd service installed
- [ ] Manual service start works
- [ ] Sync fetches and classifies messages
- [ ] Labels applied to Gmail
- [ ] Status command shows statistics
- [ ] Automatic sync timer triggers correctly
- [ ] No errors in journalctl logs

## Troubleshooting

### Build Errors

If you get validation errors during build:

```bash
# Check the specific assertion that failed
# Module assertions:
# - At least one account must be configured ✓
# - Gmail/Outlook require oauthTokenFile ✓
# - IMAP requires passwordFile and imap config N/A
```

### Service Failures

If sync service fails:

```bash
# Check detailed logs
journalctl --user -u cairn-mail-sync.service -n 50

# Common issues:
# 1. OAuth token expired - run: cairn-mail auth setup gmail
# 2. Ollama not running - run: ollama serve
# 3. Database permissions - check ~/.local/share/cairn-mail/
```

### Missing Configuration

If config.yaml not generated:

```bash
# Verify module is enabled
home-manager packages | grep cairn-mail

# Check for file permission issues
ls -la ~/.config/cairn-mail/
```

## Success Criteria

The module is working correctly when:

1. ✅ Configuration applied without errors
2. ✅ Systemd services running
3. ✅ Automatic sync every 5 minutes
4. ✅ Messages fetched from Gmail
5. ✅ AI classification working
6. ✅ Labels synced to Gmail
7. ✅ Status command shows statistics
8. ✅ No manual database setup required

## Next Steps After Successful Test

Once testing is complete:

1. **Optional**: Add additional accounts (IMAP when implemented)
2. **Optional**: Customize AI tag taxonomy
3. **Optional**: Adjust sync frequency
4. **Phase 2**: Enable web UI when implemented

## Reverting if Needed

If you need to disable the module:

```bash
# Edit keith.nix
programs.cairn-mail.enable = false;

# Apply
home-manager switch

# Stop and disable services
systemctl --user stop cairn-mail-sync.timer
systemctl --user disable cairn-mail-sync.timer
```

## Notes

- The module uses the same OAuth token file you created earlier
- Database location: `~/.local/share/cairn-mail/mail.db`
- Logs: `journalctl --user -u cairn-mail-sync.service`
- The manual test account created earlier will be replaced by the declarative config
