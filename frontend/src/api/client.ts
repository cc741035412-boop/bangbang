import createClient from "openapi-fetch";

import { readToken } from "./http";
import type { paths } from "./generated/schema";

export const apiClient = createClient<paths>({ baseUrl: "/api" });

// 统一在 apiClient 请求里注入登录 token，保证后端能按当前教师班级过滤数据。
// openapi-fetch 中间件：发请求前把 Authorization 头带上，与 http.ts 的 authHeaders 一致。
apiClient.use({
  onRequest({ request }) {
    const token = readToken();
    if (token) request.headers.set("Authorization", `Bearer ${token}`);
  },
});
