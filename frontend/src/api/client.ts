let csrfToken: string | null = null;
let sessionEpoch = 0;
const active = new Set<AbortController>();
const unauthorized = new Set<() => void>();

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  constructor(status: number, code: string, message: string) {
    super(message); this.status = status; this.code = code;
  }
}

export function resetSessionContext(token: string | null) {
  sessionEpoch += 1;
  csrfToken = token;
  for (const controller of active) controller.abort();
  active.clear();
}

export function subscribeUnauthorized(listener: () => void) {
  unauthorized.add(listener);
  return () => { unauthorized.delete(listener); };
}

export function invalidateSession() {
  resetSessionContext(null);
  for (const listener of unauthorized) listener();
}

let sessionChannel: BroadcastChannel | null = null;
if (typeof window !== 'undefined') {
  try {
    if ('BroadcastChannel' in window) {
      sessionChannel = new window.BroadcastChannel('homemind-session');
      sessionChannel.onmessage = (event) => { if (event.data === 'changed') invalidateSession(); };
    }
  } catch { /* Sandboxed browsers can use the non-secret storage notification. */ }
  window.addEventListener('storage', (event) => {
    if (event.key === 'homemind-session-event') invalidateSession();
  });
}

export function broadcastSessionChange() {
  if (sessionChannel) sessionChannel.postMessage('changed');
  else {
    try { window.localStorage.setItem('homemind-session-event', crypto.randomUUID()); }
    catch { /* Focus/pageshow revalidation still handles restricted storage. */ }
  }
}

export const isObject = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
export const isText = (v: unknown): v is string => typeof v === 'string' && v.length > 0;
export const isNumber = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);

export async function apiRequest(path: string, method = 'GET', body?: unknown, extraHeaders: Record<string, string> = {}, timeoutMs = 8000): Promise<unknown> {
  const writing = !['GET', 'HEAD'].includes(method);
  if (writing && !csrfToken) throw new ApiError(0, 'csrf_missing', '登录会话尚未就绪，请重新读取登录状态。');
  const epoch = sessionEpoch;
  const controller = new AbortController();
  active.add(controller);
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  try {
    const response = await fetch(`/api${path}`, {
      method, signal: controller.signal, credentials: 'same-origin', cache: 'no-store',
      headers: { Accept: 'application/json', ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
        ...(writing ? { 'X-CSRF-Token': csrfToken! } : {}), ...extraHeaders },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    let data: unknown;
    try { data = await response.json(); } catch { throw new ApiError(response.status, 'invalid_data', '服务返回了无法识别的数据。'); }
    if (epoch !== sessionEpoch) throw new ApiError(0, 'session_changed', '账号会话已切换，本次响应已忽略。');
    if (!response.ok) {
      if (response.status === 401) {
        invalidateSession();
      }
      const detail = isObject(data) && isObject(data.detail) ? data.detail : {};
      throw new ApiError(response.status, isText(detail.code) ? detail.code : 'request_failed',
        isText(detail.message) ? detail.message.slice(0, 240) : '操作未完成，请检查登录状态和输入。');
    }
    return data;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (timedOut) throw new ApiError(0, 'timeout', '请求超时，请先读取当前状态，确认操作是否已生效。');
    if (epoch !== sessionEpoch) throw new ApiError(0, 'session_changed', '账号会话已切换，本次操作已取消。');
    throw new ApiError(0, 'network', '无法连接服务，请检查后端并重试。');
  } finally { clearTimeout(timer); active.delete(controller); }
}
