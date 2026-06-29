import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';
import path from 'path';

export default defineConfig({
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      // Demo build: no PWA/offline. Emit a self-destroying service worker so
      // any SW already registered in browsers unregisters itself and clears
      // its caches (fixes stale bundle serving the old duckdns base URL).
      selfDestroying: true,
      devOptions: {
        enabled: false,
      },
      manifest: {
        name: 'OpenSplit',
        short_name: 'OpenSplit',
        description: 'Sistema de cobros y repartos Lightning Network',
        theme_color: '#FF2D78',
        background_color: '#0A0B12',
        display: 'standalone',
        start_url: '/',
        icons: [
          {
            src: '/brand/OpenSplitlogo.svg',
            sizes: 'any',
            type: 'image/svg+xml',
            purpose: 'any maskable',
          },
        ],
      },
      workbox: {
        runtimeCaching: [
          {
            urlPattern: /^\/api\/v1\/.*/i,
            handler: 'NetworkFirst',
            options: {
              networkTimeoutSeconds: 5,
              cacheName: 'api-cache',
              expiration: {
                maxEntries: 100,
                maxAgeSeconds: 60,
              },
            },
          },
          {
            urlPattern: /\.(?:png|jpg|jpeg|svg|gif|webp|ico|woff2?)$/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'static-assets',
              expiration: {
                maxEntries: 100,
                maxAgeSeconds: 60 * 60 * 24 * 30,
              },
            },
          },
        ],
      },
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
});
