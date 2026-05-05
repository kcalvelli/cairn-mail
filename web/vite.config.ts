import { writeFileSync } from 'fs'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// Build ID: changes every build, used for cache invalidation
const buildId = Date.now().toString(36)

// Write build ID to a file so the backend can serve it via /api/version
const writeBuildId = () => ({
  name: 'write-build-id',
  closeBundle() {
    writeFileSync('dist/build-id.json', JSON.stringify({ version: buildId }))
  },
})

// https://vitejs.dev/config/
export default defineConfig({
  define: {
    '__APP_VERSION__': JSON.stringify(buildId),
  },
  plugins: [
    react(),
    writeBuildId(),
    VitePWA({
      strategies: 'injectManifest',
      srcDir: 'src',
      filename: 'sw.ts',
      registerType: 'autoUpdate',
      includeAssets: ['logo.png', 'icon-192.png', 'icon-512.png', 'icon-monochrome.svg'],
      manifest: {
        name: 'Cairn Mail',
        short_name: 'Cairn',
        description: 'AI-powered email client with intelligent classification',
        theme_color: '#1976d2',
        background_color: '#000000',
        display: 'standalone',
        start_url: '/',
        // App shortcuts for quick actions from home screen long-press
        shortcuts: [
          {
            name: 'Compose',
            short_name: 'Compose',
            description: 'Write a new email',
            url: '/compose',
            icons: [{ src: 'icon-192.png', sizes: '192x192' }],
          },
          {
            name: 'Inbox',
            short_name: 'Inbox',
            description: 'View your inbox',
            url: '/?folder=inbox',
            icons: [{ src: 'icon-192.png', sizes: '192x192' }],
          },
        ],
        // Share target to receive shared content from other apps
        share_target: {
          action: '/compose',
          method: 'GET',
          enctype: 'application/x-www-form-urlencoded',
          params: {
            title: 'subject',
            text: 'body',
            url: 'url',
          },
        },
        icons: [
          // Standard icons
          {
            src: 'icon-192.png',
            sizes: '192x192',
            type: 'image/png',
            purpose: 'any',
          },
          {
            src: 'icon-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'any',
          },
          // Maskable icons for adaptive icon shapes
          {
            src: 'icon-192.png',
            sizes: '192x192',
            type: 'image/png',
            purpose: 'maskable',
          },
          {
            src: 'icon-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
          // Monochrome icons for Material You theming on Android 13+
          {
            src: 'icon-monochrome.svg',
            sizes: '192x192',
            type: 'image/svg+xml',
            purpose: 'monochrome',
          },
        ],
      },
      injectManifest: {
        // Static assets to precache (injected into self.__WB_MANIFEST)
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff,woff2}'],
      },
    }),
  ],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8080',
        ws: true,
      },
    },
  },
})
