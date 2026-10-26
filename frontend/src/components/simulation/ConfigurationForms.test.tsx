import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { makeSnapshot } from '../../test/simulation-fixtures';
import { EntityModal, RoomModal } from './ConfigurationForms';
import type { Operation } from './labels';

beforeEach(() => {
  // JSDOM has no pseudo-element scrollbar layout; retain its real element styles.
  const getComputedStyle = window.getComputedStyle.bind(window);
  vi.spyOn(window, 'getComputedStyle').mockImplementation((element) => getComputedStyle(element));
});
afterEach(() => vi.restoreAllMocks());

describe.each([
  { kind: '房间', Modal: RoomModal, label: '房间名称' },
  { kind: '实体', Modal: EntityModal, label: '实体名称' },
])('$kind 创建表单', ({ Modal, label }) => {
  it.each([false, true])('首个请求未返回时重复回车不会重复创建（父级pending=%s）', async (pending) => {
    const snapshot = makeSnapshot();
    snapshot.rooms = [{ id: 'room-1', name: '客厅', primary_temperature_entity_id: null,
      primary_occupancy_entity_id: null, temperature_c: null, occupied: null, window_open: null }];
    const run = vi.fn<Operation>(() => new Promise<boolean>(() => {}));
    const props = { snapshot, run, pending: false, onClose: vi.fn() };
    const { rerender } = render(<Modal {...props} />);
    fireEvent.change(screen.getByLabelText(label), { target: { value: '测试配置' } });
    const form = screen.getByRole('dialog').querySelector('form')!;
    await act(async () => { fireEvent.submit(form); });
    await waitFor(() => expect(run).toHaveBeenCalledTimes(1));
    rerender(<Modal {...props} pending={pending} />);
    await act(async () => { fireEvent.submit(form); });
    expect(run).toHaveBeenCalledTimes(1);
    if (pending) expect(screen.getByLabelText(label)).toBeDisabled();
  });
});
