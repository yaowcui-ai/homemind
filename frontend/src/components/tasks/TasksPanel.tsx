import { useRef, useState, useSyncExternalStore } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Empty, Spin } from 'antd';
import { simulationApi } from '../../api/simulation';
import { tasksApi, type TaskSubmission } from '../../api/tasks';
import { preferencesApi } from '../../api/preferences';
import type { TaskDetail as Detail } from '../../api/tasks.types';
import TaskComposer from './TaskComposer';
import AgentComposer from './AgentComposer';
import TaskDetail from './TaskDetail';
import { modeLabels, scenarioLabels, statusLabels } from './labels';
import styles from './Tasks.module.css';

const queryOptions = { networkMode: 'always' as const, retry: false, refetchOnWindowFocus: false, refetchOnReconnect: false };
export default function TasksPanel({ homeId, submission, debugEnabled = false }: { homeId: string; submission: TaskSubmission; debugEnabled?: boolean }) {
  const client = useQueryClient();
  const state = useSyncExternalStore(submission.subscribe, submission.getSnapshot);
  const [mode, setMode] = useState<'rule' | 'single_agent'>('rule');
  const [composerKey, setComposerKey] = useState(0);
  const snapshot = useQuery({ ...queryOptions, queryKey: ['simulation', homeId], queryFn: simulationApi.getSnapshot });
  const preferences = useQuery({ ...queryOptions, queryKey: ['preferences', homeId], queryFn: preferencesApi.get });
  const config = useQuery({ ...queryOptions, queryKey: ['agent-config', homeId], queryFn: tasksApi.agentConfig });
  const list = useQuery({ ...queryOptions, queryKey: ['tasks', homeId], queryFn: () => tasksApi.list() });
  const selected = state.selectedId;
  const detail = useQuery({ ...queryOptions, queryKey: ['task', homeId, selected], queryFn: () => tasksApi.get(selected!), enabled: !!selected });
  const recovery = useQuery({ ...queryOptions, queryKey: ['task-recovery', homeId], enabled: state.restorePending, gcTime: 0, queryFn: async () => {
    const writeEpoch = submission.getWriteEpoch();
    const task = await submission.recover();
    return task && await cacheTask(task, writeEpoch) ? task : null;
  } });
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const writeLock = useRef(false);
  async function cacheTask(task: Detail, writeEpoch: number) {
    if (submission.getWriteEpoch() !== writeEpoch) return false;
    const queryKey = ['task', homeId, task.id];
    await client.cancelQueries({ queryKey, exact: true });
    if (submission.getWriteEpoch() !== writeEpoch) return false;
    client.setQueryData(queryKey, task);
    return true;
  }
  async function saved(task: Detail) {
    if (!await cacheTask(task, submission.getWriteEpoch())) return;
    await Promise.all([client.invalidateQueries({ queryKey: ['tasks', homeId] }), client.invalidateQueries({ queryKey: ['simulation', homeId] })]);
  }
  async function operation(action: () => Promise<Detail>) {
    if (writeLock.current || state.busy) return;
    writeLock.current = true; setWorking(true); setError(null);
    try { await saved(await action()); }
    catch (error) { setError(error instanceof Error ? error.message : '操作结果待确认，请读取原任务。'); }
    finally { writeLock.current = false; setWorking(false); }
  }
  async function read() {
    setError(null);
    const result = await recovery.refetch();
    if (result.error) setError(result.error.message);
    await Promise.all([list.refetch(), snapshot.refetch(), ...(selected && !state.busy ? [detail.refetch()] : [])]);
  }
  function beginNew() {
    submission.beginNew(); setComposerKey((key) => key + 1); setError(null);
  }
  if (!snapshot.data || !preferences.data) return <section className={styles.card}>
    {snapshot.isError || preferences.isError ? <Alert type="error" title="尚未读取任务所需状态" description={snapshot.error?.message ?? preferences.error?.message} action={<Button onClick={() => { void snapshot.refetch(); void preferences.refetch(); }}>重新读取</Button>} /> : <Spin description="正在读取家庭与偏好…" />}
  </section>;
  const busy = working || state.busy;
  const blocked = busy || recovery.isFetching;
  return <>
    <Alert className={styles.banner} type="info" showIcon title="自然语言与规则 · 共用受控执行和独立核验" description="可以使用固定规则，或让单 Agent 理解范围与例外。时间以仿真分钟计；未来目标可在原任务继续推进与核验。" />
    <div className={styles.modeSwitch} role="group" aria-label="任务输入方式">
      <Button disabled={busy} type={mode === 'rule' ? 'primary' : 'default'} onClick={() => setMode('rule')}>规则任务</Button>
      <Button disabled={busy} type={mode === 'single_agent' ? 'primary' : 'default'} onClick={() => setMode('single_agent')}>自然语言任务</Button>
      <Button disabled={blocked} onClick={beginNew}>开始新任务</Button>
    </div>
    {state.pending && !state.busy && <Alert className={styles.recovery} type="warning" title="原提交结果待确认" description={<>
      <p>刷新不会重新执行。请先读取原提交结果；仍未找到时，可用同一键重试原始意图。开始新任务会放下本次重试定位，原任务仍保留在历史中。</p>
      <div className={styles.taskActions}><Button disabled={blocked} onClick={() => { void read(); }}>读取原提交结果</Button><Button disabled={blocked} onClick={() => { void operation(() => submission.retryPending()); }}>同键重试原始意图</Button></div>
    </>} />}
    {(error || recovery.error) && <Alert type="error" title={error ?? recovery.error?.message} />}
    {busy && state.pending?.kind !== 'agent' && <p role="status">正在处理，请等待实际结果。</p>}
    <div className={styles.columns}>
      {mode === 'rule'
        ? <TaskComposer key={composerKey} snapshot={snapshot.data} preferences={preferences.data} onCreated={saved} submission={submission} debugEnabled={debugEnabled}
          disabled={snapshot.isError || snapshot.isFetching || preferences.isError || preferences.isFetching || blocked} />
        : <div>{config.isError && <Alert type="error" title={config.error.message} action={<Button onClick={() => { void config.refetch(); }}>读取模型配置</Button>} />}
          <AgentComposer key={composerKey} snapshot={snapshot.data} config={config.data} submission={submission} onCreated={saved} disabled={snapshot.isError || snapshot.isFetching || blocked} />
        </div>}
      <div>
        <section className={styles.card} aria-label="任务列表">
          <div className={styles.sectionHead}><h2>最近任务</h2><Button loading={list.isFetching || recovery.isFetching} disabled={busy} onClick={() => { void read(); }}>读取任务</Button></div>
          {list.isError && <Alert type="error" title={list.error.message} />}
          {list.data?.length === 0 && <Empty description="还没有任务，选择规则或自然语言开始" />}
          {list.data?.map((task) => <button key={task.id} className={`${styles.taskRow} ${selected === task.id ? styles.selected : ''}`} onClick={() => submission.select(task.id)}>
            <span><strong>{scenarioLabels[task.scenario]}</strong><small>{modeLabels[task.mode]} · {new Date(task.created_at * 1000).toLocaleString('zh-CN', { hour12: false })}</small></span><span>{statusLabels[task.status]}</span>
          </button>)}
        </section>
        {detail.isError && <Alert type="error" title={detail.error.message} />}
        {detail.data && <TaskDetail key={detail.data.id} task={detail.data} pending={blocked || !!state.pending} debugEnabled={debugEnabled} currentSnapshot={snapshot.data}
          onVerify={() => { void operation(() => submission.verify(detail.data.id)); }} onAdvance={() => { void operation(() => submission.advance(detail.data.id, {
            expected_world_id: snapshot.data.world_id, expected_simulated_minutes: snapshot.data.simulated_minutes,
          })); }}
          onReply={(text) => { if (detail.data.mode !== 'rule') { const { id, agent_run } = detail.data; void operation(() => submission.reply(id, { text, expected_turn: agent_run.turn })); } }}
          onConfirm={() => { if (detail.data.mode !== 'rule') { const { id, agent_run } = detail.data; void operation(() => submission.confirm(id, { expected_turn: agent_run.turn })); } }} />}
      </div>
    </div>
  </>;
}
