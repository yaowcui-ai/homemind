import { Tag } from 'antd';
import type { AgentRun, RoleMetrics } from '../../api/tasks.types';
import styles from './Tasks.module.css';

const names: Record<RoleMetrics['role'], string> = { coordinator_goal: '协调 Agent · 目标理解',
  comfort: '舒适 Agent', energy: '节能 Agent', coordinator_plan: '协调 Agent · 方案选择' };
const statuses = { succeeded: '响应完成', failed: '分析失败', cancelled: '已中断', skipped: '未运行' };

export default function RolePanel({ run }: { run: AgentRun }) {
  if (run.strategy !== 'expert_forecast') return null;
  const roles = run.role_runs ?? [];
  const candidate = (id: string | null | undefined) => {
    const index = run.forecast?.candidates.findIndex((c) => c.id === id) ?? -1;
    return index < 0 ? '未定位候选' : `方案 ${index + 1}`;
  };
  const comfort = roles.find((r) => r.role === 'comfort')?.advice;
  const energy = roles.find((r) => r.role === 'energy')?.advice;
  return <section className={styles.plan} aria-label="多 Agent 分析记录">
    <h3>本轮角色记录</h3>
    <p className={styles.hint}>舒适与节能分别分析相同资料，协调角色负责理解目标和选择方案。下列记录来自本轮实际响应；响应完成不代表设备已经执行。</p>
    {comfort?.outcome === 'recommend' && energy?.outcome === 'recommend' && <p>
      舒适建议{candidate(comfort.preferred_candidate_id)}；节能建议{candidate(energy.preferred_candidate_id)}。
      {run.selected_candidate_id && `协调选择${candidate(run.selected_candidate_id)}。`}
    </p>}
    {!roles.length && <p>尚无已完成的角色记录，请查看任务状态。</p>}
    <div className={styles.forecastGrid}>{roles.map((record) => <article className={styles.forecastCandidate} key={record.role}>
      <h4>{names[record.role]}<Tag>{statuses[record.status]}</Tag></h4>
      {record.advice && <>
        <p>公开建议：{record.advice.public_summary}</p>
        <p className={styles.hint}>依据：{record.advice.evidence_refs.map((ref) => ref === 'goal' ? '目标约束' : `${candidate(ref.slice('candidate:'.length))}的预测`).join('、') || '未提供引用'}</p>
      </>}
      <details className={styles.records}><summary>阶段调用记录</summary>
        <p>模型调用 {record.model_calls} 次 · 只读工具 {record.tool_calls} 次</p>
        {record.status !== 'skipped' && <>
          <p>本阶段耗时 {record.elapsed_ms} ms · 实际模型 {record.actual_model ?? '未知'}</p>
          <p>Token：{record.usage ? `输入 ${record.usage.input_tokens} / 输出 ${record.usage.output_tokens}` : '未知'}</p>
        </>}
        {record.failure_code && <p className={styles.hint}>阶段分类：{record.failure_code}</p>}
      </details>
    </article>)}</div>
  </section>;
}
