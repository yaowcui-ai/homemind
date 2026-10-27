import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { simulationApi } from '../../api/simulation';
import { makeEntity, makeSnapshot } from '../../test/simulation-fixtures';
import EntityCard from './EntityCard';
import type { Operation } from './labels';

const run: Operation = async (operation) => { await operation(); return true; };
afterEach(() => vi.restoreAllMocks());

describe('实体卡片能力边界', () => {
  it('窗户传感器使用模拟事件，不伪造开窗器控制', async () => {
    const event = vi.spyOn(simulationApi, 'event').mockResolvedValue(makeSnapshot());
    const control = vi.spyOn(simulationApi, 'control');
    render(<EntityCard entity={makeEntity('window')} worldId="world-test" run={run} pending={false} debugEnabled onEdit={() => {}} onFault={() => {}} />);
    expect(screen.getByText('只读传感')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '模拟开窗' }));
    await waitFor(() => expect(event).toHaveBeenCalledWith({ entity_id: 'entity-1', window_open: true }));
    expect(control).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: '应用设置' })).not.toBeInTheDocument();
  });

  it('离线设备无法提交控制，但仍可打开故障设置', () => {
    render(<EntityCard entity={makeEntity('light', { available: false })} worldId="world-test" run={run} pending={false} debugEnabled onEdit={() => {}} onFault={() => {}} />);
    expect(screen.getByRole('button', { name: '应用设置' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '故障设置' })).toBeEnabled();
  });

  it('未知的存在信号不显示为无人', () => {
    render(<EntityCard entity={makeEntity('occupancy', { known: false, state: { occupied: null } })} worldId="world-test" run={run} pending={false} onEdit={() => {}} onFault={() => {}} />);
    expect(screen.getByText('未知')).toBeInTheDocument();
    expect(screen.queryByText('无人', { exact: true })).not.toBeInTheDocument();
  });
});
