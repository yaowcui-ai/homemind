import type { TaskStatus } from '../../api/tasks.types';
export const scenarioLabels = { homecoming: '回家准备', sleep: '睡眠模式', away: '离家模式', local: '局部设备操作' };
export const modeLabels = { rule: '规则', single_agent: '单 Agent' };
export const statusLabels: Record<TaskStatus, string> = { queued: '已受理', planning: '正在处理', running: '执行中', waiting_input: '等待补充', waiting_confirmation: '等待确认', waiting_verification: '等待目标核验', succeeded: '全部条件已核验', partial: '部分完成', failed: '未完成', cancelled: '已取消' };
