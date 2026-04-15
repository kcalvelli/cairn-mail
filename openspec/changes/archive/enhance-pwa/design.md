## Context

cairn-mail is a PWA served from a NixOS systemd service. The frontend is built by Nix (`buildNpmPackage`) and bundled into the Python package as static assets. Deploys happen via `nixos-rebuild switch`, which replaces the Nix store path and restarts the systemd service. The new files are immediately available on the server, but the PWA client continues serving from its service worker cache until the SW lifecycle completes.

The app is accessed via Tailscale Serve (HTTPS) on mobile devices where it is installed as a standalone PWA. In standalone mode, the PWA window is rarely fully closed on mobile, so the "waiting" service worker may never activate.

## Goals / Non-Goals

### Goals
- **Immediate update**: When a new version is deployed, active clients detect it and update within minutes — no manual cache clear required
- **Zero-interaction update**: The update happens automatically without user prompts (the app is single-user, no risk of disrupting others)
- **Push notifications**: New emails trigger a push notification on mobile even when the PWA is not open
- **Privacy-first**: VAPID keys are self-hosted; push payloads contain only sender name and subject (no email body)

### Non-Goals
- Offline operation / background sync (separate proposal)
- Per-tag notification filtering (future enhancement)
- Quiet hours / do-not-disturb scheduling (future)
- Rich notification actions beyond click-to-open (future)

## Decisions

### Cache Update Strategy: skipWaiting + version polling

**Decision**: Configure Workbox with `skipWaiting: true` and `clientsClaim: true`, plus a version-polling mechanism as a safety net.

**How it works**:
1. Each build produces a unique hash (git short SHA or Vite build hash)
2. The hash is embedded in the frontend via Vite `define` (`__APP_VERSION__`)
3. The same hash is served by `GET /api/version`
4. `skipWaiting: true` means new service workers activate immediately after install, without waiting for old clients to close
5. `clientsClaim: true` means the new SW claims all open clients immediately
6. The frontend polls `/api/version` every 5 minutes; on mismatch, it calls `window.location.reload()` to pick up the new SW and assets
7. The React Query `buster` is set to `__APP_VERSION__` so IndexedDB cache is invalidated on version change

**Alternatives considered**:
- *Prompt-based update* (show "Update available" banner) — Rejected: single-user app, no reason to delay updates
- *`autoUpdate` with `onNeedRefresh`* — The vite-plugin-pwa `autoUpdate` mode already calls `skipWaiting`, but it relies on `navigator.serviceWorker.oncontrollerchange` which can be unreliable in standalone PWA mode. Version polling is more robust.
- *Server-sent version via WebSocket* — Would work but adds coupling to the WebSocket lifecycle; polling is simpler and works even if the WebSocket is disconnected

### Push Notification Architecture: VAPID + pywebpush

**Decision**: Use Web Push with VAPID keys, `pywebpush` on the backend, and the Push API in the service worker.

**How it works**:
1. VAPID keys generated once via `pywebpush.webpush.generate_vapid_keys()` or `openssl`
2. Private key stored as an agenix secret; public key served via `GET /api/push/vapid-key`
3. Frontend requests push permission and subscribes via `PushManager.subscribe()`
4. Subscription (endpoint, p256dh, auth) sent to `POST /api/push/subscribe` and stored in SQLite
5. During sync, when new messages arrive, backend sends push via `pywebpush` to all active subscriptions
6. Service worker `push` event handler displays notification
7. `notificationclick` event opens the app at the message URL

**Push payload** (kept minimal for privacy):
```json
{
  "title": "New email from John Doe",
  "body": "Re: Meeting tomorrow",
  "url": "/?message=abc123",
  "tag": "new-email"
}
```

**Subscription cleanup**: Expired or invalid subscriptions (HTTP 404/410 from push service) are automatically removed.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| `skipWaiting` could break in-flight requests | API routes use `NetworkOnly` — never served from cache. Only static assets change, and those are content-hashed by Vite |
| Version polling adds HTTP requests | One lightweight JSON request every 5 minutes is negligible |
| Push subscription stored in SQLite (single device concern) | This is a single-user app — one user, one or two devices. SQLite is sufficient |
| VAPID key rotation | Not planned; if needed, delete subscriptions and re-subscribe |

## Open Questions

- None — both features are well-understood web platform capabilities with clear implementation paths
