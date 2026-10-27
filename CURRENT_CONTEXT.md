# HomeMind 当前接续

更新日期：2026-10-27（Asia/Shanghai）。

## 当前授权与进度

**最新委托：用户在 A 交付后“继续下一步”，授权产品 B；核心代码与旅程已实现、验证并交付。** 本轮不自动进入 C—E。方案：[B 设计](docs/superpowers/specs/2026-10-27-product-b-design.md)、[计划](docs/superpowers/plans/2026-10-27-product-b-single-agent.md)、[验证记录](docs/verification/product-b-single-agent.md)。用户下次“继续下一步”默认进入 C，无需重问已确认定位、模型服务或浅色视觉。

B 最终：后端209passed/4 MySQL条件skip，Agent56passed；真实MySQL最新4passed/4.52s；前端64passed，lint/TS/Vite通过。完整受控Agent浏览器10项、真实MySQL原21项通过；最后状态竞态修复后又定向复验Agent关键5项、规则任务6项通过。root已目视桌面与360px截图，360/390px几何/点击均过。独立后端规格/质量、前端规格/质量、根脚本审阅均批准。selectionVersion/writeEpoch、一次性restore、controller跨页忙锁、exact cancelQueries和取消await后代次复查均有真实RED/GREEN，不再有已知未修复质量阻塞。

**本轮真实模型两次预算已用完且通过，不再补跑真实调用。** 仅合成家庭2模型/2只读工具→严格clarify，5539输入/219输出token，5641ms、0设备动作。不是完整真实场景或模型准确率。追踪RED曾向LangSmith尝试发合成trace、401，已明确关闭追踪并封默认测试HTTP；原始失败必须保留，详见B验证。

工程历史：M3 与 Figma 浅色改版/React 同步此前完成；M4现已按产品B对齐PRD实现。用户已批准“按此方向同步，代码中修复排版”。现在执行 A—E 产品路线，不机械顺排所有旧技术模块。

本目录为独立 Git 仓库，当前分支 `codex/product-b-single-agent`：A 31604e3、B设计7655943、后端e3a59ec、灯预校验0bd2387、前端919d831；根脚本/CI/材料一并本地保存。不推送、合并或发布。父仓库通过 `.git/info/exclude` 忽略本目录，旧项目未提交改动不纳入提交。

## B 新实现

- v0.4.0/M4；迁移0003_m4增加mode/agent_run，旧任务rule。API仍单执行进程，LangGraph控制模型/工具/严格解析，服务短事务校验执行，模型时不持家庭锁。
- DeepSeek只读read_home/read_preferences、严格plan/clarify/refuse；当前只有一个规划Agent。每轮3模型/6工具、单20秒/轮65秒、输出2048token；最多3回答。保留/保护、归属、能力、窗户、重复/矛盾动作、版本过期全量检查后才执行；全屋/影响较大必要确认。
- 同task回答/确认、每轮幂等与锁内二查；取消/超时保留已发调用数与未知用量；公开问答/计划/分阶段耗时，关闭LangSmith继承追踪。复用executor独立读回，不把响应成功当目标成功。
- React任务助手自然语言/规则两入口；家庭sessionStorage保存草稿、选中及创建/回答/确认冻结body/key。刷新只读恢复；5xx保原键；晚到读/写不抢用户选择或倒退状态。
- 任务内到deadline原子推进/核验，sleep每次明确10仿真分钟；仅debug启用。普通模式阻止未来homecoming/会等待sleep，local/away可用。推进没有跨刷新持久幂等，未知结果先读当前时刻，不自动补发；这是C可靠性后续项。

## M3 工程基线（历史，B 新实现见上方与验证记录）

