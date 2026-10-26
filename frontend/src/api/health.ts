export interface HealthResponse {
  status: 'ok';
  service: 'homemind-api';
  version: string;
  stage: string;
}

class HealthError extends Error {}

function isHealthResponse(value: unknown): value is HealthResponse {
  if (typeof value !== 'object' || value === null) return false;
  const body = value as Record<string, unknown>;
  return body.status === 'ok'
    && body.service === 'homemind-api'
    && typeof body.version === 'string' && body.version.trim().length > 0
    && typeof body.stage === 'string' && body.stage.trim().length > 0;
}

export async function fetchHealth(): Promise<HealthResponse> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 5000);
  try {
    const response = await fetch('/api/health', {
      signal: controller.signal,
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) throw new HealthError('后端暂未连接，请确认后端服务已启动。');

    let body: unknown;
    try {
      body = await response.json();
    } catch {
      throw new HealthError('后端返回了无法识别的服务信息。');
    }
    if (!isHealthResponse(body)) throw new HealthError('后端返回了无法识别的服务信息。');
    return body;
  } catch (error) {
    if (controller.signal.aborted) throw new HealthError('连接检查超时，请稍后重试。');
    if (error instanceof HealthError) throw error;
    throw new HealthError('后端暂未连接，请确认后端服务已启动。');
  } finally {
    clearTimeout(timer);
  }
}
