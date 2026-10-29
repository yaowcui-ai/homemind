import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import AgentComposer from './AgentComposer';
import { TaskSubmission } from '../../api/tasks';
import { makeAgentTask } from '../../test/agent-fixtures';

it('模型未配置显示原因，保留清晰的自然语言输入但禁止提交', () => {
  render(<AgentComposer snapshot={makeAgentTask().final_snapshot} config={{ available: false, model: 'model', reason: '自然语言任务尚未配置模型，请使用规则模板' }}
    submission={new TaskSubmission()} onCreated={vi.fn()} disabled={false} />);
  expect(screen.getByText('自然语言任务尚未配置模型，请使用规则模板')).toBeVisible();
  expect(screen.getByRole('button', { name: '提交自然语言任务' })).toBeDisabled();
});

it('可用实验入口保存选择并把策略随原始需求提交，旧配置不显示实验', async () => {
  const submission = new TaskSubmission();
  submission.saveAgentDraft({ text: '60分钟后客厅26℃，能耗优先，允许合帘', keep_entity_ids: [], protected_room_ids: [] });
  vi.spyOn(submission, 'submitAgent').mockResolvedValue(makeAgentTask());
  const view = render(<AgentComposer snapshot={makeAgentTask().final_snapshot}
    config={{ available: true, model: 'model', reason: null, strategies: ['standard', 'single_forecast'] }}
    submission={submission} onCreated={vi.fn()} disabled={false} />);
  fireEvent.click(screen.getByRole('radio', { name: '温控方案比较（实验）' }));
  fireEvent.click(screen.getByRole('button', { name: '提交自然语言任务' }));
  await waitFor(() => expect(submission.submitAgent).toHaveBeenCalledWith(expect.objectContaining({ strategy: 'single_forecast' })));
  expect(submission.getSnapshot().agentDraft.strategy).toBe('single_forecast');
  view.rerender(<AgentComposer snapshot={makeAgentTask().final_snapshot} config={{ available: true, model: 'model', reason: null }}
    submission={submission} onCreated={vi.fn()} disabled={false} />);
  expect(screen.queryByRole('radio', { name: '温控方案比较（实验）' })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: '提交自然语言任务' })).toBeDisabled();
});

it('专家入口显式选择并提交expert策略，不让普通关灯默认走多Agent', async () => {
  const submission = new TaskSubmission();
  submission.saveAgentDraft({ text: '60分钟26℃，能耗优先', keep_entity_ids: [], protected_room_ids: [] });
  vi.spyOn(submission, 'submitAgent').mockResolvedValue(makeAgentTask());
  render(<AgentComposer snapshot={makeAgentTask().final_snapshot}
    config={{ available: true, model: 'model', reason: null, strategies: ['standard', 'single_forecast', 'expert_forecast'] }}
    submission={submission} onCreated={vi.fn()} disabled={false} />);
  expect(screen.getByRole('radio', { name: '常规助手' })).toBeChecked();
  fireEvent.click(screen.getByRole('radio', { name: '多 Agent 协作（实验）' }));
  fireEvent.click(screen.getByRole('button', { name: '提交自然语言任务' }));
  await waitFor(() => expect(submission.submitAgent).toHaveBeenCalledWith(expect.objectContaining({ strategy: 'expert_forecast' })));
});

it('已配置不声称已连接，等待真实响应只显示正在处理', async () => {
  const submission = new TaskSubmission();
  let finish!: (value: ReturnType<typeof makeAgentTask>) => void;
  vi.spyOn(submission, 'submitAgent').mockReturnValue(new Promise((resolve) => { finish = resolve; }));
  render(<AgentComposer snapshot={makeAgentTask().final_snapshot} config={{ available: true, model: 'model', reason: null }}
    submission={submission} onCreated={vi.fn()} disabled={false} />);
  expect(screen.getByText(/模型已配置/)).toBeVisible();
  expect(screen.queryByText(/模型已连接/)).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('生活需求'), { target: { value: '关闭客厅主灯' } });
  fireEvent.click(screen.getByRole('button', { name: '提交自然语言任务' }));
  await waitFor(() => expect(submission.submitAgent).toHaveBeenCalledWith(expect.objectContaining({ text: '关闭客厅主灯', expected_world_id: 'world-test' })));
  expect(screen.getByText('正在处理，请等待实际结果。')).toBeVisible();
  expect(screen.queryByText(/规划完成|\d+%/)).not.toBeInTheDocument();
  finish(makeAgentTask());
  await waitFor(() => expect(screen.queryByText('正在处理，请等待实际结果。')).not.toBeInTheDocument());
});
