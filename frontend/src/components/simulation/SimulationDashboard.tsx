import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Alert, Button, Empty, Popconfirm, Spin } from 'antd';
import { PlusOutlined, ReloadOutlined, UndoOutlined } from '@ant-design/icons';
import { simulationApi } from '../../api/simulation';
import type { ControlResult, EntityView, RoomView, Snapshot } from '../../api/simulation.types';
import EntityCard from './EntityCard';
import FamilyConfiguration from './FamilyConfiguration';
import { EntityModal, RoomModal } from './ConfigurationForms';
import FaultPanel from './FaultPanel';
import type { Operation } from './labels';
import styles from './Simulation.module.css';

interface Props { view: 'overview' | 'configuration'; homeId: string; debugEnabled: boolean }

export default function SimulationDashboard({ view, homeId, debugEnabled }: Props) {
  const query = useQuery({
    queryKey: ['simulation', homeId], queryFn: simulationApi.getSnapshot,
    networkMode: 'always', retry: false, refetchOnWindowFocus: false, refetchOnReconnect: false,
  });
  const [notice, setNotice] = useState<{ type: 'success' | 'warning' | 'error'; text: string } | null>(null);
  const [roomEditor, setRoomEditor] = useState<{ room?: RoomView } | null>(null);
  const [entityEditor, setEntityEditor] = useState<{ entity?: EntityView; roomId?: string } | null>(null);
  const [faultId, setFaultId] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: async (operation: () => Promise<Snapshot | ControlResult>) => {
      const result = await operation();
      const readback = await query.refetch();
      if (readback.isError) throw new Error('操作已提交，但状态读取失败，请先刷新确认实际结果。');
      return result;
    },
    networkMode: 'always',
  });
  const run: Operation = async (operation, success = '配置已更新') => {
    setNotice(null);
    try {
      const result = await mutation.mutateAsync(operation);
      if ('outcome' in result) setNotice({ type: result.outcome === 'verified' ? 'success' : result.outcome === 'failed' ? 'error' : 'warning', text: result.message });
      else setNotice({ type: 'success', text: success });
      return true;
    } catch (error) {
      setNotice({ type: 'error', text: error instanceof Error ? error.message : '操作未完成，请刷新后重试。' });
      return false;
    }
  };
  const snapshot = query.data;
  if (!snapshot) return <section className={styles.fetchError}>
    {query.isFetching ? <Spin description="正在读取仿真家庭…" /> : <Alert type="error" title="尚未读取家庭状态" description={query.error?.message} action={<Button onClick={() => { void query.refetch(); }}>重读家庭</Button>} />}
  </section>;

  const pending = mutation.isPending || query.isFetching || query.isError;
  const faultEntity = snapshot.entities.find((e) => e.id === faultId);
  return <>
    <Alert className={styles.banner} type="info" showIcon title="个人家庭 · 配置与状态持续保存" description={`当前账号拥有独立家庭。设备状态、温度和能耗均为仿真数据。${debugEnabled ? '演示控制已开启，可模拟环境变化与设备故障。' : ''}`} />
    {notice && <Alert type={notice.type} showIcon title={notice.text} closable onClose={() => setNotice(null)} />}
    {query.isError && <Alert type="warning" title="当前展示上一次状态，暂时禁止操作" description={query.error.message} />}

    <section className={styles.metrics} aria-label="当前家庭概况">
      <div className={styles.metric}><span>房间</span><strong data-testid="room-count">{snapshot.rooms.length}<small>间</small></strong></div>
      <div className={styles.metric}><span>配置实体</span><strong data-testid="entity-count">{snapshot.entities.length}<small>个</small></strong></div>
      <div className={styles.metric}><span>累计仿真能耗</span><strong>{snapshot.energy_wh.toFixed(3)}<small>Wh</small></strong></div>
      <div className={styles.metric}><span>已归档实体</span><strong>{snapshot.archived_count}<small>个</small></strong></div>
    </section>

    <section className={styles.toolbar} aria-label="仿真时间控制">
      <div><span className={styles.clockLabel}>仿真时钟 · 室外参数 {snapshot.outdoor_temperature_c}℃</span><strong className={styles.clockValue}>t + {snapshot.simulated_minutes}<small>分钟</small></strong></div>
      <div className={styles.toolbarActions}>
        {debugEnabled && [1, 5, 20].map((minutes) => <Button key={minutes} disabled={pending} onClick={() => { void run(() => simulationApi.advance(minutes), `已推进 ${minutes} 分钟`); }}>推进 {minutes} 分钟</Button>)}
        <Button aria-label="读取状态" icon={<ReloadOutlined />} loading={query.isFetching} disabled={mutation.isPending} onClick={() => { void query.refetch(); }}>读取状态</Button>
        {debugEnabled && <Popconfirm title="重置本次仿真运行？" description="保留房间、实体与配置；清除运行状态、故障和延迟动作，生成新的环境实例。" okText="确认重置" cancelText="取消" onConfirm={() => { void run(() => simulationApi.reset(), '运行状态已重置，用户配置保持不变'); }}>
          <Button aria-label="重置运行" icon={<UndoOutlined />} disabled={pending}>重置运行</Button>
        </Popconfirm>}
      </div>
    </section>

    {view === 'configuration' ? <FamilyConfiguration snapshot={snapshot} run={run} pending={pending} onRoom={(room) => setRoomEditor({ room })} onEntity={(entity, roomId) => setEntityEditor({ entity, roomId })} />
      : <>
        {snapshot.rooms.length === 0 && <div className={styles.empty}><Empty description="当前没有房间" /><Button type="primary" onClick={() => setRoomEditor({})}>新增房间</Button></div>}
        {snapshot.rooms.map((room) => <section className={styles.room} key={room.id} aria-label={`${room.name}房间`}>
          <div className={styles.roomHead}>
            <div><h2>{room.name}</h2><p>
              <span>室温 {room.temperature_c === null ? '未知' : `${room.temperature_c.toFixed(1)}℃`}</span>
              <span>占用 {room.occupied === null ? '未知' : room.occupied ? '有人' : '无人'}</span>
              <span>窗户 {room.window_open === null ? '未知' : room.window_open ? '打开' : '已监测窗户关闭'}</span>
            </p></div>
            <div className={styles.roomButtons}>
              <Button disabled={pending} onClick={() => setRoomEditor({ room })}>房间设置</Button>
              <Button icon={<PlusOutlined />} disabled={pending} onClick={() => setEntityEditor({ roomId: room.id })}>新增实体</Button>
            </div>
          </div>
          <div className={styles.entityGrid}>
            {snapshot.entities.filter((e) => e.room_id === room.id).map((entity) => <EntityCard
              key={`${entity.id}:${entity.version}`} entity={entity} worldId={snapshot.world_id} run={run} pending={pending} debugEnabled={debugEnabled}
              onEdit={(e) => setEntityEditor({ entity: e })} onFault={(e) => setFaultId(e.id)}
            />)}
          </div>
          {!snapshot.entities.some((e) => e.room_id === room.id) && <Empty description="房间中还没有实体" />}
        </section>)}
      </>}

    <section className={styles.eventList} aria-label="最近仿真事件">
      <h2>最近变化 <small>· 本家庭记录</small></h2>
      {snapshot.recent_events.length === 0 && <p>还没有变更。试着打开一盏灯，或推进仿真时间。</p>}
      {[...snapshot.recent_events].reverse().slice(0, 8).map((event) => <p key={event.sequence}><time>t+{event.at_minutes}m</time><span>{event.message}</span></p>)}
    </section>
    {roomEditor && <RoomModal key={roomEditor.room?.id ?? 'new-room'} {...roomEditor} snapshot={snapshot} run={run} pending={pending} onClose={() => setRoomEditor(null)} />}
    {entityEditor && <EntityModal key={entityEditor.entity?.id ?? `new-${entityEditor.roomId ?? ''}`} {...entityEditor} snapshot={snapshot} run={run} pending={pending} onClose={() => setEntityEditor(null)} />}
    {debugEnabled && faultEntity && <FaultPanel key={faultEntity.id} entity={faultEntity} run={run} pending={pending} onClose={() => setFaultId(null)} />}
  </>;
}
