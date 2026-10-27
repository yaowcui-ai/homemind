import { afterEach, describe, expect, it, vi } from 'vitest';
import { apiRequest, resetSessionContext, subscribeUnauthorized } from './client';

afterEach(() => { resetSessionContext(null); vi.unstubAllGlobals(); });

describe('同源认证客户端', () => {
  it('写操作携带内存 CSRF 与同源 Cookie，不把令牌写到正文', async () => {
    resetSessionContext('csrf-test');
    const fetch = vi.fn().mockResolvedValue(Response.json({ ok: true }));
    vi.stubGlobal('fetch', fetch);
    await apiRequest('/tasks', 'POST', { scenario: 'away' }, { 'Idempotency-Key': 'test-key-0001' });
    expect(fetch).toHaveBeenCalledWith('/api/tasks', expect.objectContaining({
      credentials: 'same-origin', headers: expect.objectContaining({ 'X-CSRF-Token': 'csrf-test', 'Idempotency-Key': 'test-key-0001' }),
      body: JSON.stringify({ scenario: 'away' }),
    }));
  });

  it('没有 CSRF 时不提交写请求', async () => {
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    await expect(apiRequest('/tasks', 'POST', {})).rejects.toThrow(/登录|会话/);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('会话切换后忽略此前迟到的响应，即使底层请求没有遵守 abort', async () => {
    let release!: (response: Response) => void;
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise<Response>((resolve) => { release = resolve; })));
    resetSessionContext('account-a');
    const pending = apiRequest('/simulation');
    resetSessionContext('account-b');
    release(Response.json({ home_id: 'a' }));
    await expect(pending).rejects.toThrow(/切换|会话/);
  });

  it('401 通知界面清理会话，错误不泄露原始连接信息', async () => {
    const listener = vi.fn(); const unsubscribe = subscribeUnauthorized(listener);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ detail: { code: 'unauthorized', message: '请先登录。' } }, { status: 401 })));
    await expect(apiRequest('/simulation')).rejects.toThrow('请先登录。');
    expect(listener).toHaveBeenCalledOnce();
    unsubscribe();
  });
});
