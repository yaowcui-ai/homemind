import { useRef, useState, useSyncExternalStore } from 'react';
import { Alert, Button, Input, Select } from 'antd';
import type { AgentConfig, TaskDetail } from '../../api/tasks.types';
import type { Snapshot } from '../../api/simulation.types';
import type { TaskSubmission } from '../../api/tasks';
import { entityLabel, roomLabel } from './taskLabels';
import styles from './Tasks.module.css';

interface Props { snapshot: Snapshot; config?: AgentConfig; disabled: boolean; submission: TaskSubmission; onCreated: (task: TaskDetail) => Promise<void> }
export default function AgentComposer({ snapshot, config, disabled, submission, onCreated }: Props) {
  const state = useSyncExternalStore(submission.subscribe, submission.getSnapshot);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lock = useRef(false);
  const draft = state.agentDraft;
  async function submit() {
    if (disabled || !config?.available || !draft.text.trim() || lock.current) return;
    lock.current = true; setPending(true); setError(null);
    try {
      await onCreated(await submission.submitAgent({ text: draft.text.trim(), expected_world_id: snapshot.world_id,
        keep_entity_ids: draft.keep_entity_ids, protected_room_ids: draft.protected_room_ids }));
    } catch (error) { setError(error instanceof Error ? error.message : '任务提交未完成，请读取原提交结果。'); }
    finally { lock.current = false; setPending(false); }
  }
  return <section className={styles.card} aria-label="自然语言任务表单">
    <h2>说说你想怎样安排家</h2>
    <p className={styles.hint}>单 Agent 理解需求，程序检查范围和约束后通过共用执行器处理。设备与时间仍为仿真。</p>
    {config ? config.available
      ? <p className={styles.hint}>模型已配置：{config.model}。调用结果以本次任务记录为准。</p>
      : <Alert type="info" title={config.reason ?? '自然语言任务尚未配置模型，请使用规则模板'} />
      : <p className={styles.hint}>尚未读取模型配置，请先读取配置。</p>}
    {error && <Alert type="error" title={error} description="结果不明时先读取原提交结果；同键重试会使用原始需求。" />}
    <form className={styles.agentForm} onSubmit={(event) => { event.preventDefault(); void submit(); }}>
      <label htmlFor="agent-intent">生活需求</label>
      <Input.TextArea id="agent-intent" rows={5} maxLength={2000} value={draft.text} disabled={disabled || pending}
        placeholder="例如：60 个仿真分钟后回家，客厅准备到 26℃；或关闭客厅主灯。"
        onChange={(event) => submission.saveAgentDraft({ ...draft, text: event.target.value })} />
      <details className={styles.records}><summary>明确保留设备与保护房间（可选）</summary>
        <label htmlFor="agent-keep">保留设备（不改变）</label>
        <Select id="agent-keep" mode="multiple" allowClear value={draft.keep_entity_ids} disabled={disabled || pending}
          options={snapshot.entities.filter((e) => e.enabled && ['light', 'climate', 'cover'].includes(e.type)).map((e) => ({ value: e.id, label: entityLabel(snapshot, e.id) }))}
          onChange={(value) => submission.saveAgentDraft({ ...draft, keep_entity_ids: value })} />
        <label htmlFor="agent-protected">保护房间（不执行动作）</label>
        <Select id="agent-protected" mode="multiple" allowClear value={draft.protected_room_ids} disabled={disabled || pending}
          options={snapshot.rooms.map((r) => ({ value: r.id, label: roomLabel(snapshot, r.id) }))}
          onChange={(value) => submission.saveAgentDraft({ ...draft, protected_room_ids: value })} />
        <p className={styles.hint}>这些是额外硬约束，服务端独立检查；也可以在需求中说明例外。</p>
      </details>
      <Button block type="primary" htmlType="submit" loading={pending} disabled={disabled || !config?.available || !draft.text.trim()}>提交自然语言任务</Button>
    </form>
    {pending && <p role="status">正在处理，请等待实际结果。</p>}
    <p className={styles.hint}>最多补充 3 轮。未来温度目标需要演示模式的仿真时间推进能力。</p>
  </section>;
}
