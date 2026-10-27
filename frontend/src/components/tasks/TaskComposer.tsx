import { useRef, useState } from 'react';
import { Alert, Button, Form, InputNumber, Select } from 'antd';
import type { TaskSubmission } from '../../api/tasks';
import type { Preferences } from '../../api/auth.types';
import type { Snapshot } from '../../api/simulation.types';
import type { RuleRequest, Scenario, TaskDetail } from '../../api/tasks.types';
import styles from './Tasks.module.css';

interface Values { scenario: Scenario; room_ids: string[]; keep_entity_ids: string[]; protected_room_ids: string[]; target_temperature_c: number; ready_in_minutes: number }
interface Props { snapshot: Snapshot; preferences: Preferences; onCreated: (task: TaskDetail) => Promise<void>; disabled: boolean; submission: TaskSubmission }
const descriptions: Record<Scenario, string> = {
  homecoming: '打开所选房间的灯、合上窗帘，按目标温度制冷；到达仿真目标时刻后核验。',
  sleep: '关闭所选房间的灯、合上窗帘，按睡眠目标制冷；其他房间保持原样。',
  away: '关闭所选房间的灯和空调，合上窗帘；保留勾选的设备，不根据占用信号推断全屋无人。',
};

export default function TaskComposer({ snapshot, preferences, onCreated, disabled, submission }: Props) {
  const [form] = Form.useForm<Values>();
  const scenario = Form.useWatch('scenario', form) ?? 'homecoming';
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);
  async function submit(values: Values) {
    if (disabled || inFlight.current) return;
    inFlight.current = true; setPending(true); setError(null);
    const body: RuleRequest = {
      scenario: values.scenario, room_ids: values.room_ids,
      keep_entity_ids: values.keep_entity_ids, protected_room_ids: values.protected_room_ids,
      expected_world_id: snapshot.world_id,
      ...(values.scenario === 'away' ? {} : { target_temperature_c: values.target_temperature_c }),
      ...(values.scenario === 'homecoming' ? { ready_in_minutes: values.ready_in_minutes } : {}),
    };
    try { await onCreated(await submission.submit(body)); }
    catch (error) { setError(error instanceof Error ? error.message : '任务提交未完成，请读取列表确认。'); }
    finally { inFlight.current = false; setPending(false); }
  }
  const roomOptions = snapshot.rooms.map((r) => ({ label: r.name, value: r.id }));
  return <section className={styles.card} aria-label="规则任务表单">
    <h2>安排一个场景</h2><p className={styles.hint}>明确选择范围与保留项。任务通过固定规则执行，不调用语言模型。</p>
    {error && <Alert type="error" title={error} description="可先读取任务列表确认结果。同内容重试会复用幂等键。" />}
    <Form form={form} layout="vertical" disabled={disabled || pending} onFinish={(v) => { void submit(v); }} initialValues={{
      scenario: 'homecoming', room_ids: snapshot.rooms.slice(0, 1).map((r) => r.id), keep_entity_ids: [], protected_room_ids: [],
      target_temperature_c: preferences.comfort_temperature_c, ready_in_minutes: preferences.arrival_lead_minutes,
    }} onValuesChange={(changed) => {
      if (changed.scenario) {
        form.setFieldValue('target_temperature_c', changed.scenario === 'sleep' ? preferences.sleep_temperature_c : preferences.comfort_temperature_c);
        if (changed.scenario !== 'away') form.setFieldValue('room_ids', (form.getFieldValue('room_ids') as string[]).slice(0, 1));
      }
    }}>
      <Form.Item label="场景模板" name="scenario" rules={[{ required: true }]}><Select options={[{ value: 'homecoming', label: '回家准备' }, { value: 'sleep', label: '睡眠模式' }, { value: 'away', label: '离家模式' }]} /></Form.Item>
      <p className={styles.templateDescription}>{descriptions[scenario]}</p>
      <Form.Item label="作用房间" name="room_ids" rules={[{ required: true, message: '至少选择一个房间' }, { validator: async (_, value: string[]) => {
        if (scenario !== 'away' && value?.length !== 1) throw new Error('回家或睡眠方案请选择一个房间');
      } }]}><Select mode="multiple" options={roomOptions} placeholder="选择当前家庭的房间" /></Form.Item>
      {scenario !== 'away' && <Form.Item label="目标温度（℃）" name="target_temperature_c" rules={[{ required: true }]}><InputNumber min={16} max={30} precision={0} /></Form.Item>}
      {scenario === 'homecoming' && <Form.Item label="准备时间（仿真分钟）" name="ready_in_minutes" rules={[{ required: true }]}><InputNumber min={1} max={1440} precision={0} /></Form.Item>}
      <Form.Item label="保留设备（不改变）" name="keep_entity_ids"><Select mode="multiple" allowClear options={snapshot.entities.filter((e) => e.enabled && ['light', 'climate', 'cover'].includes(e.type)).map((e) => ({ value: e.id, label: `${snapshot.rooms.find((r) => r.id === e.room_id)?.name} · ${e.name}` }))} /></Form.Item>
      <Form.Item label="保护房间（不执行动作）" name="protected_room_ids"><Select mode="multiple" allowClear options={roomOptions} /></Form.Item>
      <Button aria-label="执行规则任务" type="primary" htmlType="submit" loading={pending} disabled={disabled || snapshot.rooms.length === 0}>执行规则任务</Button>
    </Form>
  </section>;
}
