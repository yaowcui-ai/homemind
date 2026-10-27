import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import TaskComposer from './TaskComposer';
import { TaskSubmission } from '../../api/tasks';
import { makeAgentTask } from '../../test/agent-fixtures';

it('普通模式禁用未来回家目标，并解释需要仿真推进', () => {
  const task = makeAgentTask();
  render(<TaskComposer snapshot={task.final_snapshot} preferences={task.preferences_snapshot}
    onCreated={vi.fn()} submission={new TaskSubmission('ordinary-home')} disabled={false} debugEnabled={false} />);
  expect(screen.getByRole('button', { name: '执行规则任务' })).toBeDisabled();
  expect(screen.getByText(/需要仿真时间推进/)).toBeVisible();
});
