/* 帮帮师记 —— 基础离线壳 Service Worker
 *
 * 只缓存应用外壳（HTML / 静态资源 / 图标 / manifest），让已安装的 PWA 在
 * 断网时仍能打开界面；绝不缓存 /api 数据，也不把读写请求伪装成离线可用，
 * 避免给教师看到一份「看似能看、实际是旧数据」的假离线状态。
 */
const CACHE_NAME = "bangbang-shell-v1";
const SHELL = [
  "/",
  "/index.html",
  "/manifest.webmanifest",
  "/icon-192.png",
  "/icon-512.png",
  "/icon-maskable-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key !== CACHE_NAME)
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;

  // 只处理同源 GET；写操作与 API 一律交给浏览器默认网络行为。
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/")) return;

  // 页面导航：优先网络，断网时回退到缓存的 app 壳。
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put("/index.html", copy));
          return response;
        })
        .catch(() => caches.match("/index.html")),
    );
    return;
  }

  // 静态资源：缓存优先 + 后台更新（stale-while-revalidate）。
  event.respondWith(
    caches.match(request).then((cached) => {
      const network = fetch(request)
        .then((response) => {
          if (response && response.status === 200) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => cached);
      return cached || network;
    }),
  );
});