- Python 3.12.14 / uv；Node 24.14.1 / npm 11.11.0。版本 0.3.0、stage=M3，依赖锁已更新。
- 独立 MySQL Compose 项目 `homemind`，服务 mysql、卷 homemind_mysql_data、127.0.0.1:13306。实际 MySQL 8.4.11，app/test 分库分账号；容器/卷安装标签、镜像摘要与身份保存在 `.local/`。
- 随机凭据只在忽略的 `.local/mysql.env` 与 `backend/.env`；不可打印、提交或复制到前端，不读取旧项目密钥。Compose 显式项目环境覆盖父终端遗留值，同名资源或安装标记不匹配时拒绝接管。
- 关系表保存用户、会话、家庭、房间、实体/归档/物理状态、偏好、任务、动作与事件。迁移 `0001_m3` → `0002_m3`；后者仅将任务幂等键列明确二进制排序。应用无内存/SQLite 降级，测试 SQLite 仅显式注入。
- Cookie/Argon2id/CSRF/Origin；注册一次模板，每账号一独立家庭。全部业务、调试和任务引用限定认证 home_id；退出撤销会话。
- 保留 M2 可配置两房十二实体、控制/感知分开、Decimal 分钟热模型与能耗、故障/延迟、归档、主读数未知与保留配置的 reset。全部状态通过家庭事务重建/保存；登录或重启不播种已移除设备。
- 规则基线三个模板：homecoming/sleep/away，按配置发现实体，遵守保留/保护、窗口/主读数质量，统一绝对动作与独立核验；按家庭幂等及执行占用。任务/动作/初始偏好和快照持久保存。
- 回家目标要求恰好目标分钟的显式核验证据，首次证据不可覆盖；没有该时刻证据时不以晚达标冒充按时完成。成功历史 verify 为只读重放，其他部分/失败条件可继续核验但不重发动作。
- 网页含注册登录/退出、家庭配置、规则表单/结果、偏好。查询按 home_id 分键，代次丢弃迟到响应；标签页通知及焦点/pageshow 重新核对。核对期间页面、弹窗和浮层都 hidden/inert；同账号保留草稿和未知提交键，不同账号清缓存并重挂载。
- 用户批准的 Figma 浅色视觉已同步 React：白色 224px 侧栏、按视图标题、蓝灰主题变量、传感/可控实体分组与类型图标、明确草稿/应用操作、流式时钟控件、任务双栏、偏好说明和桌面登录双栏。360/390px 手机布局与注册已真实检查；没有修改 API、鉴权、幂等、依赖或业务数据库结构。
- 调试开关默认 false；本项目本地初始化显式 true，开启模拟事件/故障/时间推进/reset。生产普通配置/读取/控制仍鉴权，Cookie Secure。

## M3 与 Figma 历史验证

- 根代理独立最终后端：153 passed、3 MySQL-gated skips；前端 30 passed；真实浏览器最终 21 passed。
- 独立测试库实际 MySQL：3 passed；两个真实 API 进程前后比较会话、完整环境/配置、归档、偏好、任务/动作及幂等重放，一致；证据 `output/m3-restart-proof.json`。
- 根资源防护 3 passed；后端 Ruff/格式 36 文件、根脚本 6 文件、前端 ESLint/TypeScript/Vite 通过；uv 锁/67 包兼容、离线工具/图/适配器/RSA 检查通过。
- 后端规格/质量与前端/根脚本规格/质量分别独立只读审阅，问题修复后复核批准。保留冷认证依赖缺项、deadline、大小写、历史、重试键、跨标签、焦点、portal 等原始 red/green 记录。
- 桌面/手机、登录、任务结果和任务手机表单截图在 `output/m3-*.png`，已目视检查。旧 M1/M2 证据继续保留。
- CI 已配置专属 MySQL、迁移、后端/脚本/浏览器检查；本轮未发布或运行远端 CI。
- 本次界面同步：30 前端单测、ESLint、TypeScript/Vite 构建通过；21 真实浏览器回归通过。额外 2 项视觉检查覆盖各页截图及 360/390px 溢出/开关/时钟边界/手机注册；注册切换的过渡截图另做稳定样式确认，定向 1 项通过。独立规格与代码质量审阅均批准。证据、原始失败和截图在 `output/figma-sync-*`，旧 `m3-*` 保留。

