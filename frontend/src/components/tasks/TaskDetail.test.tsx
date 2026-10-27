import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import TaskDetail from './TaskDetail';
import { makeTask } from '../../test/simulation-fixtures';

it('部分完成的未知条件恢复后，可以显式重新核验而不重新执行任务', () => {
  const verify = vi.fn();
  render(<TaskDetail task={makeTask()} pending={false} onVerify={verify} />);
  fireEvent.click(screen.getByRole('button', { name: '核验目标' }));
  expect(verify).toHaveBeenCalledOnce();
});
