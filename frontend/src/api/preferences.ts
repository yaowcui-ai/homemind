import { apiRequest, isObject, isNumber } from './client';
import type { Preferences } from './auth.types';

export function isPreferences(data: unknown): data is Preferences {
  return isObject(data) && isNumber(data.version) && isNumber(data.comfort_temperature_c)
    && isNumber(data.sleep_temperature_c) && isNumber(data.arrival_lead_minutes)
    && ['low', 'auto'].includes(String(data.fan_mode));
}

async function preferences(method = 'GET', body?: Partial<Omit<Preferences, 'version'>>): Promise<Preferences> {
  const data = await apiRequest('/preferences', method, body);
  if (!isPreferences(data)) throw new Error('服务返回了无法识别的偏好信息。');
  return data;
}

export const preferencesApi = { get: () => preferences(), update: (body: Partial<Omit<Preferences, 'version'>>) => preferences('PATCH', body) };