## 启动与服务状态

完整步骤见 [README](README.md)。B本轮用户自行打开Docker后，`python scripts/setup_mysql.py`已保留数据迁移应用/测试库到0003_m4。已有容器N-Tester-backend占8100（不停止或接管），本项目忽略的backend/.env API端口、允许Origin及frontend/.env代理已配套改8110；网页5174。代码默认端口仍8100。普通MySQL浏览器指定HOMEMIND_E2E_API_PORT=8110；受控Agent独立夹具18110/5176、显式fresh SQLite，不是MySQL或真实模型证据。

验收临时8110/5174、18110/5176、18100进程均已退出；MySQL保留运行/数据。8100既有容器继续运行，勿接管或停止。

M3阶段历史：当时启动Docker引擎触发既有容器按原策略自动恢复，环境副作用已记录。本次B由用户自行打开引擎，助手只启动匹配安装标记的HomeMind MySQL并解决本项目端口冲突。

## 下一步

下一阶段 **C：体验与可靠性**，由用户发起后基于B的真实Bad Case与现有已知限制细化；优先验证真实模型场景表现/失败解释、推进未知结果恢复、任务中断反馈与必要确认/取消等最小需求，不自动铺开全部旧M6/M7模块。Figma新状态/连线仍待额度可用后在既有文件补齐。访谈和完整模型对照仍未开展，不能伪造；真实调用需先明确数量/预算和可核验条件。

用户补充使用背景 U01：“有少量设备，偶尔使用”。仅本人自述，未获知平台/类型，不算第三方访谈或需求验证。当前研究与真实 AI 评测均未开展，验证计划 DEV01—DEV12 为开发场景草案，保留集尚未准备/冻结。

用户已选择 **DeepSeek 官方 API**；默认 `deepseek-flash`、`https://api.deepseek.com`、非思考模式。本轮已在本项目backend/.env把用户API_KEY适配为HOMEMIND_MODEL_API_KEY并启用模型；未输出密钥、不读取旧项目密钥。基础真实接入已按上方两次合成调用通过，完整效果评测未做。此前Vite/原生依赖修复与首次/日常启动步骤保留在README。

已完成 [Figma 改版与同步](docs/superpowers/specs/2026-10-27-figma-redesign-brief.md)。插件已安装且账号连接成功，已创建 [HomeMind 设计](https://www.figma.com/design/Bo7Jqfnh4NNRQiMwNvXc2O)：5 个桌面、5 个手机主页面、手机注册、十种状态板、基础变量与设备组件，均为可编辑图层。用户已批准后实际修改 12 个前端源文件，并完成上述检查。详见 [设计记录](docs/verification/figma-redesign.md)。

Figma 灯卡开关宽度、手机时钟高度及非空房间删除禁用样式仍待回写；三次修正被 Starter MCP 额度拒绝，whoami 已核实方案，不重复写入或绕过限额。**React 中这些问题已修复/保留正确禁用，并实际验证**。这是用户批准的差异，不影响网页同步交付。Figma 文件、sessionId、节点和详细审计在 `output/figma-design-progress.json`，后续补稿复用会话，勿新建重复文件。临时验收 API/Vite 已由 Playwright 退出，本项目 MySQL 保留；没有启动常驻网页/API。

B已接入单规划Agent；多Agent、SSE、后台时钟、用户取消/自动重规划、图检查点恢复及真实硬件仍未实现，不用纯仿真事务冒充外部设备exactly-once。

入口：[路线](docs/homemind-development-roadmap.md)、[PRD](docs/product/prd.md)、[B设计](docs/superpowers/specs/2026-10-27-product-b-design.md)、[B计划](docs/superpowers/plans/2026-10-27-product-b-single-agent.md)、[B验证](docs/verification/product-b-single-agent.md)。M3历史资料从相应记录追溯。
