# Change: Enhance PWA with forced cache updates and push notifications

## Why
Two gaps prevent cairn-mail from behaving like a native mobile app:

1. **Stale cache after deploy** — The PWA uses `registerType: 'autoUpdate'` but the new service worker won't activate until all tabs/windows close. Users on mobile (standalone PWA) may run stale code indefinitely because the standalone window is rarely fully closed. There is no mechanism to force a cache clear and immediate update when we ship a new version.

2. **No push notifications** — Users must have the app open to learn about new emails. Native email apps push notifications even when closed; our PWA should do the same.

## What Changes

### 1. Forced Cache Update on Deploy
- Add a backend `/api/version` endpoint that returns the current build hash
- Inject a build hash into the frontend at build time (Vite `define`)
- The app polls `/api/version` periodically and compares to its embedded hash
- When a mismatch is detected, trigger `skipWaiting` on the waiting service worker and reload the page
- Tie the React Query `buster` to the build hash so IndexedDB cache is also invalidated
- Configure Workbox with `skipWaiting: true` and `clientsClaim: true` for immediate takeover

### 2. Push Notifications for New Emails
- Generate VAPID keys (one-time, stored as agenix secret)
- Backend stores push subscriptions (endpoint, p256dh, auth keys) in SQLite
- During email sync, send Web Push notifications for new high-priority messages
- Service worker handles `push` event to display notification and `notificationclick` to open the message
- Settings UI to enable/disable push and manage subscription
- NixOS/Home-Manager config for VAPID key paths

## Impact
- Affected specs: none existing (new capabilities)
- Affected code:
  - `web/vite.config.ts` — Workbox config, build hash injection
  - `web/src/App.tsx` — version polling, cache buster
  - `web/src/hooks/useWebSocket.ts` or new hook — version check
  - `src/cairn_mail/api/routes/` — version endpoint, push subscription endpoints
  - `src/cairn_mail/db/models.py` — PushSubscription model
  - `src/cairn_mail/sync_engine.py` — trigger push on new messages
  - `modules/home-manager/default.nix` — VAPID key config
  - `modules/nixos/default.nix` — VAPID key path, push settings
  - `flake.nix` — pywebpush dependency

## Supersedes
- `add-pwa-push-notifications` (incomplete stub, no spec deltas)
- Partially overlaps `add-pwa-background-sync` (that proposal covers offline queueing, which remains a separate concern)
