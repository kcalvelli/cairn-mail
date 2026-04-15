# Design Document: Phase 8 - AI Classification, PWA, Theming

## Overview

This document captures architectural decisions for Phase 8, which bundles four related improvements: AI classification enhancements, branding, PWA functionality, and theming support.

## Design Decisions

### 1. Theme System Architecture

**Decision:** Use React Context with MUI's ThemeProvider for theming.

**Rationale:**
- MUI already has built-in support for light/dark themes
- React Context provides app-wide access without prop drilling
- localStorage for persistence is simple and doesn't require backend changes
- System preference detection via `prefers-color-scheme` is widely supported

**Implementation:**
```typescript
// ThemeContext provides:
interface ThemeContextValue {
  mode: 'light' | 'dark' | 'system';
  resolvedMode: 'light' | 'dark'; // actual applied mode
  toggleMode: () => void;
  setMode: (mode: 'light' | 'dark' | 'system') => void;
}

// Storage key
const THEME_KEY = 'cairn-theme';

// System preference detection
const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)');
```

**Alternatives Considered:**
- **CSS-only theming**: Less integration with MUI components
- **Server-side preference**: Requires database changes, overkill for this use case
- **CSS custom properties only**: Would need custom MUI integration

### 2. PWA Implementation Strategy

**Decision:** Use `vite-plugin-pwa` with Workbox for service worker generation.

**Rationale:**
- vite-plugin-pwa handles manifest generation and SW registration
- Workbox provides battle-tested caching strategies
- Auto-updates with minimal configuration
- TypeScript support out of the box

**Service Worker Strategy:**
```javascript
// vite.config.ts
export default defineConfig({
  plugins: [
    VitePWA({
      registerType: 'autoUpdate',
      workbox: {
        // Cache static assets only, not API responses
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff,woff2}'],
        // Don't cache /api/* routes
        navigateFallbackDenylist: [/^\/api/],
      },
      manifest: {
        name: 'Cairn AI Mail',
        short_name: 'Mail',
        // ... rest of manifest
      }
    })
  ]
});
```

**Alternatives Considered:**
- **Manual service worker**: More control but significant maintenance burden
- **workbox-cli**: Requires separate build step
- **No PWA**: Would miss installability and offline improvements

### 3. Offline Handling Philosophy

**Decision:** Offline-aware, not offline-first. Show status, disable actions, but don't queue operations.

**Rationale:**
- Email is inherently a connected experience
- Full offline support would require significant backend changes (SQLite in browser, sync logic)
- Users expect email to require connectivity
- Simple offline awareness prevents confusing errors

**User Experience:**
```
Online:
  - All features work normally
  - No indicators shown

Offline:
  - Banner: "You're offline. Some features may be unavailable."
  - Send button: Disabled with tooltip "Cannot send while offline"
  - Sync button: Disabled
  - Read cached messages: Still works (browser cache)
  - New messages: Won't load (API fails gracefully)
```

**Alternatives Considered:**
- **Offline-first with IndexedDB**: Massive complexity, not needed for v1
- **Queue operations**: Sync conflicts, data consistency issues
- **Ignore offline**: Poor UX with cryptic errors

### 4. Model Recommendation Strategy

**Decision:** Document recommendations, change default to phi3:mini, but don't auto-detect hardware.

**Rationale:**
- Auto-detecting GPU/RAM from browser is unreliable
- Users typically know their hardware constraints
- Phi3:mini is a better default (faster, smaller, good quality)
- Documentation empowers users to make informed choices

**Recommended Models:**

| Model | Parameters | RAM | Use Case |
|-------|------------|-----|----------|
| phi3:mini | 3.8B | 4GB | Default, fast, resource-constrained |
| mistral:7b | 7B | 8GB | Balanced quality/speed |
| llama3.1:8b | 8B | 16GB | Best quality, slower |

**Configuration Example:**
```nix
programs.cairn-mail.ai = {
  model = "phi3:mini";  # or "mistral:7b" or "llama3.1:8b"
  endpoint = "http://localhost:11434";
  temperature = 0.3;
};
```

**Alternatives Considered:**
- **Auto-detect and recommend**: Unreliable from browser context
- **Multiple models per task**: Unnecessary complexity
- **Cloud fallback**: Violates local-only constraint

### 5. Confidence Score Implementation

**Decision:** Extract confidence from LLM response, default to 0.8 if not provided.

**Rationale:**
- Many LLMs can provide confidence with proper prompting
- Visual indicator helps users understand classification quality
- Default of 0.8 (high) prevents alarming users on first use
- Not stored in database (calculated on classification)

**Prompt Addition:**
```
RESPOND WITH ONLY A JSON OBJECT (no markdown, no explanation):
{
  "tags": ["tag1", "tag2"],
  "priority": "high" | "normal",
  "action_required": true | false,
  "can_archive": true | false,
  "confidence": 0.85  // How confident are you in this classification (0.0-1.0)
}
```

**UI Display:**
- High (0.8-1.0): Green dot/badge, no label
- Medium (0.5-0.8): Yellow dot/badge, "Uncertain" tooltip
- Low (0.0-0.5): Red dot/badge, "Low confidence" tooltip

