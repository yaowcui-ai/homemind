import { Button, Empty, Popconfirm, Tag } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { simulationApi } from '../../api/simulation';
import type { EntityView, RoomView, Snapshot } from '../../api/simulation.types';
import { entityLabels } from './labels';
import type { Operation } from './labels';
import styles from './Simulation.module.css';

interface Props {
  snapshot: Snapshot; run: Operation; pending: boolean;
  onRoom: (room?: RoomView) => void;
  onEntity: (entity?: EntityView, roomId?: string) => void;
}

export default function FamilyConfiguration({ snapshot, run, pending, onRoom, onEntity }: Props) {
  return <section aria-label="家庭配置面板">
    <div className={styles.manageHeader}>
      <div><h2>把默认模板，调整成你的家</h2><p>支持六种实体类型。移除会归档记录，重置运行状态不会恢复已移除的实体。</p></div>
      <Button aria-label="新增房间" type="primary" icon={<PlusOutlined />} disabled={pending} onClick={() => onRoom()}>新增房间</Button>
    </div>
    {snapshot.rooms.length === 0 && <Empty description="先新增一个房间，再添加实体" />}
    {snapshot.rooms.map((room) => {
      const entities = snapshot.entities.filter((e) => e.room_id === room.id);
      return <section className={styles.manageRoom} key={room.id} aria-label={`${room.name}配置`}>
        <div className={styles.roomHead}>
          <div><h2>{room.name}</h2><p>{entities.length} 个配置实体</p></div>
          <div className={styles.roomButtons}>
            <Button disabled={pending} onClick={() => onRoom(room)}>编辑房间</Button>
            <Button disabled={pending} onClick={() => onEntity(undefined, room.id)}>新增实体</Button>
            <Popconfirm title="移除这个空房间？" description="有实体时需先迁移或归档。" okText="确认移除" cancelText="取消" onConfirm={() => { void run(() => simulationApi.removeRoom(room.id), '空房间已移除'); }}>
              <Button danger disabled={pending || entities.length > 0}>移除房间</Button>
            </Popconfirm>
          </div>
        </div>
        {entities.map((entity) => <div className={styles.manageRow} key={entity.id} aria-label={entity.name}>
          <div><strong>{entity.name}</strong><small>{entityLabels[entity.type]} · {entity.enabled ? '已启用' : '已停用'}
            {room.primary_temperature_entity_id === entity.id && ' · 主温度'}
            {room.primary_occupancy_entity_id === entity.id && ' · 主占用'}</small></div>
          <div className={styles.manageActions}>
            {!entity.available && <Tag color="orange">离线</Tag>}
            <Button size="small" disabled={pending} onClick={() => onEntity(entity)}>编辑实体</Button>
            <Popconfirm title={`移除“${entity.name}”？`} description="实体会归档，相关延迟动作会取消。" okText="确认移除" cancelText="取消" onConfirm={() => { void run(() => simulationApi.removeEntity(entity.id), '实体已归档'); }}>
              <Button size="small" danger disabled={pending}>移除实体</Button>
            </Popconfirm>
          </div>
        </div>)}
      </section>;
    })}
  </section>;
}
