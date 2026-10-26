import { useRef } from 'react';
import { Form, Input, InputNumber, Modal, Select, Switch } from 'antd';
import { simulationApi } from '../../api/simulation';
import type { EntityType, EntityView, RoomView, Snapshot } from '../../api/simulation.types';
import { entityLabels } from './labels';
import type { Operation } from './labels';
import styles from './Simulation.module.css';

interface SharedProps { snapshot: Snapshot; run: Operation; pending: boolean; onClose: () => void }
interface RoomValues { name: string; initial_temperature_c: number; primary_temperature_entity_id?: string; primary_occupancy_entity_id?: string }

export function RoomModal({ room, snapshot, run, pending, onClose }: SharedProps & { room?: RoomView }) {
  const [form] = Form.useForm<RoomValues>();
  const submitting = useRef(false);
  const options = (type: EntityType) => snapshot.entities.filter((e) => e.room_id === room?.id && e.type === type && e.enabled).map((e) => ({ value: e.id, label: e.name }));
  async function submit(values: RoomValues) {
    if (pending || submitting.current) return;
    submitting.current = true;
    try {
      const ok = room
        ? await run(() => simulationApi.updateRoom(room.id, {
          name: values.name,
          primary_temperature_entity_id: values.primary_temperature_entity_id ?? null,
          primary_occupancy_entity_id: values.primary_occupancy_entity_id ?? null,
        }), '房间配置已更新')
        : await run(() => simulationApi.addRoom(values.name, values.initial_temperature_c), '房间已创建');
      if (ok) onClose();
    } finally { submitting.current = false; }
  }
  return <Modal open title={room ? '编辑房间' : '新增房间'} onCancel={onClose} onOk={() => form.submit()} confirmLoading={pending} okText="保存房间" cancelText="取消" destroyOnHidden>
    <p className={styles.formHint}>房间通过稳定 ID 关联实体，改名不会使设备丢失。主读数缺失时显示未知。</p>
    <Form form={form} disabled={pending} layout="vertical" onFinish={(values) => { void submit(values); }} initialValues={{
      name: room?.name ?? '', initial_temperature_c: 27,
      primary_temperature_entity_id: room?.primary_temperature_entity_id ?? undefined,
      primary_occupancy_entity_id: room?.primary_occupancy_entity_id ?? undefined,
    }}>
      <Form.Item name="name" label="房间名称" rules={[{ required: true, whitespace: true, message: '请输入房间名称' }, { max: 40, message: '最多 40 个字符' }]}><Input maxLength={40} /></Form.Item>
      {!room && <Form.Item name="initial_temperature_c" label="初始室温（℃）" rules={[{ required: true }]}><InputNumber min={0} max={50} step={0.1} /></Form.Item>}
      {room && <>
        <Form.Item name="primary_temperature_entity_id" label="主温度传感器"><Select allowClear placeholder="未绑定，温度显示未知" options={options('temperature')} /></Form.Item>
        <Form.Item name="primary_occupancy_entity_id" label="主人体存在传感器"><Select allowClear placeholder="未绑定，占用显示未知" options={options('occupancy')} /></Form.Item>
      </>}
    </Form>
  </Modal>;
}

interface EntityValues {
  name: string; room_id: string; type: EntityType; enabled: boolean;
  default_brightness_pct: number; initial_target_temperature_c: number; initial_position_pct: number;
  initial_occupied: boolean; initial_open: boolean;
}

export function EntityModal({ entity, roomId, snapshot, run, pending, onClose }: SharedProps & { entity?: EntityView; roomId?: string }) {
  const [form] = Form.useForm<EntityValues>();
  const submitting = useRef(false);
  const type = Form.useWatch('type', form) ?? entity?.type ?? 'light';
  async function submit(values: EntityValues) {
    if (pending || submitting.current) return;
    submitting.current = true;
    try {
      const config: Record<string, number | boolean> = {};
      if (values.type === 'light') config.default_brightness_pct = values.default_brightness_pct;
      if (values.type === 'climate') config.initial_target_temperature_c = values.initial_target_temperature_c;
      if (values.type === 'cover') config.initial_position_pct = values.initial_position_pct;
      if (values.type === 'occupancy') config.initial_occupied = values.initial_occupied;
      if (values.type === 'window') config.initial_open = values.initial_open;
      const ok = entity
        ? await run(() => simulationApi.updateEntity(entity.id, { name: values.name, room_id: values.room_id, enabled: values.enabled, config }), '实体配置已更新')
        : await run(() => simulationApi.addEntity({ name: values.name, room_id: values.room_id, type: values.type, config }), '实体已创建');
      if (ok) onClose();
    } finally { submitting.current = false; }
  }
  return <Modal open title={entity ? '编辑实体' : '新增实体'} onCancel={onClose} onOk={() => form.submit()} confirmLoading={pending} okText="保存实体" cancelText="取消" destroyOnHidden>
    <p className={styles.formHint}>能力由实体类型定义。传感器只提供读数，模拟事件在房间卡片中操作。迁移主传感器会清除原房间的绑定。</p>
    <Form form={form} disabled={pending} layout="vertical" onFinish={(values) => { void submit(values); }} initialValues={{
      name: entity?.name ?? '', room_id: entity?.room_id ?? roomId ?? snapshot.rooms[0]?.id,
      type: entity?.type ?? 'light', enabled: entity?.enabled ?? true,
      default_brightness_pct: entity?.config.default_brightness_pct ?? 60,
      initial_target_temperature_c: entity?.config.initial_target_temperature_c ?? 26,
      initial_position_pct: entity?.config.initial_position_pct ?? 100,
      initial_occupied: entity?.config.initial_occupied ?? false,
      initial_open: entity?.config.initial_open ?? false,
    }}>
      <Form.Item name="name" label="实体名称" rules={[{ required: true, whitespace: true, message: '请输入实体名称' }, { max: 60, message: '最多 60 个字符' }]}><Input maxLength={60} /></Form.Item>
      <Form.Item name="room_id" label="所属房间" rules={[{ required: true, message: '请选择房间' }]}><Select options={snapshot.rooms.map((r) => ({ value: r.id, label: r.name }))} /></Form.Item>
      <Form.Item name="type" label="实体类型" rules={[{ required: true }]}><Select disabled={!!entity} options={Object.entries(entityLabels).map(([value, label]) => ({ value, label }))} /></Form.Item>
      {type === 'light' && <Form.Item name="default_brightness_pct" label="默认开灯亮度（%）" rules={[{ required: true }]}><InputNumber min={1} max={100} precision={0} /></Form.Item>}
      {type === 'climate' && <Form.Item name="initial_target_temperature_c" label="初始目标温度（℃）" rules={[{ required: true }]}><InputNumber min={16} max={30} precision={0} /></Form.Item>}
      {type === 'cover' && <Form.Item name="initial_position_pct" label="初始开度（%）" rules={[{ required: true }]}><InputNumber min={0} max={100} precision={0} /></Form.Item>}
      {type === 'occupancy' && <Form.Item name="initial_occupied" label="初始有人" valuePropName="checked"><Switch /></Form.Item>}
      {type === 'window' && <Form.Item name="initial_open" label="初始开窗" valuePropName="checked"><Switch /></Form.Item>}
      {entity && <Form.Item name="enabled" label="启用实体" valuePropName="checked"><Switch /></Form.Item>}
    </Form>
  </Modal>;
}
