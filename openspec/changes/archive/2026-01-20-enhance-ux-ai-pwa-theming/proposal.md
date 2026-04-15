# Change: Phase 8 - AI Classification Improvements, Branding, PWA & Theme

## Why

After completing email composition and sending functionality (Phase 7), cairn-mail is now a functional email client. However, several areas need improvement to enhance user experience and deliver on the promise of intelligent email management:

**AI Classification Pain Points:**
- Current model recommendation (llama3.2) may not be optimal for all users
- No guidance on model selection for different hardware constraints
- Classification quality varies and users have no way to tune it
- No confidence scores to indicate classification certainty

**Branding & Visual Identity:**
- No logo or brand identity visible in the application
- Inconsistent visual styling between sidebar and topbar
- Application looks generic and unfinished

**PWA & Offline Experience:**
- Application cannot be installed as a standalone app
- No offline awareness (users see confusing errors when offline)
- Mobile experience suffers without PWA features
- No manifest or service worker for installability

**Theme Preferences:**
- No way to switch between light and dark mode
- Users with different lighting conditions or preferences are stuck with default theme
- Dark mode is increasingly expected in modern applications

**Business Impact:**
Without these improvements, cairn-mail feels like a technical proof-of-concept rather than a polished product. Users who prefer dark mode, want to install as an app, or need better AI recommendations will find the experience lacking.

## What Changes

### 1. AI Classification Improvements

**Bug Fix - Custom Tags Not Loaded:**
- Currently, tags defined in Nix config (`ai.tags`) are written to config.yaml but never read
- ConfigLoader only syncs `accounts` section, ignoring `ai` section entirely
- Fix: Update ConfigLoader to read `ai` config and pass to sync operations
- Fix: Update sync.py to pass custom_tags to AIConfig

**Model Recommendations:
- Document recommended models for different hardware tiers:
  - **Low-end (4GB RAM):** phi3:mini (3.8B parameters) - Fast, good quality
  - **Mid-range (8GB RAM):** mistral:7b - Excellent balance of quality and speed
  - **High-end (16GB+ RAM):** llama3.1:8b - Best classification quality
- Add model selection guidance in settings documentation
- Update default from llama3.2 to phi3:mini for broader compatibility

**Classification Confidence:**
- Return confidence score (0.0-1.0) from LLM
- Display confidence indicator in UI (high/medium/low)
- Allow filtering by classification confidence
- Log low-confidence classifications for debugging

**Custom Tag Descriptions:**
- Allow users to customize tag descriptions via Nix config
- Document how to add domain-specific tags
- Example: "project-alpha" for specific project emails

### 2. Branding

**Logo Integration:**
- Add cairn-mail logo to topbar (left side)
- Logo as PNG asset: `/web/public/cairn-mail.png`
- Alt text and title for accessibility
- Link logo to homepage (/)

**Visual Consistency:**
- Unify sidebar and topbar background colors
- Both use MUI `primary.main` color (or themed variant)
- Consistent spacing and elevation across navigation
- Cohesive visual identity throughout app

### 3. Progressive Web App (PWA)

**Manifest Configuration:**
- Create `manifest.json` with app metadata
- App name: "Cairn AI Mail"
- Short name: "Mail"
- Theme color matching brand
- Icons at multiple resolutions (192x192, 512x512)
- Display mode: "standalone"
- Start URL: "/"

**Installability:**
- Configure Vite PWA plugin
- Service worker for caching static assets
- "Add to Home Screen" prompt support
- Installed app opens without browser chrome

**Offline Awareness:**
- Detect online/offline status
- Show offline indicator in UI (banner or icon)
- Disable actions that require network when offline
- Queue operations for when connectivity returns (optional)
- Graceful error messages for network failures

### 4. Light/Dark Mode Toggle

**Theme Toggle:**
- Add theme toggle button in topbar (sun/moon icon)
- Persist preference in localStorage
- Support system preference detection (`prefers-color-scheme`)
- Three modes: Light, Dark, System (auto)

**MUI Theme Configuration:**
- Configure MUI ThemeProvider with both light and dark palettes
- Consistent brand colors in both themes
- Proper contrast ratios for accessibility
- Custom component styling for both modes

**Implementation:**
- Create ThemeContext for global theme state
- Toggle component with smooth transition
- Settings page option for detailed preference (future)

## Impact

### Affected Capabilities
- `ai-classifier` (MODIFIED) - Confidence scores, model recommendations
- `web-ui` (MODIFIED) - Branding, theme toggle, offline indicator
- `pwa` (NEW) - Manifest, service worker, installability
- `theming` (NEW) - Light/dark mode support

