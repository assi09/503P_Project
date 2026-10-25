// Client for the real backend API. Endpoints the backend does not serve yet fall back to
// `fallback` (the mock), so the app can move to the real API one endpoint at a time.
import { getToken } from './token';
import type {
  AccessRequest,
  Account,
  ApiClient,
  ChatMessage,
  Conversation,
  Credentials,
  DataStatus,
  DaySummary,
  Evidence,
  GoogleStatus,
  HealthAction,
  MetricSeries,
  Report,
  SignedIn,
} from './types';

const TIMEOUT_MS = 15_000;
// An answer can take up to a minute; the server stops waiting after about 55 s.
const CHAT_TIMEOUT_MS = 70_000;

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

export async function request<T>(
  baseUrl: string,
  path: string,
  init?: RequestInit,
  timeoutMs = TIMEOUT_MS,
): Promise<T> {
  const token = getToken();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let response: Response;
  try {
    response = await fetch(`${baseUrl.replace(/\/$/, '')}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(token && { Authorization: `Bearer ${token}` }),
        ...init?.headers,
      },
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

function post<T>(baseUrl: string, path: string, body?: unknown, timeoutMs?: number): Promise<T> {
  return request<T>(
    baseUrl,
    path,
    { method: 'POST', ...(body !== undefined && { body: JSON.stringify(body) }) },
    timeoutMs,
  );
}

export function httpClient(baseUrl: string, fallback: ApiClient): ApiClient {
  return {
    ...fallback,
    getActions: () => request<HealthAction[]>(baseUrl, '/actions'),
    getAction: (id) => request<HealthAction>(baseUrl, `/actions/${encodeURIComponent(id)}`),
    proposeAction: (requestKey, log) =>
      post<HealthAction>(baseUrl, '/actions', { requestKey, log }),
    reviseAction: (id, version, log) =>
      post<HealthAction>(baseUrl, `/actions/${encodeURIComponent(id)}/revise`, { version, log }),
    cancelAction: (id, version) =>
      post<HealthAction>(baseUrl, `/actions/${encodeURIComponent(id)}/cancel`, { version }),
    confirmAction: (id, version) =>
      post<HealthAction>(
        baseUrl,
        `/actions/${encodeURIComponent(id)}/confirm`,
        { version },
        30_000,
      ),
    undoAction: (id, version) =>
      post<HealthAction>(baseUrl, `/actions/${encodeURIComponent(id)}/undo`, { version }, 30_000),
    signUp: (credentials: Credentials) => post<SignedIn>(baseUrl, '/auth/signup', credentials),
    logIn: (credentials: Credentials) => post<SignedIn>(baseUrl, '/auth/login', credentials),
    logOut: () => post<void>(baseUrl, '/auth/logout'),
    getAccount: () => request<Account>(baseUrl, '/auth/me'),
    getAccessRequests: () => request<AccessRequest[]>(baseUrl, '/admin/access-requests'),
    decideAccessRequest: (id, approve) =>
      post<Account>(
        baseUrl,
        `/admin/access-requests/${encodeURIComponent(id)}/${approve ? 'approve' : 'reject'}`,
      ),
    getDataStatus: () => request<DataStatus>(baseUrl, '/data/status'),
    getLatestReport: () => request<Report>(baseUrl, '/reports/latest'),
    getDay: (date) => request<DaySummary>(baseUrl, `/days/${encodeURIComponent(date)}`),
    getMetricSeries: (metric, { end, days }) =>
      request<MetricSeries>(
        baseUrl,
        `/metrics/${encodeURIComponent(metric)}?days=${days}${end ? `&end=${end}` : ''}`,
      ),
    getEvidence: (id) => request<Evidence>(baseUrl, `/evidence/${encodeURIComponent(id)}`),
    getChat: (conversationId) =>
      request<ChatMessage[]>(
        baseUrl,
        conversationId ? `/chat?conversation=${encodeURIComponent(conversationId)}` : '/chat',
      ),
    getConversations: () => request<Conversation[]>(baseUrl, '/conversations'),
    createConversation: () => post<Conversation>(baseUrl, '/conversations'),
    renameConversation: (id, title) =>
      request<Conversation>(baseUrl, `/conversations/${encodeURIComponent(id)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title }),
      }),
    deleteConversation: (id) =>
      request<void>(baseUrl, `/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' }),
    getGoogleStatus: () => request<GoogleStatus>(baseUrl, '/google/status'),
    connectGoogle: (capability) =>
      post<{ url: string }>(baseUrl, '/google/connect', capability ? { capability } : undefined),
    syncGoogle: () => post<GoogleStatus>(baseUrl, '/google/sync'),
    disconnectGoogle: () => post<GoogleStatus>(baseUrl, '/google/disconnect'),
    sendMessage: (text, { expert, depth, attachment, conversationId }) =>
      post<ChatMessage[]>(
        baseUrl,
        '/chat',
        { text, expert, depth, attachment, conversationId },
        CHAT_TIMEOUT_MS,
      ),
  };
}
