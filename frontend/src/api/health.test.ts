import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchHealth } from './health';

const health = { status: 'ok', service: 'homemind-api', version: '0.1.0', stage: 'M1' };

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('HomeMind 健康接口', () => {
  it('只认有效的 HomeMind 服务响应，并使用同源接口', async () => {
    const fetch = vi.fn().mockResolvedValue(Response.json(health));
    vi.stubGlobal('fetch', fetch);
    await expect(fetchHealth()).resolves.toEqual(health);
    expect(fetch).toHaveBeenCalledWith('/api/health', expect.objectContaining({
      signal: expect.any(AbortSignal),
    }));
  });

  it('HTTP 失败时不透传上游正文', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('private upstream text', {
      status: 502,
    })));
    await expect(fetchHealth()).rejects.toThrow('后端暂未连接，请确认后端服务已启动。');
  });

  it.each([
    { ...health, service: 'another-api' },
    { ...health, version: 1 },
    { ...health, stage: '' },
    { status: 'ok' },
  ])('不把其他服务或错误结构误报为在线：%j', async (body) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(body)));
    await expect(fetchHealth()).rejects.toThrow('后端返回了无法识别的服务信息。');
  });

  it('无效 JSON 返回可理解的错误', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>private</html>')));
    await expect(fetchHealth()).rejects.toThrow('后端返回了无法识别的服务信息。');
  });

  it('网络错误不泄漏原始异常', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('private connection details')));
    await expect(fetchHealth()).rejects.toThrow('后端暂未连接，请确认后端服务已启动。');
  });

  it('五秒没有响应时结束检查', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn((_url, options: RequestInit) => new Promise((_resolve, reject) => {
      options.signal?.addEventListener('abort', () => reject(new DOMException('', 'AbortError')));
    })));
    const result = expect(fetchHealth()).rejects.toThrow('连接检查超时，请稍后重试。');
    await Promise.all([result, vi.advanceTimersByTimeAsync(5000)]);
  });
});
