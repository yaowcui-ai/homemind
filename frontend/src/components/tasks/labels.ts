import type { TaskStatus } from '../../api/tasks.types';
export const scenarioLabels = { homecoming: '回家准备', sleep: '睡眠模式', away: '离家模式' };
export const statusLabels: Record<TaskStatus, string> = { queued: '已受理', running: '执行中', waiting_input: '等待补充', waiting_verification: '等待目标核验', succeeded: '全部条件已核验', partial: '部分完成', failed: '未完成', cancelled: '已取消' };
