const CACHE_NAME = "racex-shell-v2";
const OFFLINE_URL = "/offline";
const OFFLINE_FALLBACK = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#103b32">
  <title>You’re offline · RaceX</title>
  <style>
    *{box-sizing:border-box}body{min-height:100vh;display:grid;place-items:center;margin:0;padding:1.5rem;background:#f3f0e8;color:#18221f;font-family:system-ui,sans-serif}
    main{width:min(100%,32rem);padding:clamp(1.5rem,6vw,3rem);border:1px solid #d7d8ca;background:#fbfaf5;box-shadow:0 14px 34px #103b3217}
    .mark{display:grid;place-items:center;width:3rem;height:3rem;border-radius:.7rem;color:#fff;background:#103b32;font-weight:800}
    p{color:#65736d;line-height:1.55}button{min-height:2.75rem;margin-top:.5rem;padding:.8rem 1rem;border:0;color:#fff;background:#c96f3b;font-weight:700}
  </style>
</head>
<body><main><span class="mark">RX</span><p>RACEX ANALYSIS DESK</p><h1>You’re offline</h1>
<p>Reconnect to the internet to load meetings and race analysis. Race data is not stored for offline use.</p>
<form action="/offline" method="get"><button type="submit">Try again</button></form></main></body>
</html>`;

function offlineResponse() {
  return new Response(OFFLINE_FALLBACK, {
    headers: { "Content-Type": "text/html; charset=utf-8" },
  });
}

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);
    const homeUrl = new URL("/", self.location.origin);
    const offlineUrl = new URL(OFFLINE_URL, self.location.origin);
    const [homeResponse, offlineResponse] = await Promise.all([
      fetch(homeUrl, { cache: "reload" }),
      fetch(offlineUrl, { cache: "reload" }),
    ]);

    if (!homeResponse.ok || !offlineResponse.ok) {
      throw new Error("Unable to cache the RaceX app shell.");
    }

    await Promise.all([
      cache.put(homeUrl, homeResponse.clone()),
      cache.put(offlineUrl, offlineResponse.clone()),
    ]);

    const offlineHtml = await offlineResponse.text();
    const stylesheetUrls = [...offlineHtml.matchAll(/href="([^"]+\.css(?:\?[^"]*)?)"/g)]
      .map((match) => new URL(match[1], self.location.origin))
      .filter((url) => url.origin === self.location.origin);

    await Promise.all(stylesheetUrls.map(async (url) => {
      const response = await fetch(url);
      if (response.ok) await cache.put(url, response);
    }));
  })());

  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const cacheNames = await caches.keys();
    await Promise.all(cacheNames
      .filter((name) => name.startsWith("racex-shell-") && name !== CACHE_NAME)
      .map((name) => caches.delete(name)));
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const requestUrl = new URL(request.url);

  if (request.method !== "GET" || requestUrl.origin !== self.location.origin) return;

  if (request.mode === "navigate") {
    event.respondWith((async () => {
      try {
        const response = await fetch(request);
        if (response.ok && ["/", OFFLINE_URL].includes(requestUrl.pathname)) {
          const cache = await caches.open(CACHE_NAME);
          await cache.put(requestUrl, response.clone());
        }
        return response;
      } catch {
        const cache = await caches.open(CACHE_NAME);
        return await cache.match(request, { ignoreSearch: true })
          ?? await cache.match(new URL(OFFLINE_URL, self.location.origin))
          ?? offlineResponse();
      }
    })());
    return;
  }

  if (requestUrl.pathname.startsWith("/_next/static/")) {
    event.respondWith((async () => {
      const cache = await caches.open(CACHE_NAME);
      const cachedResponse = await cache.match(request);
      if (cachedResponse) return cachedResponse;

      const response = await fetch(request);
      if (response.ok) await cache.put(request, response.clone());
      return response;
    })());
  }
});
