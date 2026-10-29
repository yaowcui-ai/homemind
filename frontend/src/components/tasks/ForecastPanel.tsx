import { Alert, Tag } from 'antd';
import type { AgentRun } from '../../api/tasks.types';
import type { Snapshot } from '../../api/simulation.types';
import { entityLabel, roomLabel } from './taskLabels';
import styles from './Tasks.module.css';

export default function ForecastPanel({ run, snapshot }: { run: AgentRun; snapshot: Snapshot }) {
  if (!['single_forecast', 'expert_forecast'].includes(run.strategy ?? '') || !run.goal) return null;
  const goal = run.goal;
  const forecast = run.forecast;
  return <section className={styles.plan} aria-label="仿真方案预测">
    <h3>温控方案比较（实验）</h3>
    <p>{roomLabel(snapshot, goal.room_id)} · {goal.ready_in_minutes} 仿真分钟内 ≤{goal.target_temperature_c}℃ · {goal.priority === 'energy_first' ? '能耗优先' : '尽早达标优先'}</p>
    <p className={styles.hint}>仿真预测不代表已经执行或实际温度已达标，结果以确认执行后的实测核验为准。</p>
    {!forecast ? <p>本轮未生成可用预测，请查看任务说明和下一步。</p> : <>
      <p className={styles.hint}>能耗范围：{forecast.energy_scope_entity_ids.map((id) => entityLabel(snapshot, id)).join('、')}；包含实际窗帘移动，不含其他设备。</p>
      <div className={styles.forecastGrid}>{forecast.candidates.map((candidate, index) => <article className={styles.forecastCandidate} key={candidate.id}>
        <h4>方案 {index + 1}{candidate.id === run.selected_candidate_id && <Tag color="blue">模型选择</Tag>}</h4>
        <p>{candidate.fan_mode === 'low' ? '低速风' : '自动风速'} · {candidate.cover_position_pct === null ? '不调整窗帘' : `窗帘 ${candidate.cover_position_pct}% 开合位置`}</p>
        <p>截止温度 {candidate.end_temperature_c.toFixed(1)}℃ · {candidate.deadline_met ? '预测按时达标' : '预测无法按时达标'}</p>
        <p>{candidate.first_observed_goal_minute === null ? '期限内未观测到达标' : `首次观测达标：${candidate.first_observed_goal_minute} 仿真分钟后`}</p>
        <p>范围仿真能耗 {candidate.energy_wh.toFixed(3)} Wh</p>
      </article>)}</div>
      <p className={styles.hint}>预测依据：t+{forecast.source.simulated_minutes} 分钟的家庭快照 · {forecast.model_version}。候选比较仅覆盖本轮允许的设置。</p>
    </>}
    {run.preference_optimal === false && <Alert type="warning" title="模型选择未达到本轮候选中的偏好最优，请核对取舍后决定是否执行。" />}
  </section>;
}
