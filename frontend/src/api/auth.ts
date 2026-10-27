import { apiRequest, broadcastSessionChange, isObject, isText, resetSessionContext } from './client';
import type { AuthSession, Credentials } from './auth.types';

function isSession(data: unknown): data is AuthSession {
  return isObject(data) && isText(data.csrf_token) && typeof data.simulation_debug_enabled === 'boolean'
    && (data.user === null || (isObject(data.user) && isText(data.user.id) && isText(data.user.username) && isText(data.user.home_id)));
}

async function session(path: string, method = 'GET', body?: unknown): Promise<AuthSession> {
  const data = await apiRequest(path, method, body);
  if (!isSession(data)) throw new Error('服务返回了无法识别的账号信息。');
  resetSessionContext(data.csrf_token);
  if (method !== 'GET') broadcastSessionChange();
  return data;
}

export const authApi = {
  session: () => session('/auth/session'),
  register: (body: Credentials) => session('/auth/register', 'POST', body),
  login: (body: Credentials) => session('/auth/login', 'POST', body),
  logout: () => session('/auth/logout', 'POST', {}),
};
