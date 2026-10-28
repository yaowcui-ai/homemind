import { useState } from 'react';
import { Alert, Button, Input, Tag } from 'antd';
import type { TaskDetail as Detail } from '../../api/tasks.types';
import type { Snapshot } from '../../api/simulation.types';
import { scenarioLabels, statusLabels, modeLabels } from './labels';
import { actionTarget, entityLabel, optionLabel, roomLabel } from './taskLabels';
import styles from './Tasks.module.css';

const outcomeLabels: Record<string, string> = { planned: '待执行', submitted: '已提交', verified: '已核验', failed: '失败', unknown: '未知', skipped: '未执行', pending: '待核验' };
interface Props {
  task: Detail; pending: boolean; onVerify: () => void; onReply?: (text: string) => void; onConfirm?: () => void;
  onAdvance?: () => void; debugEnabled?: boolean; currentSnapshot?: Snapshot;
}
export default function TaskDetail({ task, pending, onVerify, onReply, onConfirm, onAdvance, debugEnabled = false, currentSnapshot }: Props) {
  const [reply, setReply] = useState('');
  const run = task.agent_run;
  const proposed = run?.proposed_plan;
  const snapshot = task.initial_snapshot;
  const now = currentSnapshot?.simulated_minutes ?? task.final_snapshot.simulated_minutes;
  const sameWorld = (currentSnapshot?.world_id ?? task.world_id) === task.world_id;
  const due = task.plan?.due_at_minutes ?? task.verification.due_at_minutes;
  const continuing = ['waiting_verification', 'partial'].includes(task.status) && task.actions.length > 0;
  const temperatureGoal = (task.plan?.temperatures.length ?? 0) > 0;
  const canAdvance = debugEnabled && sameWorld && continuing && temperatureGoal && (due !== null ? due > now : task.scenario === 'sleep');
  const canVerify = ['waiting_verification', 'partial', 'failed'].includes(task.status) && (task.mode !== 'single_agent' || task.actions.length > 0);
  const keep = proposed?.keep_entity_ids ?? task.request.keep_entity_ids ?? [];
  const protectedRooms = proposed?.protected_room_ids ?? task.request.protected_room_ids ?? [];
  const rooms = proposed?.room_ids ?? (task.mode === 'rule' ? task.request.room_ids : []);
  return <section className={styles.card} aria-label="任务详情">
    <div className={styles.sectionHead}><h2>{scenarioLabels[task.scenario]}</h2><div><Tag>{modeLabels[task.mode ?? 'rule']}</Tag><Tag color={task.status === 'succeeded' ? 'green' : task.status === 'failed' ? 'red' : 'gold'}>{statusLabels[task.status]}</Tag></div></div>
    <Alert type={task.status === 'succeeded' ? 'success' : task.status === 'failed' ? 'error' : 'info'} title={task.message} />
    {task.status === 'failed' && task.actions.length === 0 && run?.failure_code === 'protected_conflict' && <p className={styles.hint}>
      方案把操作对象与保留或保护范围设为冲突，未发送设备动作。请点击“开始新任务”，明确要操作和保持不变的对象后重新提交。
    </p>}
    {task.status === 'failed' && task.actions.length === 0 && run?.failure_code === 'refused' && <p className={styles.hint}>
      此任务已结束，未发送设备动作。请点击“开始新任务”，说明你的取舍或调整需求后重新提交。
    </p>}
    <p className={styles.hint}>任务编号 {task.id}</p>
    {task.mode === 'single_agent' && <p className={styles.requestText}>你的需求：{task.request.text}</p>}
    {(proposed || task.mode === 'rule') && <div className={styles.plan} aria-label="实际任务方案">
      <h3>理解到的目标与方案</h3>
      <p>目标：{scenarioLabels[task.scenario]}{(task.plan?.temperatures ?? []).map((goal) => ` · ${roomLabel(snapshot, goal.room_id)} ${goal.target}℃`).join('')}</p>
      <p>作用房间：{rooms.map((id) => roomLabel(snapshot, id)).join('；') || '以实际动作清单为准'}</p>
      <p>保留设备：{keep.map((id) => entityLabel(snapshot, id)).join('；') || '无额外保留'}</p>
      <p>保护房间：{protectedRooms.map((id) => roomLabel(snapshot, id)).join('；') || '无额外保护'}</p>
      {task.mode === 'rule' && <p>本次偏好：回家 {task.preferences_snapshot.comfort_temperature_c}℃ / 睡眠 {task.preferences_snapshot.sleep_temperature_c}℃，提前 {task.preferences_snapshot.arrival_lead_minutes} 仿真分钟。表单明确输入的目标优先。</p>}
      {run?.rationale && <p>方案说明：{run.rationale}</p>}
      {task.status === 'waiting_confirmation' && task.plan.actions.map((action, index) => <p key={`${action.entity_id}-${index}`}><strong>{entityLabel(snapshot, action.entity_id)}</strong> · {actionTarget(action)}</p>)}
      {task.plan?.constraints.map((condition, index) => <p key={index}>{condition.label}：{condition.message}</p>)}
    </div>}
    {run && task.status === 'waiting_input' && <section className={styles.continueForm} aria-label="补充任务信息">
      <h3>补充信息后继续原任务</h3><p>{run.question}</p>
      <div className={styles.optionList}>{run.options.map((option) => <Button key={`${option.kind}-${option.id}`} autoInsertSpace={false} disabled={pending || !onReply}
        onClick={() => onReply?.(option.id)}>{optionLabel(snapshot, option)}</Button>)}</div>
      <label htmlFor={`reply-${task.id}`}>自由补充回答</label>
      <Input.TextArea id={`reply-${task.id}`} value={reply} onChange={(event) => setReply(event.target.value)} maxLength={2000} rows={3} disabled={pending} />
      <Button type="primary" disabled={pending || !reply.trim() || !onReply} onClick={() => { onReply?.(reply.trim()); setReply(''); }}>提交补充回答</Button>
      <p className={styles.hint}>已补充 {run.turn}/{run.max_replies} 轮，回答会继续当前任务。</p>
    </section>}
    {run && task.status === 'waiting_confirmation' && <div className={styles.continueForm}>
      <p>请核对以上实际范围、例外和动作；确认后才会执行。家庭状态变化会使旧方案失效。</p>
      <Button type="primary" disabled={pending || !onConfirm} onClick={onConfirm}>确认执行此方案</Button>
    </div>}
    <h3>动作与读回</h3>
    {!task.actions.length && <p className={styles.hint}>{['waiting_input', 'waiting_confirmation', 'planning'].includes(task.status) ? '尚未发送设备动作。' : '没有已执行动作。请查看任务说明与条件。'}</p>}
    {task.actions.map((action) => <div className={styles.action} key={action.id}>
      <div><strong>{action.entity_name}</strong><small>{actionTarget(action)}</small><small>{action.room_name} · {action.message}</small>
        {action.transport_outcome === 'unknown' && <small>设备响应未知，以上结果来自独立读回。</small>}</div>
      <Tag color={action.status === 'verified' ? 'green' : 'orange'}>{outcomeLabels[action.status]}</Tag>
    </div>)}
    <h3>目标核验与下一步</h3>
    <p className={styles.hint}>当前仿真时刻 t+{now} 分钟{due !== null && ` · 目标时刻 t+${due} 分钟`}。设备设置成功与室温达标分别判断。</p>
    <p className={styles.hint}>{task.actions.length || task.verification.conditions.length
      ? `最近核验时刻 t+${task.verification.checked_at_minutes} 分钟。` : '尚无核验证据。'}</p>
    {task.verification.conditions.map((condition, index) => <div className={styles.condition} key={`${index}-${condition.label}`}>
      <div><strong>{condition.label}</strong><small>{condition.message}</small></div><Tag>{outcomeLabels[condition.outcome]}</Tag>
    </div>)}
    {!sameWorld && continuing && <p className={styles.hint}>仿真环境已重置，旧任务不能推进；请开始新任务。</p>}
    {sameWorld && continuing && due !== null && now > due && <p className={styles.hint}>已错过目标时刻，不能补造历史证据；可读取已有核验结果。</p>}
    {sameWorld && continuing && due !== null && now === due && <p className={styles.hint}>已到目标时刻，请现在核验目标。</p>}
    {!debugEnabled && continuing && temperatureGoal && <p className={styles.hint}>此环境没有仿真时间推进能力，不能继续等待未来目标；请检查演示配置。</p>}
    <div className={styles.taskActions}>
      {canAdvance && <Button disabled={pending || !onAdvance} onClick={onAdvance}>{due !== null ? `推进至目标时刻 t+${due} 分钟并核验` : '推进 10 仿真分钟并核验'}</Button>}
      {canVerify && <Button aria-label="核验目标" onClick={onVerify} loading={pending} disabled={pending}>核验目标</Button>}
    </div>
    {canVerify && <p className={styles.hint}>核验只读取结果，不会重新发送设备动作。推进仅改变仿真时间，不代表真实预约控制。</p>}
    <p className={styles.hint}>初始 t+{task.initial_snapshot.simulated_minutes} 分钟 → 结果 t+{task.final_snapshot.simulated_minutes} 分钟 · 累计仿真能耗 {task.final_snapshot.energy_wh.toFixed(3)} Wh</p>
    {run && <details className={styles.records}><summary>运行记录与调用用量</summary>
      <p>实际模型：{run.actual_model ?? '未知'} · 模型调用 {run.model_calls} 次 · 只读工具 {run.tool_calls} 次</p>
      <p>Token 用量：{run.usage ? `输入 ${run.usage.input_tokens} / 输出 ${run.usage.output_tokens}` : '未知'}</p>
      <p>已记录耗时：规划 {run.timings.planning_ms} ms · 校验 {run.timings.validation_ms} ms · 执行 {run.timings.execution_ms} ms</p>
      {run.failure_code && <p>失败分类：{run.failure_code}</p>}
      {run.records.map((record, index) => <p key={index}>{record.message}{record.duration_ms !== undefined ? ` · ${record.duration_ms} ms` : record.elapsed_ms !== undefined ? ` · ${record.elapsed_ms} ms` : ''}</p>)}
      <h3>公开对话</h3>{run.conversation.map((message, index) => <p key={index}>{message.role === 'user' ? '你' : '助手'}：{message.text}</p>)}
    </details>}
  </section>;
}
