import { onlineManager, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ConnectionCard from './components/ConnectionCard';

const clients: QueryClient[] = [];
const health = { status: 'ok', service: 'homemind-api', version: '0.1.0', stage: 'M1' };

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  clients.push(client);
  return render(<QueryClientProvider client={client}><ConnectionCard /></QueryClientProvider>);
}

afterEach(() => {
  clients.splice(0).forEach((client) => client.clear());
  onlineManager.setOnline(true);
  vi.unstubAllGlobals();
});

describe('工程基础控制台', () => {
  it('检查期间显示等待状态，收到实际响应后展示在线', async () => {
    let resolveResponse!: (value: Response) => void;
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((resolve) => {
      resolveResponse = resolve;
    })));
    renderApp();
    expect(screen.getByText('正在检查连接…')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /重新检查/ })).toBeDisabled();
    resolveResponse(Response.json(health));
    expect(await screen.findByText('后端已连接')).toBeInTheDocument();
    expect(screen.getByText('v0.1.0')).toBeInTheDocument();
  });

  it('离线时给出明确提示，手动重查后恢复', async () => {
    const fetch = vi.fn()
      .mockRejectedValueOnce(new Error('connection failed'))
      .mockResolvedValueOnce(Response.json(health));
    vi.stubGlobal('fetch', fetch);
    renderApp();
    expect(await screen.findByText('后端暂未连接，请确认后端服务已启动。')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /重新检查/ }));
    expect(await screen.findByText('后端已连接')).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it('明确标注仿真范围，不声称接入真实设备', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(health)));
    renderApp();
    await screen.findByText('后端已连接');
    expect(screen.getByText('当前为本地仿真，尚未接入真实设备或 Agent。')).toBeInTheDocument();
  });

  it('浏览器报告离线后，手动检查仍会发起本地请求而不保留假在线', async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce(Response.json(health))
      .mockRejectedValueOnce(new Error('connection failed'));
    vi.stubGlobal('fetch', fetch);
    renderApp();
    await screen.findByText('后端已连接');
    act(() => onlineManager.setOnline(false));
    fireEvent.click(screen.getByRole('button', { name: /重新检查/ }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('后端暂未连接，请确认后端服务已启动。')).toBeInTheDocument();
    expect(screen.queryByText('后端已连接')).not.toBeInTheDocument();
  });
});
