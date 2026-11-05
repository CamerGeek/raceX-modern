const CACHE_VERSION = "racex-shell-v3";
const SHELL_CACHE = CACHE_VERSION;
const PAGE_CACHE = `${CACHE_VERSION}-pages`;
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const OFFLINE_URL = "/offline";

const PRECACHE_URLS = [
  "/",
  OFFLINE_URL,
  "/manifest.webmanifest",
  "/icon.svg",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/maskable-192.png",
  "/icons/maskable-512.png",
  "/apple-touch-icon.png",
  "/favicon.ico",
];

const OFFLINE_FALLBACK = `<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#103b32">
  <title>RaceX · Hors ligne</title>
  <style>
    *{box-sizing:border-box}body{min-height:100vh;display:grid;place-items:center;margin:0;padding:1.5rem;background:#f3f0e8;color:#18221f;font-family:system-ui,sans-serif}
    main{width:min(100%,32rem);padding:clamp(1.5rem,6vw,3rem);border:1px solid #d7d8ca;background:#fbfaf5;box-shadow:0 14px 34px #103b3217}
    .mark{display:grid;place-items:center;width:3rem;height:3rem;border-radius:.7rem;color:#fff;background:#103b32;font-weight:800}
    .kicker{margin:.9rem 0 .2rem;color:#1d594b;font-size:.7rem;font-weight:700;letter-spacing:.12em}
    p{color:#65736d;line-height:1.55}button{min-height:2.75rem;margin-top:.5rem;padding:.8rem 1rem;border:0;color:#fff;background:#c96f3b;font-weight:700;cursor:pointer}
    a{color:#1d594b;font-weight:700}
    .lang{display:none}
    html[data-lang="fr"] .lang-fr,html[data-lang="en"] .lang-en,html[data-lang="es"] .lang-es{display:block}
  </style>
</head>
<body>
<main>
  <span class="mark">RX</span>
  <p class="kicker">RACEX</p>
  <div class="lang lang-fr"><h1>Vous êtes hors ligne</h1><p>Reconnectez-vous à Internet pour charger les nouvelles analyses. Vos dernières données enregistrées restent consultables sur cet appareil.</p></div>
  <div class="lang lang-en"><h1>You’re offline</h1><p>Reconnect to the internet to load new analysis. Your last saved data is still available on this device.</p></div>
  <div class="lang lang-es"><h1>Estás sin conexión</h1><p>Vuelve a conectarte a Internet para cargar nuevos análisis. Tus últimos datos guardados siguen disponibles en este dispositivo.</p></div>
  <form action="${OFFLINE_URL}" method="get"><button type="submit">↻</button></form>
  <p><a href="/">RaceX</a></p>
</main>
<script>
  (function () {
    var language = (navigator.language || "fr").slice(0, 2).toLowerCase();
    document.documentElement.lang = language;
    document.documentElement.dataset.lang = ["fr", "en", "es"].indexOf(language) >= 0 ? language : "fr";
  })();
</script>
</body>
</html>`;

function offlineResponse() {
  return new Response(OFFLINE_FALLBACK, {
    headers: { "Content-Type": "text/html; charset=utf-8" },
  });
}

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(SHELL_CACHE);
    await Promise.all(PRECACHE_URLS.map(async (url) => {
      try {
        const response = await fetch(new Request(url, { cache: "reload" }));
        if (response.ok) await cache.put(url, response);
      } catch {
        // A missing optional asset must not block the install.
      }
    }));
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const cacheNames = await caches.keys();
    await Promise.all(cacheNames
      .filter((name) => name.startsWith("racex-") && name !== SHELL_CACHE && name !== PAGE_CACHE && name !== STATIC_CACHE)
      .map((name) => caches.delete(name)));
    await self.clients.claim();
  })());
});

async function networkFirstNavigation(request) {
  const cache = await caches.open(PAGE_CACHE);
  try {
    const response = await fetch(request);
    if (response.ok) await cache.put(request, response.clone());
    return response;
  } catch {
    const cached = await cache.match(request, { ignoreSearch: true });
    if (cached) return cached;
    const shell = await caches.open(SHELL_CACHE);
    return await shell.match(new URL(OFFLINE_URL, self.location.origin))
      ?? await shell.match(new URL("/", self.location.origin))
      ?? offlineResponse();
  }
}

async function networkFirstData(request) {
  const cache = await caches.open(PAGE_CACHE);
  try {
    const response = await fetch(request);
    if (response.ok) await cache.put(request, response.clone());
    return response;
  } catch {
    return await cache.match(request, { ignoreSearch: true })
      ?? new Response("", { status: 504, statusText: "Offline" });
  }
}

async function cacheFirstStatic(request) {
  const cache = await caches.open(STATIC_CACHE);
  const cached = await cache.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) await cache.put(request, response.clone());
  return response;
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const requestUrl = new URL(request.url);

  if (request.method !== "GET" || requestUrl.origin !== self.location.origin) return;
  if (requestUrl.pathname.startsWith("/api/")) return;

  if (request.mode === "navigate") {
    event.respondWith(networkFirstNavigation(request));
    return;
  }

  if (requestUrl.searchParams.has("_rsc") || request.headers.get("RSC") === "1") {
    event.respondWith(networkFirstData(request));
    return;
  }

  const isStaticAsset = requestUrl.pathname.startsWith("/_next/static/")
    || requestUrl.pathname.startsWith("/icons/")
    || requestUrl.pathname.startsWith("/images/")
    || ["style", "script", "font", "image"].includes(request.destination);
  if (isStaticAsset) {
    event.respondWith(cacheFirstStatic(request));
  }
});
