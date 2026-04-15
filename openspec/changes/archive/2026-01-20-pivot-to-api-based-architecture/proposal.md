# Proposal: Pivot to API-Based Architecture with Two-Way Sync

## Why

The current notmuch/Maildir architecture has fundamental limitations that prevent cairn-mail from being a practical, user-friendly solution:

1. **One-Way Sync Problem**: Tags applied locally via notmuch never sync back to Gmail/IMAP/Outlook, creating a fragmented experience where changes made in cairn-mail aren't reflected in the user's primary email client.

2. **Client Ecosystem Limitations**: Notmuch-compatible email clients (aerc, alot, astroid) are niche terminal/desktop apps that most users find unintuitive. The learning curve is steep and the UI/UX is dated.

3. **Maildir is Ancient**: The Maildir format was designed in 1995 and doesn't map well to modern email features like labels, categories, importance markers, or collaborative workflows.

4. **Isolated Experience**: Users must choose between using cairn-mail (with AI tags) OR their regular email client (Gmail web, Outlook, mobile apps) - they can't benefit from AI tagging in their normal workflow.

5. **Mobile Gap**: No mobile support means users can't access their AI-organized email on phones/tablets where most email reading happens.

## What Changes

We will **completely pivot** the architecture from local Maildir+notmuch to a cloud-connected API-based system:

### Core Architecture Changes

1. **Email Provider Integration Layer**
   - Replace `mbsync`/Maildir with native provider APIs:
     - **Gmail**: Gmail API (OAuth2, full read/write access to labels, messages)
     - **IMAP**: IMAP with X-GM-LABELS extension (Gmail), IMAP METADATA (RFC 5464)
     - **Outlook.com**: Microsoft Graph API (OAuth2, categories, importance, flags)
   - Implement two-way synchronization:
     - Pull new messages for AI classification
     - Push AI-assigned labels/categories back to the provider
     - Subscribe to webhooks/push notifications for real-time updates

2. **AI Classification Engine** (Enhanced)
   - Keep local LLM processing via Ollama (privacy-first)
   - Map AI tags to provider-native concepts:
     - Gmail: Custom labels (`AI/Work`, `AI/Finance`, `AI/ToDo`, `AI/Priority-High`)
     - Outlook: Categories and importance markers
     - IMAP: Custom flags or IMAP KEYWORD extension
   - Add conflict resolution for user-modified labels
   - Support incremental classification (only new/changed messages)

3. **Modern UI Options** (Choose Your Own Adventure)
   - **Option A: Web Application**
     - React/Vue/Svelte frontend
     - Local backend server (Rust/Go/Python)
     - Access via `localhost:8080` in any browser
     - Mobile-responsive design
   - **Option B: Browser Extension**
     - Gmail/Outlook.com integration directly in the web UI
     - Side panel showing AI insights and tags
     - Works everywhere the user reads email
   - **Option C: Desktop Application**
     - Electron or Tauri app
     - Cross-platform (Linux, macOS, Windows)
     - Tray icon for background sync
   - All options connect to the same local AI backend

4. **Data Storage**
   - Replace Maildir with SQLite database for metadata:
     - Message IDs, AI tags, classification timestamps
     - Sync state tracking
     - User feedback for tag corrections
   - **No local email storage** - emails stay on the provider
   - Cache headers/bodies temporarily for AI processing only

### Implementation Phases

1. **Phase 1: Core API Layer** (MVP)
   - Gmail API integration with OAuth2
   - AI classifier adapted to work with API-fetched messages
   - Two-way label sync (AI tags → Gmail labels)
   - Secure credential storage (OAuth tokens + IMAP passwords)
   - CLI tool for testing and manual classification

2. **Phase 2: Web UI** (User-Friendly Interface)
   - Simple web dashboard showing AI-tagged messages
   - Tag management and feedback interface
   - Settings for AI behavior customization

3. **Phase 3: Additional Providers**
   - IMAP with extension support (Fastmail, iCloud, etc.)
   - Outlook.com / Microsoft Graph API
   - Provider-agnostic abstraction layer

4. **Phase 4: Advanced Features**
   - Browser extension for Gmail/Outlook
   - Multi-account support with unified inbox
   - Smart filters and rules based on AI tags
   - Advanced analytics and insights

## Impact

### Breaking Changes (**MAJOR**)

- **Complete architecture replacement**: The entire Maildir+notmuch+mbsync stack is removed
- **No backward compatibility**: Existing configurations must be migrated
- **New dependencies**: Requires provider API credentials (OAuth2 apps)
- **NixOS module rewrite**: All existing module options will change

### Benefits

- **Two-Way Sync**: AI tags appear as labels in Gmail, categories in Outlook, everywhere the user reads email
- **Universal Access**: Users can leverage AI organization in their existing email clients (web, mobile, desktop)
- **Modern UX**: Web-based or browser-integrated interface that's intuitive and accessible
- **Mobile Support**: AI-tagged emails visible on phones/tablets via native Gmail/Outlook apps
- **Real-World Practicality**: Actual day-to-day usability instead of a niche power-user tool
- **Easier Onboarding**: OAuth2 flow is more user-friendly than Maildir setup

### Affected Components

- **Removed**: mbsync, msmtp, notmuch, Maildir, aerc/alot/astroid integrations
- **Added**: Gmail API client, Microsoft Graph client, IMAP extension support
- **Added**: Web server, frontend UI, SQLite storage
- **Modified**: AI classifier (API message format instead of Maildir files)
- **Modified**: NixOS module (completely new options schema)

### Risks

1. **API Rate Limits**: Gmail API has quotas (10,000 quota units/day for free tier)
   - Mitigation: Implement smart polling, caching, and batch operations
2. **OAuth Token Management**: Must create OAuth apps for Gmail/Outlook
   - Mitigation: Provide helper CLI tool and clear documentation
3. **Credential Security**: OAuth tokens and IMAP passwords must be stored securely
   - Mitigation: Integrate with sops-nix/agenix or use systemd-creds for encrypted storage
4. **Offline Access**: No local email cache means no offline reading
   - Mitigation: Optional local caching for recently classified messages
5. **Provider Lock-In**: Harder to switch providers than with IMAP
   - Mitigation: Abstract interface layer that works across providers

## Open Questions

1. **Which secrets management solution should we use?**
   - Option A: sops-nix (encrypted secrets in repo, decrypted at activation)
   - Option B: agenix (age-encrypted secrets, simpler than sops)
   - Option C: systemd-creds (systemd's built-in credential system)
   - **Recommendation**: Support all three, with examples for each

2. **Should we maintain IMAP support or focus on APIs only?**
   - **Recommendation**: Support both - IMAP for Fastmail/self-hosted, APIs for Gmail/Outlook

3. **How should we handle OAuth2 client credentials?**
   - **Recommendation**: User creates their own OAuth apps (privacy-first, documented thoroughly)

4. **Should we keep the declarative NixOS config style or add imperative CLI?**
   - **Recommendation**: Keep declarative as primary (NixOS module), add CLI for one-off operations

## Success Criteria

This pivot will be successful if:

1. Users can connect their Gmail account and see AI tags appear as labels within 10 minutes
2. Tags applied by AI in cairn-mail sync back to Gmail web/mobile within 1 minute
3. The web UI is intuitive enough for non-technical users to understand and use
4. At least 3 email providers are supported (Gmail, IMAP, Outlook.com)
5. OAuth2 setup has clear documentation and helper tools
