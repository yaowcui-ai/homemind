# M3 账号隔离、业务持久化与规则基线

日期：2026-10-27（Asia/Shanghai）。用户“继续下一步。”授权完成既定 M3；本文件细化已批准范围，不增加模型、SSE、设备驱动或 M6 恢复调度。

## 交付边界与实现选择

采用 MySQL 8.4、SQLAlchemy 2.0 async/asyncmy、Alembic，单个 API 执行进程。复用 M2 的 SimulationService：从当前家庭的关系记录重建引擎，在家庭事务内修改并保存，读回独立快照。无缓存全局 demo-home，无隐式 SQLite/内存降级。SQLite 只可由单元测试显式注入数据库对象；MySQL 集成与重启检查另用真实独立实例验证。

选择不透明 Cookie 会话，不增加 JWT 刷新链；选择关系表保存房间/实体和任务事实，不建立同一事实的 JSON 与关系双份权威。事务中的纯仿真副作用和结果可共同提交；不据此声称外部硬件恰好一次。M3 规则模板表单不接自然语言模型。

数据库是新 Compose 项目 `homemind`，MySQL 服务 `mysql`，卷 `homemind_mysql_data`，仅映射 `127.0.0.1:13306`。应用库/用户为 `homemind_app`，独立集成库/用户为 `homemind_test`。项目脚本创建随机 root/app/test 凭据，只存忽略的 `.local/mysql.env` 和本项目 `backend/.env`，日志不打印凭据或 DSN。数据库资源标签必须有项目名和安装 UUID；同名容器/卷不属当前安装则拒绝复用或重建。开发端口冲突直接报错。

迁移不是应用启动时的 create_all。迁移命令先检查库名属于本项目和安装标记；首次仅对确认空库显式 `--initialize-empty`，已有非本项目表/不匹配标记则拒绝。应用启动验证迁移版本和安装标记。缺失配置返回中文 503，不伪造已连接；/health 仍只表示进程存活。

## 数据模型

表名前缀 `hm_`，外加 Alembic 的版本表。时间戳用 UTC 秒整数，避免本地时区混淆。所有家庭业务表携带 home_id 并有外键；查询同时限定当前 home_id，不先按任意 ID 取数据再由前端过滤。

- installation：固定主键、安装 UUID、创建时刻。匹配本项目配置。
- users：不可变 UUID、规范化唯一 username、Argon2id password_hash、创建时刻。用户名为 3—32 位 ASCII 字母数字/下划线，规范为小写；密码 12—128 字符，密码不 strip、不存明文。
- sessions：Cookie 随机值的 SHA256 为主键、nullable user_id、CSRF 随机值、12 小时绝对过期时间。匿名会话用于登录/注册防护；认证时轮换 session 和 CSRF、撤销旧会话。
- homes：UUID、唯一 user_id、world_id、revision、config_revision、simulated_minutes、event_sequence。注册事务一次创建独立模板；后续加载不按“缺实体”重新播种。
- rooms：id、home_id、name、initial_temperature/temperature（Decimal）、主温度/占用 ID。物理真值不经公开接口泄露。
- entities：id、home_id、room_id、name、type、config/state JSON、enabled/available/known/archived、version、observed_at_minutes、Decimal energy_watt_minutes、fault_mode、delay_minutes、pending JSON。保留归档记录；不因房间删除丢掉历史快照。
- preferences：home_id、version、data JSON，保存 comfort_temperature_c=26、sleep_temperature_c=27、fan_mode=low、arrival_lead_minutes=20。合法温度为 16—30 整数，lead 为 1—1440，风速 low/auto；任务复制当时版本和值。
- tasks：id、home_id、idempotency_key、request_hash、request JSON、scenario、status、world_id、initial_snapshot、preferences_snapshot、plan、final_snapshot、verification JSON、created_at/updated_at。唯一约束 (home_id,idempotency_key)。历史不引用可变名称作为唯一证据。
- actions：id、home_id、task_id、顺序、entity_id、当时名称/房间、参数、status、transport_outcome、说明与读回事实。归档后仍可解释。
- events：home_id、单调 sequence、可选 task_id/entity_id、仿真时刻、kind、message、data。M2 最近 50 条是该家庭事件的快照投影；持久历史不止 50 条。

可在实体记录 JSON 中保存完整归档快照，或从归档实体行重建；不保存锁等运行对象。引擎 codec 必须完整覆盖 Decimal、归档、待执行动作、版本、时钟及事件序号。快照 home_id 取认证家庭，绝不能继续返回 demo-home。

## 认证和请求防护

