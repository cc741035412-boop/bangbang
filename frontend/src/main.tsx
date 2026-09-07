import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";

import { AppProviders } from "./app/providers";
import { AppRoutes } from "./app/routes";
import "./styles/index.css";

const root = document.getElementById("root");

if (!root) {
  throw new Error("找不到应用挂载节点 #root");
}

createRoot(root).render(
  <StrictMode>
    <AppProviders>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AppProviders>
  </StrictMode>,
);

// PWA：仅生产环境注册离线壳 Service Worker，开发环境交给 Vite HMR，不干预。
if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // 注册失败不阻断使用（例如不支持 SW 的浏览器或受限网络）。
    });
  });
}
