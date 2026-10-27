import { useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Form, InputNumber, Select, Spin } from 'antd';
import type { Preferences } from '../../api/auth.types';
import { preferencesApi } from '../../api/preferences';
import styles from './Tasks.module.css';

function Editor({ data, refresh }: { data: Preferences; refresh: () => Promise<unknown> }) {
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState<{ error: boolean; text: string } | null>(null);
  const lock = useRef(false);
  async function save(values: Omit<Preferences, 'version'>) {
    if (lock.current) return;
    lock.current = true; setPending(true); setNotice(null);
    try { await preferencesApi.update(values); await refresh(); setNotice({ error: false, text: '偏好已保存，新任务会使用这些设置。' }); }
    catch (error) { setNotice({ error: true, text: error instanceof Error ? error.message : '保存未完成。' }); }
    finally { lock.current = false; setPending(false); }
  }
  return <>
    {notice && <Alert type={notice.error ? 'error' : 'success'} title={notice.text} />}
    <Form layout="vertical" initialValues={data} disabled={pending} onFinish={(values) => { void save(values); }}>
      <Form.Item name="comfort_temperature_c" label="回家目标温度（℃）" rules={[{ required: true }]}><InputNumber min={16} max={30} precision={0} /></Form.Item>
      <Form.Item name="sleep_temperature_c" label="睡眠目标温度（℃）" rules={[{ required: true }]}><InputNumber min={16} max={30} precision={0} /></Form.Item>
      <Form.Item name="fan_mode" label="默认风速" rules={[{ required: true }]}><Select options={[{ value: 'low', label: '低速风' }, { value: 'auto', label: '自动风速' }]} /></Form.Item>
      <Form.Item name="arrival_lead_minutes" label="默认准备时间（仿真分钟）" rules={[{ required: true }]}><InputNumber min={1} max={1440} precision={0} /></Form.Item>
      <Button type="primary" htmlType="submit" loading={pending}>保存偏好</Button>
    </Form>
  </>;
}
export default function PreferencesPanel({ homeId }: { homeId: string }) {
  const query = useQuery({ queryKey: ['preferences', homeId], queryFn: preferencesApi.get, networkMode: 'always', retry: false, refetchOnWindowFocus: false, refetchOnReconnect: false });
  return <div className={styles.preferenceLayout}><section className={`${styles.card} ${styles.preferences}`} aria-label="家庭偏好">
    <h2>舒适与习惯</h2><p className={styles.hint}>作为新规则任务的默认值，任务中仍可明确指定温度。修改不会改写过去的任务。</p>
    {query.isError && <Alert type="error" title={query.error.message} action={<Button onClick={() => { void query.refetch(); }}>重试读取</Button>} />}
    {!query.data ? <Spin /> : <Editor data={query.data} refresh={() => query.refetch()} />}
  </section><aside className={styles.preferenceInfo}>
    <h2>让任务沿用你的习惯</h2>
    <p>回家与睡眠场景会带入相应的目标温度。风速和准备时间也会作为新任务的默认值。</p>
    <div><strong>随时调整</strong><p>创建任务时仍可明确指定温度与作用房间。</p></div>
    <div><strong>历史保持原样</strong><p>保存只影响之后的新任务，不会改写已保存的任务或立即控制设备。</p></div>
    <small>温度与准备时间用于当前仿真环境。</small>
  </aside></div>;
}
