// Client for the real backend API. Endpoints the backend does not serve yet fall back to
// `fallback` (the mock), so the app can move to the real API one endpoint at a time.
import type { ApiClient, DataStatus, Evidence, Report } from './types';

const TIMEOUT_MS = 15_000;

/** An error the screens can show as is. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly code: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export async function request<T>(baseUrl: string, path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(`${baseUrl.replace(/\/$/, '')}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
      signal: controller.signal,
    });
  } catch (error) {
    const timedOut = error instanceof Error && error.name === 'AbortError';
    throw new ApiError(
      timedOut ? 'The server took too long to answer.' : 'Could not reach the server.',
      timedOut ? 'timeout' : 'network',
    );
  } finally {
    clearTimeout(timer);
  }

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    // The backend answers errors as {"error": {"code", "message"}}.
    const error = body?.error;
    throw new ApiError(
      typeof error?.message === 'string' ? error.message : `Request failed (${response.status}).`,
      typeof error?.code === 'string' ? error.code : 'http_error',
      response.status,
    );
  }
  return body as T;
}

export function httpClient(baseUrl: string, fallback: ApiClient): ApiClient {
  return {
    ...fallback,
    getDataStatus: () => request<DataStatus>(baseUrl, '/data/status'),
    getLatestReport: () => request<Report>(baseUrl, '/reports/latest'),
    getEvidence: (id) =>
      request<Evidence>(baseUrl, `/evidence/${encodeURIComponent(id)}`).catch((error: unknown) => {
        // While the chat still runs on mock data, its answers cite mock evidence ids.
        if (error instanceof ApiError && error.status === 404) return fallback.getEvidence(id);
        throw error;
      }),
  };
}
