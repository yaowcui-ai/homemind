import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import TaskDetail from './TaskDetail';
import { makeForecastTask } from '../../test/forecast-fixtures';
import type { TaskDetail as Detail } from '../../api/tasks.types';

it('预测与实际核验分开，展示原选候选/能耗/期限而不说已经完成', () => {
  render(<TaskDetail task={makeForecastTask() as Detail} pending={false} onVerify={vi.fn()} onConfirm={vi.fn()} />);
  expect(screen.getByRole('region', { name: '仿真方案预测' })).toBeVisible();
  expect(screen.getByText(/550.050 Wh/)).toBeVisible();
  expect(screen.getByText(/850.050 Wh/)).toBeVisible();
  expect(screen.getByText(/仿真预测.*不代表.*实测/)).toBeVisible();
  expect(screen.getByText(/能耗优先/)).toBeVisible();
  expect(screen.getByText(/模型选择/)).toBeVisible();
  expect(screen.getByText('尚无核验证据。')).toBeVisible();
  expect(screen.getByRole('button', { name: '确认执行此方案' })).toBeEnabled();
});

it('偏好次优照实提示，不能显示成自动修正的最佳方案', () => {
  const task = makeForecastTask(); task.agent_run.preference_optimal = false;
  render(<TaskDetail task={task as Detail} pending={false} onVerify={vi.fn()} />);
  expect(screen.getByText(/未达到本轮候选中的偏好最优/)).toBeVisible();
});

it('预测不可用且没有goal时，仍给可执行恢复步骤和新任务出口', () => {
  const task = makeForecastTask();
  const failed = { ...task, status: 'failed', plan: { actions: [], constraints: [], temperatures: [], due_at_minutes: null },
    agent_run: { ...task.agent_run, failure_code: 'forecast_unavailable', goal: null, forecast: null, proposed_plan: null,
      selected_candidate_id: null, preference_optimal: null } } as Detail;
  render(<TaskDetail task={failed} pending={false} onVerify={vi.fn()} />);
  expect(screen.getByText(/检查.*感知.*开始新任务/)).toBeVisible();
  expect(screen.queryByRole('button', { name: '确认执行此方案' })).not.toBeInTheDocument();
});
