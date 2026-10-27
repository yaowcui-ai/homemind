# M3 账号隔离、持久化与规则基线验证

日期：2026-10-27（Asia/Shanghai）。用户“继续下一步。”授权 M3；从 M2 提交 `8ad99fd` 开始，分支 `codex/m3-accounts-persistence`。本阶段完成后停在 M4 前。

## 交付事实

- 新 Compose 项目 `homemind`，MySQL 8.4.11；专属容器/卷和安装 UUID，loopback 13306。应用与测试分库分账号，随机凭据只在本项目忽略的配置中；脚本拒绝接管同名不匹配资源，不清库重建。
- SQLAlchemy async/asyncmy 关系存储、Alembic `0001_m3` → `0002_m3`，安装/迁移检查；无隐式内存或 SQLite 降级。0002 明确任务幂等键的二进制排序规则，适用于已初始化安装。
- Argon2id、HttpOnly Cookie、不透明会话摘要、CSRF/Origin、认证轮换与退出；全部现有配置、设备、调试、偏好、任务接口限定当前家庭。
- 注册原子创建一次独立两房十二实体模板；加载不播种，归档不复活。房间/实体/物理与观察状态、版本、时钟、能耗、故障和延迟动作均可存取。
- 偏好版本、任务/动作/事件和当时名称/快照持久化。三个规则模板按当前配置发现设备，校验保留、保护、能力、开窗/未知和 world_id，再统一执行绝对动作并独立核验。
- 请求按家庭幂等，同键异内容冲突，同家庭即时执行占用与事务串行。成功历史不可被后续 verify 改写；其他未完成/未知条件可显式核验，核验不重发动作。
- 注册登录、账号切换、规则任务、偏好、结果与目标核验网页；会话代次丢弃迟到响应，按家庭查询分键。跨视图/同账号焦点核对保留未确认提交键；实际身份变化清理缓存与旧家庭组件。
- 跨标签页通知不含认证令牌；核对期间页面和弹窗/下拉等浮层一并隐藏且 inert，同身份恢复保留草稿。调试功能默认关闭，本地演示显式开启。
- API 与前端版本 0.3.0、stage=M3；没有模型调用。

## 最终检查

| 检查 | 实际结果 | 证据/覆盖 |
| --- | --- | --- |
| 后端单元与 API | 153 passed，3 明确 gated skips | `m3-final-backend-unit.txt`；SQLite 显式注入，保留 M2 回归并增加认证/隔离、迁移、规则、故障、幂等、占用、回滚与 deadline |
| 真实 MySQL 集成 | 3 passed | `m3-final-mysql-restart.txt`；两个账号、跨 ID、退出/CSRF、存取、归档/偏好/任务、8 请求并发、键大小写与 information_schema 列排序规则 |
| 实际 API 进程重启 | passed | 同一 MySQL 测试库，两次真实 18100 API；Cookie 会话、配置/环境、归档、偏好、任务/动作和幂等重放一致 |
| 本地资源防护 | 3 passed | `scripts/tests`；继承变量不能覆盖项目值、外部资源不接管、测试目标不降级到应用库 |
| 前端单元 | 30 passed / 8 files | `m3-final-frontend-unit.txt`；Cookie/CSRF、401、迟到响应、任务重试键、部分结果核验及原 M2 行为 |
| 真实浏览器 | 21 passed，约 1.5 分钟 | `m3-final-browser-portal.txt`；真实 MySQL + 临时 API + Vite + Chromium |
| 静态与构建 | passed | 后端 Ruff/格式 36 文件，根脚本 6 文件，前端 ESLint/TypeScript/Vite；最终最大 JS 块约 378kB，无此前 500kB 警告 |
| 锁和兼容性 | passed | uv 锁 68 包、虚拟环境 67 包兼容；离线 LangChain/LangGraph/社区 MySQL 适配器及 RSA 后端检查通过 |
| 独立审阅 | 规格与质量批准 | 后端和前端/根脚本分别只读审阅，修复后定向复核；没有用审阅替代实际 MySQL 或浏览器 |

`scripts/check_compatibility.py` 本身禁止网络，其 MySQL 适配器项只证明导入/RSA 后端，不证明 LangGraph MySQL 检查点恢复。表中的真实业务 MySQL/重启来自独立 `verify_m3.py`，M6 图检查点恢复未执行。

## 真实重启证明

`python scripts/verify_m3.py` 不读取旧项目。先运行专属测试库的三个集成用例，再启动本轮独立 API，注册受控测试账号，改房间名、开灯、归档新增灯、保存偏好、执行带保留项的离家任务、推进七分钟。停止后用同一配置再次启动，原 Cookie 仍能取得同一账号，以下值逐项比较：

- 家庭与 world ID、完整独立快照相等，时钟仍为七分钟。
- 已归档一实体未复活，活动十二实体 ID 保持。
- 偏好及版本相等；任务、动作、当时结果快照保持，不因之后推进时间而改写。
- 同幂等键重放返回原任务，环境不再改变。

