# M2 可配置家庭与设备仿真实施设计

日期：2026-10-26。依据已批准的总体设计和十二实体设计，作为用户“开始下一步”所授权 M2 的实施细化。

## 阶段边界

使用进程内的 `demo-home`，不实现注册、数据库、Agent、SSE 或持久化恢复。页面明确提示内存保存、重启恢复默认；M3 再持久化并加入账号归属。生产环境不开放此未鉴权的仿真路由。

后端一个受锁保护的仿真服务管理配置、环境与变更事件，所有读取返回独立快照，控制与模拟事件使用不同接口。前端按快照渲染房间和实体，不将空缺传感器当作已知状态。

## 默认模型与精度

- 时间从 0 分钟开始，每次推进 1—1440 个整数分钟，逐分钟更新，读取不推进时间。
- 室外温度固定 32℃；新增房间默认 27℃，创建时可选 0—50℃。
- 室温内部保留 0.001℃，逐分钟使用十进制定点 ROUND_HALF_UP 舍入，显示 0.1℃。
- 每分钟被动变化为 `(室外温度 - 当前温度) × 系数 + 窗帘热增益 + 占用热增益`。系数关窗 0.02、开窗 0.10；窗帘热增益为平均开度 / 100 × 0.01℃（无窗帘时取完全打开）；有人时热增益为 0.01℃。
- 多个空调按不可变实体 ID 排序依次作用。开启 cool 且温度高于目标时，auto 每分钟最多降 0.22℃、low 最多降 0.15℃，不低于各自目标；制冷功率分别为 850W、550W，否则开启待机分别为 12W、8W，关闭为 0。
- 灯开启时功率为 `2 + 四舍五入(10 × 亮度/100)` W；关闭为 0。窗帘每次实际改变开度记 0.05Wh，重复设置相同开度不额外耗能；传感器耗能暂不计。
- 按设备累计瓦分钟，输出 energy_wh 保留 0.001Wh。所有数字是透明的仿真假设，不能作为真实物理预测或节电结论。
- 温度来自房间内部热状态，温度传感器只是观察者；移除或离线不会让热状态消失。占用与窗户的物理信号独立于观测质量保存，已配置可用信号的模拟值驱动模型。缺失观测时 Agent 可见聚合值为未知，模型采用的内部环境假设不对外伪装为读数。

## 接口契约

Vite 将 `/api/simulation` 转发为后端 `/simulation`。下文所有实体和房间 ID 均由服务端生成且稳定，客户端不能传入其他家庭。未找到返回 404，非法能力/参数返回 422，非空房间删除或待执行动作冲突返回 409。业务错误结构为 `{"detail":{"code":"...","message":"中文说明"}}`，不返回堆栈。

| 方法与路径 | 请求体 | 返回 |
| --- | --- | --- |
| GET /simulation | 无 | Snapshot |
| POST /simulation/rooms | name, initial_temperature_c 可选 | Snapshot |
| PATCH /simulation/rooms/{id} | name、primary_temperature_entity_id、primary_occupancy_entity_id 中指定字段 | Snapshot |
| DELETE /simulation/rooms/{id} | 无 | Snapshot；有未归档实体时 409 |
| POST /simulation/entities | room_id, name, type, config 可选 | Snapshot |
| PATCH /simulation/entities/{id} | name、room_id、enabled、config 中指定字段 | Snapshot |
| DELETE /simulation/entities/{id} | 无 | Snapshot；归档并取消相关延迟动作 |
| POST /simulation/controls/{id} | action, parameters, expected_world_id 可选 | ControlResult |
| POST /simulation/events | entity_id，temperature_c/occupied/window_open/available/known 中指定字段 | Snapshot |
| POST /simulation/faults/{id} | mode, delay_minutes 可选 | Snapshot |
| POST /simulation/advance | minutes | Snapshot |
| POST /simulation/reset | 空对象 | Snapshot |

### Snapshot

