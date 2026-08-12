/**
 * NEXUS SOC — Service Worker (PWA)
 * Stratégie :
 *   - Cache First pour les assets statiques (HTML, CSS, JS, fonts)
 *   - Network First pour les appels API (/auth, /admin, /analyst, /plg, /health)
 *   - Offline fallback pour les pages HTML
 */

// v5 : offline.html liste désormais les pages réellement présentes en cache.
// Cette page n'est servie QUE depuis le cache — sans bump de version, l'ancienne
// copie précachée continuerait d'être affichée indéfiniment.
const CACHE_NAME    = 'nexus-soc-v5';
const OFFLINE_URL   = '/app/offline.html';

// Assets à précacher au premier chargement.
// Les polices en font partie : sans elles, une page servie depuis le cache en
// réseau fermé retombe sur les polices système et perd son identité visuelle.
const PRECACHE_URLS = [
  '/app/',
  '/app/login.html',
  '/app/docs.html',
  '/app/contact.html',
  '/app/console.html',
  '/app/portail.html',
  '/app/offline.html',
  '/app/js/api.js',
  '/app/manifest.json',
  '/app/icons/icon-192.png',
  '/app/icons/icon-512.png',
  '/app/fonts/fonts.css',
  '/app/fonts/fraunces-latin-normal.woff2',
  '/app/fonts/fraunces-latin-italic.woff2',
  '/app/fonts/fraunces-latin-ext-normal.woff2',
  '/app/fonts/fraunces-latin-ext-italic.woff2',
  '/app/fonts/manrope-latin-normal.woff2',
  '/app/fonts/manrope-latin-ext-normal.woff2',
  '/app/fonts/jetbrains-latin-normal.woff2',
  '/app/fonts/jetbrains-latin-ext-normal.woff2',
];

// Préfixes d'URL qui vont vers le réseau (pas de cache)
const API_PREFIXES = ['/auth', '/admin', '/analyst', '/plg', '/health', '/score', '/provision', '/ingest', '/monitor'];

// Sans elle, le mode hors ligne n'a plus de repli du tout : c'est la seule
// ressource dont l'absence doit faire échouer l'installation.
const CRITICAL_URL = OFFLINE_URL;

// ─── Installation ──────────────────────────────────────────────────────────
// addAll() est atomique : un seul 404 (une police renommée, une page retirée)
// ferait échouer tout le précache et priverait la plateforme de son mode hors
// ligne. On met donc en cache ressource par ressource et on tolère les échecs,
// sauf sur la page de repli.
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(async cache => {
      await cache.add(CRITICAL_URL);
      await Promise.all(PRECACHE_URLS.map(url =>
        cache.add(url).catch(err =>
          console.warn('[sw] précache ignoré :', url, err && err.message))));
    }).then(() => self.skipWaiting())
  );
});

// ─── Activation + nettoyage ancien cache ───────────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// ─── Fetch ─────────────────────────────────────────────────────────────────
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Ignorer les requêtes non-GET
  if (event.request.method !== 'GET') return;

  // API → Network First, pas de cache
  const isAPI = API_PREFIXES.some(p => url.pathname.startsWith(p));
  if (isAPI) {
    event.respondWith(networkFirst(event.request));
    return;
  }

  // Shell applicatif (pages HTML + code JS de l'app) → Network First :
  // le code évolue souvent, il ne faut JAMAIS servir une version périmée du
  // cache (sinon les correctifs console/portail n'arrivent jamais au navigateur).
  const isAppShell =
    event.request.mode === 'navigate' ||
    url.pathname.endsWith('.html') ||
    url.pathname.endsWith('.js');
  if (isAppShell) {
    event.respondWith(networkFirstShell(event.request));
    return;
  }

  // Autres assets statiques (icônes, polices, manifest…) → Cache First
  event.respondWith(cacheFirst(event.request));
});

// ─── Stratégies ────────────────────────────────────────────────────────────

async function networkFirstShell(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());   // rafraîchit le cache pour le mode hors-ligne
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;
    if (request.headers.get('accept')?.includes('text/html')) {
      return caches.match(OFFLINE_URL);
    }
    throw new Error('Network error and no cache');
  }
}

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    // Offline : retourner la page offline pour les navigations HTML
    if (request.headers.get('accept')?.includes('text/html')) {
      return caches.match(OFFLINE_URL);
    }
    throw new Error('Network error and no cache');
  }
}

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    // Optionnel : mettre les résultats API en cache court terme (5 min)
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME + '-api');
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request, { cacheName: CACHE_NAME + '-api' });
    if (cached) return cached;
    // Retourner une réponse JSON offline pour les API
    return new Response(JSON.stringify({ detail: 'Hors ligne — données non disponibles.' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}

// ─── Push notifications (optionnel — si notifications push configurées) ──────────────
self.addEventListener('push', event => {
  if (!event.data) return;
  const data = event.data.json();
  event.waitUntil(
    self.registration.showNotification(data.title || 'NEXUS SOC — Alerte', {
      body:    data.body  || 'Un nouvel incident a été détecté.',
      icon:    '/app/icons/icon-192.png',
      badge:   '/app/icons/badge-72.png',
      tag:     data.tag   || 'nexus-alert',
      data:    { url: data.url || '/app/portail.html' },
      actions: [
        { action: 'view',    title: 'Voir l\'alerte' },
        { action: 'dismiss', title: 'Ignorer' },
      ],
    })
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  if (event.action === 'dismiss') return;
  const url = event.notification.data?.url || '/app/portail.html';
  event.waitUntil(
    clients.matchAll({ type: 'window' }).then(windows => {
      const w = windows.find(w => w.url.includes('/app/'));
      if (w) { w.navigate(url); w.focus(); }
      else clients.openWindow(url);
    })
  );
});
