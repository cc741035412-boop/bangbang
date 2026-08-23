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
