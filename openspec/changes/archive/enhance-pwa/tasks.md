# Implementation Tasks

## 1. Forced Cache Update on Deploy

- [x] 1.1 Add `GET /api/version` endpoint to backend
  - Return `{ "version": "<build_hash>" }` from a constant embedded at build time
  - Use git short SHA or Nix store hash, injected via Vite `define` and Python package metadata

- [x] 1.2 Inject build hash into frontend via Vite `define`
  - Add `define: { '__APP_VERSION__': JSON.stringify(hash) }` to `vite.config.ts`
  - Source hash from `package.json` version + git SHA, or environment variable set by Nix build

- [x] 1.3 Configure Workbox with `skipWaiting` and `clientsClaim`
  - Add `skipWaiting: true` and `clientsClaim: true` to workbox config in `vite.config.ts`

- [x] 1.4 Add version polling hook (`useVersionCheck`)
  - Poll `GET /api/version` every 5 minutes
  - Compare response to `__APP_VERSION__`
  - On mismatch, call `window.location.reload()`
  - Skip polling when offline

- [x] 1.5 Tie React Query cache buster to build version
  - Change `buster: 'v1'` to `buster: __APP_VERSION__` in `App.tsx`
  - Add `declare const __APP_VERSION__: string` type declaration

## 2. Push Notification Infrastructure

- [x] 2.1 Add `pywebpush` to Python dependencies
  - Add to `flake.nix` propagatedBuildInputs
  - Build/overlay pywebpush if not in nixpkgs

- [x] 2.2 Add VAPID key configuration to Nix modules
  - `programs.cairn-mail.push.vapidPrivateKeyFile` (path to agenix secret)
  - `programs.cairn-mail.push.vapidPublicKey` (string, safe to store in config)
  - `programs.cairn-mail.push.contactEmail` (mailto: for VAPID claims)
  - Pass values into `config.yaml`

- [x] 2.3 Add `PushSubscription` model to `db/models.py`
  - Fields: id, endpoint (unique), p256dh, auth, created_at, last_used_at
  - Index on endpoint for lookups

- [x] 2.4 Add database methods for push subscriptions
  - `upsert_push_subscription(endpoint, p256dh, auth)`
  - `delete_push_subscription(endpoint)`
  - `get_all_push_subscriptions()`
  - `update_push_subscription_last_used(endpoint)`

## 3. Push Notification API

- [x] 3.1 Add `GET /api/push/vapid-key` endpoint
  - Return VAPID public key from config

- [x] 3.2 Add `POST /api/push/subscribe` endpoint
  - Accept subscription object (endpoint, keys.p256dh, keys.auth)
  - Upsert into database

- [x] 3.3 Add `DELETE /api/push/unsubscribe` endpoint
  - Accept endpoint URL
  - Remove from database

## 4. Push Notification Sending

- [x] 4.1 Create `push_service.py` module
  - `send_push(subscription, payload)` using pywebpush
  - Handle errors: remove subscription on 404/410, log others
  - `notify_new_messages(messages)` — build payload and send to all subscriptions

- [x] 4.2 Integrate push sending into sync engine
  - After new messages are processed, call `notify_new_messages()`
  - Only send for genuinely new messages (not reclassifications)
  - Batch: send one notification per message, up to 5 per sync cycle
  - Integrated in both API sync route and CLI sync command

## 5. Service Worker Push Handling

- [x] 5.1 Switch from generated SW to custom service worker source
  - Use vite-plugin-pwa `injectManifest` strategy
  - Add custom `push` and `notificationclick` event handlers
  - Keep all existing Workbox precaching behavior via `precacheAndRoute(self.__WB_MANIFEST)`

- [x] 5.2 Handle `push` event
  - Parse payload JSON
  - Display notification with title, body, icon, tag
  - Use `tag` field to collapse multiple notifications

- [x] 5.3 Handle `notificationclick` event
  - Open app at the message URL from payload
  - Focus existing window if already open

## 6. Frontend Push Settings

- [x] 6.1 Add push notification toggle to Settings page
  - Check current permission state (`Notification.permission`)
  - Toggle to enable: request permission → subscribe → POST to backend
  - Toggle to disable: unsubscribe → DELETE from backend
  - Show info message if permission denied
  - Added as new "Notifications" tab in Settings

- [x] 6.2 Add `usePushSubscription` hook
  - Manage subscription lifecycle (subscribe/unsubscribe)
  - Fetch VAPID key from backend
  - Track permission and subscription state

## 7. Cleanup

- [x] 7.1 Remove superseded `add-pwa-push-notifications` proposal
- [x] 7.2 Update `add-pwa-background-sync` proposal to note it is independent of this work