### Affected Code

**New:**
- `web/public/manifest.json` - PWA manifest
- `web/public/cairn-mail.png` - Logo (192x192)
- `web/public/cairn-mail-512.png` - Logo (512x512)
- `web/src/contexts/ThemeContext.tsx` - Theme state management
- `web/src/components/ThemeToggle.tsx` - Theme toggle button
- `web/src/components/OfflineIndicator.tsx` - Offline status
- `web/src/hooks/useOnlineStatus.ts` - Online detection hook

**Modified:**
- `src/cairn_mail/ai_classifier.py` - Add confidence extraction
- `src/cairn_mail/api/routes/messages.py` - Return confidence in response
- `web/src/main.tsx` - ThemeProvider wrapper, service worker registration
- `web/src/components/Layout.tsx` - Logo, unified colors, theme toggle
- `web/src/components/Sidebar.tsx` - Background color consistency
- `web/vite.config.ts` - PWA plugin configuration
- `web/index.html` - Manifest link, theme-color meta tag
- `modules/home-manager/default.nix` - Model recommendation docs, custom tags option

## Breaking Changes

**None** - All changes are additive or opt-in:
- Default model change (phi3:mini) is a recommendation, not forced
- Theme defaults to system preference (no visual change for most users)
- PWA features are progressive enhancements

## User-Facing Changes

### Before
- No logo or brand identity
- Inconsistent navigation styling
- Cannot install as app
- No offline awareness (confusing errors)
- No theme preference (light mode only)
- No model guidance (users guess)
- No confidence indication

### After
- **Branded experience** with logo in topbar
- **Cohesive design** with unified navigation colors
- **Installable PWA** on desktop and mobile
- **Offline indicator** shows connection status clearly
- **Theme toggle** for light/dark/system preference
- **Model recommendations** for different hardware
- **Confidence scores** on classifications

## Dependencies

**Required:**
- Phase 7 (Email Composition) - Complete (provides stable UI foundation)

**External Libraries:**
- `vite-plugin-pwa` - Service worker generation and manifest
- `workbox-precaching` - Asset caching strategies (included with vite-plugin-pwa)
- No new backend dependencies

## Out of Scope (Future Phases)

- Classification retraining or feedback loop
- Multiple custom themes (just light/dark for now)
- Full offline mode with local data persistence
- Push notifications
- Background sync
- Model fine-tuning or custom model training
- Per-account theme settings

## Security Considerations

1. **Service Worker**: Only cache static assets, not API responses
2. **Theme Storage**: localStorage only, no sensitive data
3. **Offline Actions**: Disable sensitive operations when offline
4. **Logo Assets**: Use static assets, not external URLs

## Performance Considerations

1. **Service Worker Caching**: Improves repeat load times significantly
2. **Theme Toggle**: CSS custom properties for instant theme switching
3. **Confidence Scores**: Minimal overhead (already in LLM response)
4. **Offline Detection**: Event-based, not polling

## Testing Strategy

### Unit Tests
- Theme context toggle functionality
- Online status hook behavior
- Confidence score parsing

### Integration Tests
- Theme persistence across sessions
- PWA manifest validation
- Service worker registration

### Manual Testing Checklist
- [ ] Install PWA on Chrome desktop
- [ ] Install PWA on mobile Safari
- [ ] Toggle theme and verify persistence
- [ ] Disconnect network and verify offline indicator
- [ ] Verify logo displays correctly
- [ ] Test with phi3:mini model
- [ ] Test with mistral:7b model
- [ ] Verify confidence scores in message list/detail

## Migration Plan

### Phase 1: Theme Infrastructure (Non-Visual)
1. Add ThemeContext and ThemeToggle component
2. Configure MUI dark theme palette
3. No visible changes yet (default: system preference)

### Phase 2: PWA Setup
1. Add manifest.json and icons
2. Configure vite-plugin-pwa
3. Add service worker registration
4. Test installability

### Phase 3: Visual Updates
1. Add logo to topbar
2. Unify sidebar/topbar colors
3. Add theme toggle to UI
4. Add offline indicator

### Phase 4: AI Improvements
1. Update AI classifier for confidence scores
2. Update API responses to include confidence
3. Update UI to display confidence
4. Document model recommendations

### Rollback Plan
- Theme toggle can be hidden via feature flag
- PWA can be disabled by removing manifest link
- Branding changes are purely visual (easy revert)
- Confidence scores are additive (old clients ignore)