**Alternatives Considered:**
- **Separate confidence call**: Doubles API calls, slow
- **Multiple model ensemble**: Too complex for phase 8
- **No confidence**: Misses opportunity for user trust

### 6. Branding Approach

**Decision:** Single logo in topbar, unified color scheme, minimal changes.

**Rationale:**
- Simple is better for initial branding
- Logo + consistent colors establishes identity
- Avoid over-branding that distracts from content
- Easy to implement without design system overhaul

**Visual Hierarchy:**
```
┌─────────────────────────────────────────────────────────┐
│ [Logo] Cairn AI Mail              [Theme] [Account]     │  ← Topbar (primary color)
├─────────────────┬───────────────────────────────────────┤
│ Inbox (5)       │                                       │
│ Sent            │  Message List / Detail                │
│ Drafts (2)      │                                       │
│ Trash           │                                       │
│                 │                                       │
│ Tags            │                                       │
│ • work (12)     │                                       │
│ • personal (8)  │                                       │
├─────────────────┴───────────────────────────────────────┤
│ [Offline Banner - shown when disconnected]              │
└─────────────────────────────────────────────────────────┘
                         ↑
                  Sidebar uses same primary color as topbar
```

**Color Strategy:**
- Topbar: `theme.palette.primary.main`
- Sidebar: `theme.palette.primary.main` (match topbar)
- Both adapt to light/dark mode automatically via MUI theming

### 7. Logo Asset Strategy

**Decision:** Create simple text-based logo initially, upgrade later if needed.

**Rationale:**
- No existing logo asset to use
- Simple text-based or icon-based logo is quick to create
- Can be upgraded with professional design later
- Needs to work in both light and dark modes

**Requirements:**
- SVG or PNG with transparency
- Works on both light and dark backgrounds
- 192x192 for manifest, scalable version for topbar
- Recognizable at small sizes (favicon, PWA icon)

**Initial Design:**
- Mail envelope icon + "Cairn" text
- Or just stylized "A" icon
- Primary brand color with good contrast

## Data Flow

### Theme Toggle Flow
```
User clicks toggle
       ↓
ThemeContext.toggleMode()
       ↓
Update state: mode → 'dark' (or next in cycle)
       ↓
Save to localStorage
       ↓
MUI ThemeProvider receives new mode
       ↓
All components re-render with dark palette
       ↓
<meta name="theme-color"> updated
```

### Offline Detection Flow
```
Browser fires 'offline' event
       ↓
useOnlineStatus hook updates state
       ↓
OfflineIndicator component renders
       ↓
Action buttons check isOnline
       ↓
Disabled buttons show tooltip
```

### Classification with Confidence Flow
```
Message received
       ↓
AIClassifier.classify() called
       ↓
Build prompt with confidence request
       ↓
Send to Ollama
       ↓
Parse JSON response
       ↓
Extract confidence (default 0.8)
       ↓
Return Classification with confidence
       ↓
API returns confidence in response
       ↓
UI displays confidence indicator
```

## File Structure

```
web/
├── public/
│   ├── manifest.json          # PWA manifest
│   ├── cairn-mail.png      # Logo 192x192
│   ├── cairn-mail-512.png  # Logo 512x512
│   └── favicon.ico            # Updated favicon
├── src/
│   ├── contexts/
│   │   └── ThemeContext.tsx   # Theme state management
│   ├── components/
│   │   ├── ThemeToggle.tsx    # Theme toggle button
│   │   ├── OfflineIndicator.tsx # Offline banner
│   │   └── ConfidenceBadge.tsx # Classification confidence
│   ├── hooks/
│   │   └── useOnlineStatus.ts # Online detection hook
│   ├── main.tsx               # Updated with ThemeProvider, SW registration
│   └── vite.config.ts         # PWA plugin configuration
└── package.json               # Add vite-plugin-pwa

src/
└── cairn_mail/
    ├── ai_classifier.py       # Add confidence extraction
    └── providers/base.py      # Classification.confidence field
```

## Migration Notes

### Backwards Compatibility

1. **Theme**: Default is `system`, which resolves to current behavior for most users
2. **PWA**: Progressive enhancement, works without SW support
3. **Offline**: Graceful degradation, app still works (just shows indicator)
4. **Confidence**: Optional field, old clients ignore it

### Upgrade Path

1. Deploy backend with confidence support
2. Deploy frontend with theme/PWA/offline
3. Users see improvements immediately
4. No data migration required

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Service worker caches stale assets | Medium | Low | Auto-update strategy, version in SW |
| Dark mode breaks some component | Medium | Low | Thorough testing, use MUI palette |
| LLM doesn't return confidence | High | Low | Default to 0.8, graceful fallback |
| Logo looks bad on dark bg | Medium | Low | Test on both modes, use transparency |
| Offline indicator annoying | Low | Low | Only show when actually offline |

## Success Metrics

1. **Theme adoption**: % of users who change from system default
2. **PWA installs**: Number of PWA installations
3. **Offline resilience**: Reduction in error reports when offline
4. **Classification confidence**: Average confidence score (target: >0.75)
5. **Model adoption**: % using recommended models vs llama3.2
