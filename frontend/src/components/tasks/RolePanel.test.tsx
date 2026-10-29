import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import TaskDetail from './TaskDetail';
import { makeExpertTask } from '../../test/expert-fixtures';
import type { TaskDetail as Detail } from '../../api/tasks.types';

it('不同专家意见按实际候选展示，协调选择不伪造共识或实时进度', () => {
  render(<TaskDetail task={makeExpertTask() as unknown as Detail} pending={false} onVerify={vi.fn()} onConfirm={vi.fn()} />);
  expect(screen.getByRole('region', { name: '多 Agent 分析记录' })).toBeVisible();
  expect(screen.getByText('多 Agent', { exact: true })).toBeVisible();
  expect(screen.getByText(/舒适建议方案 2/)).toBeVisible();
  expect(screen.getByText(/节能建议方案 1/)).toBeVisible();
  expect(screen.getByText(/协调选择方案 1/)).toBeVisible();
  expect(screen.queryByText(/两位专家一致|实时进度/)).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: '确认执行此方案' })).toBeEnabled();
});

it('分析失败且零动作的multi不能核验成成功，并给恢复出口', () => {
  const task = makeExpertTask();
  const failed = { ...task, status: 'failed', plan: { actions: [], constraints: [], temperatures: [], due_at_minutes: null },
    agent_run: { ...task.agent_run, failure_code: 'analysis_incomplete', proposed_plan: null,
      selected_candidate_id: null, preference_optimal: null } } as unknown as Detail;
  render(<TaskDetail task={failed} pending={false} onVerify={vi.fn()} />);
  expect(screen.queryByRole('button', { name: '核验目标' })).not.toBeInTheDocument();
  expect(screen.getByText(/分析未完整完成.*开始新任务/)).toBeVisible();
});
