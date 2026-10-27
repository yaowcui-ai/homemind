import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import TaskDetail from './TaskDetail';
import { makeAgentTask } from '../../test/agent-fixtures';

it('同名澄清选项有实际温度区别，回答保留原任务轮次', () => {
  const reply = vi.fn();
  render(<TaskDetail task={makeAgentTask()} pending={false} onVerify={vi.fn()} onReply={reply} />);
  expect(screen.getByText('操作哪个客厅？')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: /客厅.*28℃/ }));
  expect(reply).toHaveBeenCalledWith('room-1');
  expect(screen.queryByRole('button', { name: '核验目标' })).not.toBeInTheDocument();
});

it('待确认展示实际动作、范围和例外后才可确认', () => {
  const task = makeAgentTask({ status: 'waiting_confirmation', plan: {
    actions: [{ entity_id: 'entity-1', entity_name: '主灯', room_name: '客厅', action: 'set_light', parameters: { power: false } }],
    constraints: [], temperatures: [], due_at_minutes: null,
  } });
  task.agent_run!.proposed_plan = { kind: 'plan', scenario: 'away', room_ids: ['room-1'], keep_entity_ids: [],
    protected_room_ids: ['room-2'], actions: [], temperatures: [], ready_in_minutes: null, rationale: '全屋关闭，保护指定房间' };
  const confirm = vi.fn();
  render(<TaskDetail task={task} pending={false} onVerify={vi.fn()} onConfirm={confirm} />);
  expect(screen.getByText(/关闭灯光/)).toBeVisible();
  expect(screen.getByText(/保护房间/)).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: '确认执行此方案' }));
  expect(confirm).toHaveBeenCalledOnce();
});

it('失败且没有执行动作的Agent任务不能核验成成功，用量缺失如实为未知', () => {
  render(<TaskDetail task={makeAgentTask({ status: 'failed' })} pending={false} onVerify={vi.fn()} />);
  expect(screen.queryByRole('button', { name: '核验目标' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByText('运行记录与调用用量'));
  expect(screen.getByText(/Token 用量：未知/)).toBeVisible();
});

it('等待补充只有快照时刻时显示尚无核验证据，不把快照冒充最近核验', () => {
  render(<TaskDetail task={makeAgentTask()} pending={false} onVerify={vi.fn()} />);
  expect(screen.queryByText(/最近核验时刻/)).not.toBeInTheDocument();
  expect(screen.getByText('尚无核验证据。')).toBeVisible();
});

it('目标未到可在同页推进；错过目标不能补造历史证据', () => {
  const task = makeAgentTask({ status: 'waiting_verification', actions: [{ id: 'action-1', entity_id: 'entity-1',
    entity_name: '主灯', room_name: '客厅', action: 'set_light', parameters: { power: true }, status: 'verified', transport_outcome: 'verified', message: '读回已开启' }],
    plan: { actions: [], constraints: [], temperatures: [{ room_id: 'room-1', room_name: '客厅', target: 26 }], due_at_minutes: 60 },
    verification: { checked_at_minutes: 0, due_at_minutes: 60, conditions: [] } });
  const advance = vi.fn();
  const view = render(<TaskDetail task={task} pending={false} onVerify={vi.fn()} onAdvance={advance} debugEnabled currentSnapshot={task.final_snapshot} />);
  fireEvent.click(screen.getByRole('button', { name: '推进至目标时刻 t+60 分钟并核验' }));
  expect(advance).toHaveBeenCalledOnce();
  view.rerender(<TaskDetail task={task} pending={false} onVerify={vi.fn()} onAdvance={advance} debugEnabled currentSnapshot={{ ...task.final_snapshot, simulated_minutes: 61 }} />);
  expect(screen.queryByRole('button', { name: /推进至/ })).not.toBeInTheDocument();
  expect(screen.getByText(/不能补造历史证据/)).toBeVisible();
});