Cookie 名 `homemind_session`，HttpOnly、SameSite=Lax、Path=/，生产 Secure。随机会话值仅 Cookie 内持有，数据库存摘要；不使用 localStorage 保存认证令牌。认证前后的 GET /auth/session 返回当前 CSRF；所有写接口要求准确的允许 Origin、JSON 请求体（有请求体时）及 `X-CSRF-Token`，Origin 缺失、跨站或令牌错误返回 403。无会话/已退出访问业务返回 401，其他家庭对象返回 404。默认允许本机前端 5174 与 API 文档 8100 的明确 Origin；测试显式配置 testserver。

密码用 Argon2id（memory_cost=65536 KiB、time_cost=3、parallelism=2），错误登录统一信息；对注册和登录尝试做有界进程内速率限制，不宣称分布式防护。会话过期和退出均不可再操作。禁止凭请求体指定 home_id/user_id；跨账号实体、房间、任务、保留项、偏好及调试均检查归属。

| 接口 | 请求 | 返回 |
| --- | --- | --- |
| GET /auth/session | 无 | AuthSession；需要时创建匿名 Cookie |
| POST /auth/register | username,password + CSRF | AuthSession；原子创建账号/家庭/一次模板/会话 |
| POST /auth/login | username,password + CSRF | AuthSession；轮换 Cookie/CSRF |
| POST /auth/logout | {} + CSRF | AuthSession（user=null，新匿名会话） |
| GET /preferences | 认证 | Preferences |
| PATCH /preferences | 指定允许字段 + CSRF | 新版本 Preferences |

```ts
interface AuthSession {
  user: { id:string; username:string; home_id:string } | null;
  csrf_token:string;
  simulation_debug_enabled:boolean;
}
interface Preferences {
  version:number;
  comfort_temperature_c:number;
  sleep_temperature_c:number;
  fan_mode:'low'|'auto';
  arrival_lead_minutes:number;
}
```

现有 /simulation 配置/读取/控制路径与 M2 的 Snapshot/ControlResult 契约保持，全部经过认证家庭事务。事件/故障/advance/reset 属显式 `simulation_debug_enabled` 功能，默认关闭；本阶段本地配置显式开启并显示提示，关闭时返回 403 或不挂载调试路由。普通家庭读取/配置/控制在 production 可使用，不能保留公开未鉴权 M2 后门。

## 规则请求、约束与执行

```ts
type Scenario = 'homecoming'|'sleep'|'away';
interface RuleRequest {
  scenario:Scenario;
  room_ids:string[]; // 非空、去重；回家/睡眠恰好一房间，离家可多房间
  target_temperature_c?:number; // 回家/睡眠可覆盖偏好，16—30 整数
  ready_in_minutes?:number; // 回家可覆盖偏好，1—1440
  keep_entity_ids?:string[];
  protected_room_ids?:string[];
  expected_world_id?:string;
}
```

所有引用先校验归属、存在和启用状态；没有传入温度/提前量时用保存偏好并存进规范请求。无意义额外字段（如离家传温度/提前量）拒绝 422。目标房间同时被保护是明确冲突，拒绝 422，不擅自降低限制。保留实体不产生控制动作，保护房间不产生设备写入；不从有人信号推断睡眠。

三个模板明确向用户展示动作含义：

- homecoming：所选房间全部非保留灯按各自保存默认亮度打开、窗帘合上、空调按明确目标和偏好风速制冷；目标时刻是当前仿真分钟 + ready_in_minutes。
- sleep：所选房间全部非保留灯关闭、窗帘合上、空调按睡眠温度和偏好风速制冷。不会触碰其他房间。
- away：所选房间全部非保留灯/空调关闭、窗帘合上；这是用户显式选择的关闭范围，不根据部分占用推断全屋无人。

按当前配置发现所有目标类型，不能依赖房间名称或默认数量。缺少所需设备/有效主温度时记录缺失条件；开窗或窗户未知时不启动制冷，说明需要手动确认，不伪造关窗动作。其余合法动作可以完成，记录 partial/failed。温度目标不能用“设温成功”替代。

统一 validator 检查家庭/能力/范围/保留/保护/预期 world，再交统一 executor 调用绝对动作与独立观察核验。M3 纯仿真任务在一次家庭事务内写动作意图、执行和最终保存；错误事务回滚其私有引擎状态，不改变已提交家庭。实际设备的跨事务恢复留给 M6。

同家庭最多一个规则执行任务；进程内立即占用标记用于忙碌 409，家庭事务锁串行化读改写。不同家庭使用不同锁。接口以单进程为限制，不声称分布式队列。等待核验释放占用，不隐式再次执行动作。

POST /tasks 要求 Idempotency-Key（8—128 字符，字母数字 . _ : -）。摘要取经过校验的请求规范化 JSON；同家庭同键同内容返回原任务，不新增动作/事件；异内容 409。不同家庭相同键不冲突。幂等重放先于 busy 拒绝，以便安全取得原结果。