```typescript
type EntityType = 'light' | 'climate' | 'cover' | 'temperature' | 'occupancy' | 'window';
type FaultMode = 'none' | 'offline' | 'fail_before' | 'response_lost' | 'no_effect' | 'delayed';
interface RoomView {
  id: string; name: string;
  primary_temperature_entity_id: string | null;
  primary_occupancy_entity_id: string | null;
  temperature_c: number | null; occupied: boolean | null; window_open: boolean | null;
}
interface EntityView {
  id: string; room_id: string; name: string; type: EntityType;
  enabled: boolean; available: boolean; known: boolean;
  state: Record<string, string | number | boolean | null>;
  config: Record<string, string | number | boolean>;
  version: number; observed_at_minutes: number; energy_wh: number;
  fault: { mode: FaultMode; delay_minutes: number };
  pending_until_minutes: number | null;
}
interface SimulationEvent {
  sequence: number; at_minutes: number; kind: string; message: string;
  entity_id: string | null;
}
interface Snapshot {
  home_id: string; world_id: string; revision: number; config_revision: number;
  simulated_minutes: number; model_version: string; outdoor_temperature_c: number;
  energy_wh: number; rooms: RoomView[]; entities: EntityView[];
  archived_count: number; recent_events: SimulationEvent[];
}
interface ControlResult {
  outcome: 'verified' | 'failed' | 'unknown'; message: string;
  entity_id: string; world_id: string; revision: number;
}
```

Snapshot.entities 只列未归档实体，归档记录保留在内部及事件中；recent_events 最多 50 条，仅是进程内变更记录。房间不暴露传感器缺失时的内部真实室温。不可用、禁用或读数未知时将观测值置 null，不伪装 false 或 0。

### 类型、状态和配置

- light.state：power、brightness_pct；config：default_brightness_pct（1—100，默认 60；卧室模板 30）。
- climate.state：mode（off/cool）、target_temperature_c、fan_mode（low/auto）、hvac_action（off/idle/cooling）；config：initial_target_temperature_c（16—30 整数，默认 26；卧室模板 27）。
- cover.state：position_pct；config：initial_position_pct（0—100 整数，默认 100）。
- temperature.state：temperature_c；config：空；新增时读取房间当前热状态。
- occupancy.state：occupied；config：initial_occupied（布尔，默认 false）。
- window.state：window_open；config：initial_open（布尔，默认 false）。

config 严格按类型白名单校验，不能新增任意 capability。主温度/占用实体默认绑定模板实体；新增实体不擅自替换已有主读数，主读数被移除、移走或停用时清空绑定，用户显式选择。窗口读数聚合遵循十二实体设计的未知规则。

### 控制与事件

- set_light 参数为 power 和/或 brightness_pct；power=false 且 brightness>0 拒绝，亮度 0 关灯，单独开灯使用保存的默认亮度。
- set_climate 参数为 mode、target_temperature_c 和/或 fan_mode；只更新提供字段，不以设温隐式开机。
- set_cover 参数为 position_pct。
- 控制参数至少一个，禁止额外字段、布尔冒充数字、NaN、无限值和越界值。传感器拒绝控制接口。
- 事件接口只允许传感器对应的 temperature_c/occupied/window_open，另允许改变任何实体的 available/known；全部字段先验证再原子更新，错误请求不能产生部分修改。

### 故障与重置

- none 正常；offline 表示无法连接；fail_before 表示动作前失败；response_lost 表示已执行但返回 unknown；no_effect 表示指令受理但读回不符，返回 failed；delayed 表示排队至仿真时间（默认 2 分钟）后生效，返回 unknown。
- 故障持续到用户清除。响应丢失通过显式 unknown 模拟，不破坏 HTTP 连接；用户独立刷新状态可核验真实变化。
- 一个实体最多一个延迟动作，已有延迟动作时再次控制返回 409。移除、停用、迁移、配置变更、故障更改或 reset 取消相应延迟动作并记录事件，避免旧动作覆盖新配置。推进时间不等待真实时钟。
- reset 保留房间和实体 ID、名称、归属、主读数绑定、启用状态和配置；重置运行状态、时间、耗能、故障、观测质量及延迟动作，并生成新 world_id。已归档实体不复活，旧 expected_world_id 控制返回 409。

## 页面与验收

保留现有品牌布局，概览展示真实房间/实体数量、仿真分钟与能耗。房间内按实体生成控制/感知卡；传感器的人工按钮明确标为“模拟事件”。提供家庭配置界面、主读数选择、故障面板、手动刷新、推进 1/5/20 分钟与需确认的 reset。手机可执行核心动作，无横向溢出。

测试覆盖默认模板与独立实例、增删改和迁移、主绑定、能力边界、观察值未知、非法输入不变更、顺序执行、故障与延迟、reset 保留配置、旧世界拒绝、20 分钟与两次 10 分钟结果一致；浏览器验证实际 API 与界面操作，不仅做替身测试。
