import { afterEach, describe, expect, it, vi } from 'vitest';
import { simulationApi } from './simulation';

const snapshot = {
  home_id: 'demo-home', world_id: 'world-test', revision: 0, config_revision: 0,
  simulated_minutes: 0, model_version: 'thermal-v1', outdoor_temperature_c: 32,
  energy_wh: 0, rooms: [], entities: [], archived_count: 0, recent_events: [],
};

afterEach(() => vi.unstubAllGlobals());

describe('仿真快照请求', () => {
  it('读取真实接口数据，不以本地模板代替', async () => {
    const fetch = vi.fn().mockResolvedValue(Response.json(snapshot));
    vi.stubGlobal('fetch', fetch);
    await expect(simulationApi.getSnapshot()).resolves.toEqual(snapshot);
    expect(fetch).toHaveBeenCalledWith('/api/simulation', expect.objectContaining({
      credentials: 'same-origin',
    }));
  });

  it('拒绝缺少家庭配置结构的 200 响应', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ status: 'ok' })));
    await expect(simulationApi.getSnapshot()).rejects.toThrow('服务返回了无法识别的家庭数据。');
  });

  it('业务错误只展示明确的说明', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({
      detail: { code: 'room_not_empty', message: '请先迁移或移除房间中的实体。' },
    }, { status: 409 })));
    await expect(simulationApi.getSnapshot()).rejects.toThrow('请先迁移或移除房间中的实体。');
  });

  it('网络故障不显示原始连接细节', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('private connection detail')));
    await expect(simulationApi.getSnapshot()).rejects.toThrow('无法连接仿真服务，请检查后端并重试。');
  });
});