| 接口 | 说明 |
| --- | --- |
| POST /tasks | 创建并内联执行规则任务；保存并返回 TaskDetail |
| GET /tasks | 当前家庭最近 50 个 TaskSummary，按创建时刻倒序 |
| GET /tasks/{id} | 当前家庭完整 TaskDetail；其他家庭 404 |
| POST /tasks/{id}/verify | 只核验已保存条件，不重发设备动作；返回 TaskDetail |

```ts
type TaskStatus = 'queued'|'running'|'waiting_input'|'waiting_verification'|'succeeded'|'partial'|'failed'|'cancelled';
interface TaskSummary {
  id:string; scenario:Scenario; status:TaskStatus; created_at:number; updated_at:number;
  world_id:string; message:string;
}
interface ActionView {
  id:string; entity_id:string; entity_name:string; room_name:string;
  action:string; parameters:Record<string,string|number|boolean>;
  status:'planned'|'submitted'|'verified'|'failed'|'unknown'|'skipped';
  transport_outcome:string|null; message:string;
}
interface Verification {
  due_at_minutes:number|null;
  checked_at_minutes:number;
  conditions:Array<{label:string; outcome:'verified'|'failed'|'unknown'|'pending'; message:string}>;
}
interface TaskDetail extends TaskSummary {
  request:RuleRequest;
  preferences_snapshot:Preferences;
  initial_snapshot:Snapshot;
  final_snapshot:Snapshot;
  actions:ActionView[];
  verification:Verification;
}
```

全部必需条件核验通过才 succeeded。回家任务目标时刻未到时为 waiting_verification；睡眠已执行但温度未达也为 waiting_verification，明确未达标；失败或无法确认动作/缺失能力保留 partial/failed。响应丢失但独立可读回时可将动作标 verified，同时保留 transport_outcome=unknown；读数未知不能升级成功。到期核验条件失败记录失败/部分，未知记录未知/部分。reset 后未完成的旧任务不能写新环境，核验说明 world 已变并结束为 failed/partial；已完成历史保持原结果。GET 不隐式核验或推进时间。M3 没有取消、后台调度、模型重规划或检查点恢复。

## 前端与验收

未登录显示注册/登录；认证恢复中不渲染旧家庭。Cookie 配合 CSRF 访问现有控制台；查询以 home_id 分键，退出/切换会话时取消请求、清理家庭/任务/偏好缓存，不闪现旧账号设备。清理不是仅靠前端隔离，后端仍完整鉴权。

保留 M2 样式，增加账号信息/退出、规则任务视图、三个模板/作用房间/保留设备/目标参数、任务结果/动作与目标核验。偏好提供最小表单。提交失败保留幂等键，同内容重试不重复任务；更改内容才换键。所有可创建资源的表单继续阻止并发重复提交。

用 SQLite 注入的快速单元/API 测试验证程序分支，原 M2 仿真测试迁移到明确认证的测试客户端。真实 MySQL 另验迁移、两个账号隔离、跨 ID 拒绝、Cookie/CSRF/退出、重复初始化与归档、幂等和并发占用；真实 API 进程重启后读取配置、环境、偏好及历史。浏览器执行登录/注册、三模板和原 M2 操作/手机回归。不调用模型，不用替身声称 MySQL/Compose/重启已通过。

参考：[SQLAlchemy AsyncSession 并发约定](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)、[OWASP Cookie 写请求防护](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)、[OWASP 密码保存](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)。具体版本以实际安装后的 uv.lock 和 MySQL 镜像摘要为准。

## 验收中固定的边界细节

- 迁移链为 `0001_m3` → `0002_m3`；0002 只将任务幂等键列设为 `utf8mb4_bin`，不依赖服务器默认排序规则，也修复已初始化的安装。模型用 MySQL 类型变体，SQLite 测试不假装支持 MySQL 排序规则。
- 回家 deadline 未到时不能成功；首次在恰好该仿真分钟核验时保存各房间证据，之后不覆盖。首次核验已超过 deadline 且没有当时证据，温度条件为 unknown、任务 partial，不能把晚达到的温度当作按时完成。M3 不自动采样；该限制在 UI/README 说明。已成功任务 verify 为归属检查后的只读重放，不改写完成快照或时间戳。
- 未确认提交的 TaskSubmission 保存在账号 Workspace 生命周期内，跨视图保留，实际退出/切换家庭时丢弃。部分/失败任务也可显式 verify，但不重新发送动作。
- 标签页通过 BroadcastChannel 通知认证变化；不可用时只在 localStorage 写随机通知标记，不存账号或认证令牌。恢复焦点/pageshow 再读会话。核对期间页面及浮层隐藏并禁止交互；同账号保留已挂载表单/导航/重试状态，确认不同身份才清缓存并按 home_id 重新挂载。
- Compose 的环境由本项目已验证值覆盖继承的同名变量，包含固定镜像摘要；不能因外部终端遗留变量生成与记录不符的凭据、标签或镜像。