公开运行证明保存在 `output/m3-restart-proof.json`，不含密码、Cookie 或 CSRF。Windows 虚拟环境重定向进程与实际 API PID 分开处理：用随机 nonce 和进程命令身份核实实际 PID，仅停止本轮进程。测试 API/网页退出；本项目 MySQL 容器和持久卷保留。

## 浏览器覆盖

包含未登录拒绝、真实注册与 HttpOnly Cookie、同页与跨标签页账号切换、重新登录恢复原家庭、跨家庭引用拒绝；登录草稿与未知任务在同账号恢复焦点后保留；延迟会话响应时旧编辑弹窗不可见，确认同账号后原草稿恢复。

原 M2 十项回归继续使用新账号、真实认证与 MySQL，包括十二实体、灯/空调/窗帘、20 分钟温度/能耗、感知事件、配置迁移/归档/reset、主传感器删除、离线/丢响应/延迟、390px 和长名称。

规则浏览器验证离家动作与历史、刷新无重发、未来目标与动作分开、到目标分钟核验不重发动作、未知窗户导致部分完成、偏好新默认与手机表单；还真实执行 POST 后丢弃响应，再分别跨视图/焦点重试，确认同键和唯一任务。

## 失败与修复证据

所有下列文件位于忽略的 `output/`，失败未被通过记录覆盖：

- `m3-mysql-migration-first.txt`：应用库迁移通过，但首次冷连接测试账号缺 `cryptography`；日志未输出凭据。补运行依赖后两库迁移通过；`m3-final-provision.txt` 保留最后重复初始化结果。
- 后端 `m3-backend-*red*.txt`：认证/关系存取等先失败；deadline 晚达标错误与同分钟证据覆盖先复现，修复为首次目标分钟证据或未知/部分；成功历史重核验改写、排序规则移植问题也有 red/green。
- `m3-frontend-api-red.txt`：客户端未实现时失败，随后 Cookie/CSRF/会话和任务接口通过。
- `m3-e2e-auth-tasks-first.txt`：Windows npm 参数传递失败；第二次两项脚本因 AntD 必填星号的可访问名称定位失败，改用关联 label；第三次新增七项均通过。这些不是伪装成设备故障的结果。
- `m3-task-navigation-retry-red.txt`：真实服务端提交后中止响应，切换视图使旧组件丢键，复现重复；保存到账号 Workspace 后通过。原 trace 另存 `m3-playwright-navigation-retry-red/`。
- `m3-task-reverify-ui-red.txt`：部分完成任务没有核验入口，修复后单项与最终整套通过。
- `m3-compose-env-isolation-red.txt`：项目值覆盖约定先失败；明确给所有 Compose 调用传入本项目环境后，三个防护用例通过。
- `m3-cross-tab-red.txt`：另一标签登录 B，旧标签仍显示 A；通知与焦点核对后通过。
- `m3-focus-preservation-red.txt`：初次焦点方案误清登录输入和任务键；隐藏/inert 保留挂载树、仅身份变化清理后通过。首个修复又遇到 loading 图标使精确按钮名改变，明确按钮 aria-label 后真实重试通过。失败 trace 分别保留。
- `m3-session-portal-red.txt`：旧弹窗 portal 仍在 body，隐藏主页面不足；把所有浮层容器限定到会话表面后单项通过，最终 21 项通过。trace 另存 `m3-playwright-portal-red/`。
- `m3-final-browser.txt` 为门户修复前 20 项完整通过；最终证据以 `m3-final-browser-portal.txt` 和对应最终构建/lint 日志为准。
- 截图复核后增加“等待家庭数据加载完成”的断言，再运行四项 foundation 浏览器检查通过（`m3-final-screenshot-check.txt`）；最新手机概览包含实际两房十二实体。最终视觉调整后构建通过（`m3-final-build-visual.txt`）。

## 运行条件和边界

实际启动、停止、演示与命令见 [README](../../README.md)。MySQL 安装 UUID、镜像摘要和资源身份在本项目 `.local/`；随机凭据只在忽略配置中，没有读取或复制旧项目密钥，没有对旧数据库、账号或卷执行写操作。

**本轮启动 Docker 引擎时，已有容器按原重启策略自动恢复了运行。** 这是环境状态的额外影响，不能声称其他服务状态完全未变；后续资源操作全部限定新 HomeMind 项目，未停止或重建既有容器。

M3 只支持单执行进程和纯仿真事务。回家目标没有目标分钟证据时保留未知，不后台采样；没有真实模型/Agent、SSE、真实时间预约、取消/重规划、图检查点恢复、硬件或公网部署。温度/能耗是假设，不证明真实节电。CI 配置完成并本地检查，没有对外发布或声称远端 CI 已运行。

下一步为 M4 LangGraph 单 Agent 闭环，需用户再次发起。
