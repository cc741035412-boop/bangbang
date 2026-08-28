/**
 * 未纳入 openapi 生成类型的接口，用这个轻量 fetch 封装。
 *
 * 为什么不用 apiClient：src/api/generated/schema.d.ts 由后端 openapi.json 生成，
 * 后端还没有这些接口，写进 apiClient 会直接 typecheck 失败。
 *
 * codex：后端接口上线后，跑 `npm run api:generate`，
 * 再把这里的调用逐个换成 apiClient.GET/POST（类型更安全），本文件即可删除。
 */

export class HttpError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly payload?: unknown,
  ) {
    super(message);
    this.name = "HttpError";
  }
}

const TOKEN_KEY = "bangbang.access_token";

export function readToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function writeToken(token: string | null) {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    // 隐私模式下 localStorage 不可写，忽略即可，登录态退化为单次会话
  }
}

function authHeaders(): Record<string, string> {
  const token = readToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function parseError(response: Response, fallback: string) {
  let payload: unknown;
  let message = fallback;
  try {
    payload = await response.json();
    const detail = (payload as { detail?: unknown })?.detail;
    if (typeof detail === "string" && detail.trim()) message = detail;
  } catch {
    // 后端没返回 JSON，用兜底文案
  }
  return new HttpError(response.status, message, payload);
}

export async function requestJson<T>(
  path: string,
  init: RequestInit & { fallbackMessage: string },
): Promise<T> {
  const { fallbackMessage, headers, ...rest } = init;
  const response = await fetch(`/api${path}`, {
    ...rest,
    headers: {
      ...(rest.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...authHeaders(),
      ...headers,
    },
  });
  if (!response.ok) throw await parseError(response, fallbackMessage);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function requestBlob(
  path: string,
  fallbackMessage: string,
): Promise<{ blob: Blob; fileName: string }> {
  const response = await fetch(`/api${path}`, { headers: authHeaders() });
  if (!response.ok) throw await parseError(response, fallbackMessage);
  return { blob: await response.blob(), fileName: fileNameFromResponse(response) };
}

/** 从 Content-Disposition 取文件名，兼容 RFC 5987 的 UTF-8 编码写法 */
export function fileNameFromResponse(response: Response, fallback = "download") {
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  if (encoded) {
    try {
      return decodeURIComponent(encoded);
    } catch {
      // header 损坏时退回 ASCII 文件名
    }
  }
  return disposition.match(/filename="?([^";]+)"?/i)?.[1] ?? fallback;
}
