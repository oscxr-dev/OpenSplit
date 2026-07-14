import './styles/globals.css';
import '@/i18n';

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';

if (import.meta.env.DEV && 'serviceWorker' in navigator) {
  void navigator.serviceWorker
    .getRegistrations()
    .then((registrations) => Promise.all(registrations.map((registration) => registration.unregister())))
    .catch(() => undefined);
}

if (import.meta.env.DEV && 'caches' in window) {
  void caches
    .keys()
    .then((cacheNames) => Promise.all(cacheNames.map((cacheName) => caches.delete(cacheName))))
    .catch(() => undefined);
}

const rootElement = document.getElementById('root');
if (!rootElement) throw new Error('Root element not found');

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>
);
