/**
 * Custom service worker with Workbox precaching + Web Push handling.
 *
 * Uses injectManifest strategy: vite-plugin-pwa injects the precache
 * manifest into self.__WB_MANIFEST at build time.
 */

import { cleanupOutdatedCaches, precacheAndRoute } from 'workbox-precaching'

declare let self: ServiceWorkerGlobalScope

/** Browser fires this when the push service rotates a subscription. */
interface PushSubscriptionChangeEvent extends ExtendableEvent {
  readonly oldSubscription: PushSubscription | null
  readonly newSubscription: PushSubscription | null
}

// ── Workbox precaching ──────────────────────────────────────────────
cleanupOutdatedCaches()
precacheAndRoute(self.__WB_MANIFEST)

// Activate immediately (mirrors skipWaiting + clientsClaim from generateSW)
self.skipWaiting()
self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim())
})

// ── Push notifications ──────────────────────────────────────────────

interface PushPayload {
  title: string
  body: string
  url?: string
  tag?: string
}

self.addEventListener('push', (event) => {
  if (!event.data) return

  let payload: PushPayload
  try {
    payload = event.data.json() as PushPayload
  } catch {
    // Fallback for plain text push
    payload = { title: 'Cairn Mail', body: event.data.text() }
  }

  const options: NotificationOptions = {
    body: payload.body,
    icon: '/icon-192.png',
    badge: '/icon-monochrome.svg',
    tag: payload.tag || 'new-email',
    // Collapse duplicate notifications with the same tag
    renotify: true,
    data: { url: payload.url || '/' },
  }

  event.waitUntil(self.registration.showNotification(payload.title, options))
})

// ── Push subscription renewal ─────────────────────────────────────
// Push services (e.g. Mozilla autopush) periodically rotate subscriptions.
// Without this handler the old endpoint goes stale (410 Gone) and the
// backend never learns the new one, silently breaking notifications.

self.addEventListener('pushsubscriptionchange', ((event: PushSubscriptionChangeEvent) => {
  event.waitUntil(
    (async () => {
      try {
        // Remove old subscription from backend
        if (event.oldSubscription) {
          await fetch('/api/push/unsubscribe', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ endpoint: event.oldSubscription.endpoint }),
          })
        }

        // Use browser-provided renewal, or re-subscribe manually
        let newSub = event.newSubscription
        if (!newSub) {
          const resp = await fetch('/api/push/vapid-key')
          const { publicKey } = await resp.json()

          // Convert base64url VAPID key to ArrayBuffer
          const padding = '='.repeat((4 - (publicKey.length % 4)) % 4)
          const b64 = (publicKey + padding).replace(/-/g, '+').replace(/_/g, '/')
          const raw = atob(b64)
          const key = new Uint8Array(raw.length)
          for (let i = 0; i < raw.length; ++i) key[i] = raw.charCodeAt(i)

          newSub = await self.registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: key.buffer,
          })
        }

        // Register renewed subscription with backend
        const subJson = newSub.toJSON()
        await fetch('/api/push/subscribe', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            endpoint: newSub.endpoint,
            keys: {
              p256dh: subJson.keys?.p256dh ?? '',
              auth: subJson.keys?.auth ?? '',
            },
          }),
        })
      } catch (err) {
        console.error('Failed to renew push subscription:', err)
      }
    })(),
  )
}) as EventListener)

self.addEventListener('notificationclick', (event) => {
  event.notification.close()

  const url = (event.notification.data?.url as string) || '/'

  // Focus existing window if open, otherwise open a new one
  event.waitUntil(
    self.clients
      .matchAll({ type: 'window', includeUncontrolled: true })
      .then((windowClients) => {
        // Try to find an existing window to focus
        for (const client of windowClients) {
          if (client.url.includes(self.registration.scope) && 'focus' in client) {
            client.navigate(url)
            return client.focus()
          }
        }
        // No existing window — open a new one
        return self.clients.openWindow(url)
      }),
  )
})
