import { httpError, malformedError, offlineError, timeoutError } from "./errors";

export interface ApiClientOptions {
  baseUrl: string;
  getToken: () => Promise<string | null>;
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
}

export type ApiClient = <T>(path: string, init?: { method?: "GET" | "POST"; body?: unknown }) => Promise<T>;

// The only place that talks HTTP. The token is attached here and never logged or put in errors.
export function createApiClient({ baseUrl, getToken, fetchImpl = fetch, timeoutMs = 20000 }: ApiClientOptions): ApiClient {
  const root = baseUrl.replace(/\/+$/, "");
  return async function request<T>(path: string, init: { method?: "GET" | "POST"; body?: unknown } = {}): Promise<T> {
    const headers: Record<string, string> = { Accept: "application/json" };
    const token = await getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    if (init.body !== undefined) headers["Content-Type"] = "application/json";

    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeoutMs);

    let response: Response;
    try {
      response = await fetchImpl(`${root}/api/v1${path}`, {
        method: init.method ?? "GET",
        headers,
        body: init.body === undefined ? undefined : JSON.stringify(init.body),
        signal: controller.signal,
      });
    } catch {
      throw timedOut ? timeoutError() : offlineError();
    } finally {
      clearTimeout(timer);
    }

    let body: unknown = null;
    const raw = await response.text().catch(() => "");
    if (raw) {
      try {
        body = JSON.parse(raw);
      } catch {
        if (response.ok) throw malformedError();
      }
    }
    if (!response.ok) {
      const detail = body && typeof body === "object" && "detail" in body ? (body as { detail: unknown }).detail : null;
      throw httpError(response.status, detail);
    }
    return body as T;
  };
}

const PRIVATE_HOST = /^(localhost|127\.\d+\.\d+\.\d+|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|[\w-]+\.local)$/i;

// HTTPS is required, except plain HTTP to a local/LAN development server.
export function validateBaseUrl(input: string): { url: string } | { error: string } {
  const trimmed = input.trim().replace(/\/+$/, "");
  const match = /^(https?):\/\/([^/:?#]+)(:\d+)?(\/[^?#]*)?$/i.exec(trimmed);
  if (!match) return { error: "Enter a full address, for example https://progresssync.example.com" };
  const [, scheme, host] = match;
  if (scheme.toLowerCase() === "http" && !PRIVATE_HOST.test(host)) {
    return { error: "Use HTTPS. Plain HTTP is only allowed for a local development server." };
  }
  return { url: trimmed };
}
