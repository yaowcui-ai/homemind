import { useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Empty, Spin } from 'antd';
import { simulationApi } from '../../api/simulation';
import { tasksApi, type TaskSubmission } from '../../api/tasks';
import { preferencesApi } from '../../api/preferences';
import type { TaskDetail as Detail } from '../../api/tasks.types';
import TaskComposer from './TaskComposer';
import TaskDetail from './TaskDetail';
import { scenarioLabels, statusLabels } from './labels';
import styles from './Tasks.module.css';

const queryOptions = { networkMode: 'always' as const, retry: false, refetchOnWindowFocus: false, refetchOnReconnect: false };
export default function TasksPanel({ homeId, submission }: { homeId: string; submission: TaskSubmission }) {
  const client = useQueryClient();
  const snapshot = useQuery({ ...queryOptions, queryKey: ['simulation', homeId], queryFn: simulationApi.getSnapshot });
  const preferences = useQuery({ ...queryOptions, queryKey: ['preferences', homeId], queryFn: preferencesApi.get });
  const list = useQuery({ ...queryOptions, queryKey: ['tasks', homeId], queryFn: tasksApi.list });
  const [selected, setSelected] = useState<string | null>(null);
  const detail = useQuery({ ...queryOptions, queryKey: ['task', homeId, selected], queryFn: () => tasksApi.get(selected!), enabled: !!selected });
  const [error, setError] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);
  const verifyLock = useRef(false);
  async function saved(task: Detail) {
    setSelected(task.id); client.setQueryData(['task', homeId, task.id], task);
    await Promise.all([client.invalidateQueries({ queryKey: ['tasks', homeId] }), client.invalidateQueries({ queryKey: ['simulation', homeId] })]);
  }
  async function verify() {
    if (!selected || verifyLock.current) return;
    verifyLock.current = true; setVerifying(true); setError(null);
    try { await saved(await tasksApi.verify(selected)); }
    catch (error) { setError(error instanceof Error ? error.message : '核验未完成，请重试读取。'); }
    finally { verifyLock.current = false; setVerifying(false); }
  }
  if (!snapshot.data || !preferences.data) return <section className={styles.card}>
    {snapshot.isError || preferences.isError ? <Alert type="error" title="尚未读取任务所需状态" description={snapshot.error?.message ?? preferences.error?.message} action={<Button onClick={() => { void snapshot.refetch(); void preferences.refetch(); }}>重新读取</Button>} /> : <Spin description="正在读取家庭与偏好…" />}
  </section>;
  return <>
    <Alert className={styles.banner} type="info" showIcon title="规则基线 · 三个明确场景" description="目标基于当前家庭配置和保存偏好。时间只随仿真推进；等待目标核验时，可先回概览推进时间再核验。" />
    {error && <Alert type="error" title={error} />}
    <div className={styles.columns}>
      <TaskComposer snapshot={snapshot.data} preferences={preferences.data} onCreated={saved} submission={submission} disabled={snapshot.isError || snapshot.isFetching || preferences.isError || preferences.isFetching || verifying} />
      <div>
        <section className={styles.card} aria-label="任务列表">
          <div className={styles.sectionHead}><h2>最近任务</h2><Button loading={list.isFetching} onClick={() => { void list.refetch(); if (selected) void detail.refetch(); }}>读取任务</Button></div>
          {list.isError && <Alert type="error" title={list.error.message} />}
          {list.data?.length === 0 && <Empty description="还没有任务，先选择一个场景" />}
          {list.data?.map((task) => <button key={task.id} className={`${styles.taskRow} ${selected === task.id ? styles.selected : ''}`} onClick={() => setSelected(task.id)}>
            <span><strong>{scenarioLabels[task.scenario]}</strong><small>{new Date(task.created_at * 1000).toLocaleString('zh-CN', { hour12: false })}</small></span><span>{statusLabels[task.status]}</span>
          </button>)}
        </section>
        {detail.isError && <Alert type="error" title={detail.error.message} />}
        {detail.data && <TaskDetail task={detail.data} pending={verifying} onVerify={() => { void verify(); }} />}
      </div>
    </div>
  </>;
}
