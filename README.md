# HomeMind

**基于 React、FastAPI 与 LangGraph 的智能家居 AI 任务助手（仿真验证版）。** 将自然语言需求转成可解释计划，经程序校验、必要确认后执行，再分别核验设备动作与目标时刻温度。应用v0.4.0，默认两房十二实体可编辑，每账号拥有独立家庭，支持规则、标准助手、增强单Agent和多Agent温控实验。

LangGraph为主、LangChain为辅；Agent只读事实，两位专家并行提出建议，由协调角色选择，统一执行器负责写设备。设备、环境、时间和Wh为确定性仿真，真实模型接DeepSeek官方API；无真实硬件、线上用户或现实节电效果声明。

[AI全栈简历项目介绍](docs/resume/homemind-ai-fullstack.md) · [系统与技术方案](docs/superpowers/specs/2026-10-28-product-d1-design.md) · [真实开发对照](docs/product/product-d4-evaluation.md) · [错误诊断与定向调优](docs/product/product-d4-followup.md) · [GitHub](https://github.com/yaowcui-ai/homemind)

最终候选已完成 [D5 冻结新集验收](docs/product/product-d5-evaluation.md)：12 新例、3 例事先选定重复，共 36 次运行／98 次真实请求。首轮 S1 9/12、M 6/12，未证明多 Agent 优势；保留全部失败、未知用量及[公开任务证据](evaluation/results/product-d5-public-evidence-20261029.json)。这是同作者小范围新集，不是外部独立基准或线上准确率。工程交付与实际云端 CI 见[最终验证](docs/verification/final-delivery.md)。

后续按用户确认的产品阶段 A—E 推进，优先形成完整任务体验与真实效果证据，再验证按需多 Agent 的收益。阶段 A 产品定义材料：[PRD](docs/product/prd.md)、[需求证据与验证计划](docs/product/validation-plan.md)、[产品决策与迭代](docs/product/decision-iteration-log.md)。材料中的规划与假设不代表已实现或已验证。

D1完成[全栈方案与分阶段交付](docs/product/product-d-delivery-plan.md)、[单/多Agent评测及调优契约](docs/product/product-d-evaluation-design.md)；D2增强单Agent与D3专家实验共享隔离预测和执行约束。D3由协调角色提取目标，舒适/节能角色在LangGraph并行提出只读建议，再协调选择；React呈现实际意见分歧、原选及必要确认，MySQL保存角色记录。[D3工程验证与边界](docs/verification/product-d3-experts.md)区分受控模型、真实MySQL和仿真设备；本阶段真实模型请求0，效果与额外调用是否值得仍待D4/D5评测。无需新增依赖或迁移，启动步骤不变。

## 项目边界与技术栈

本目录是独立Git仓库，只包含HomeMind的源码与文档。密钥、本机配置、测试账号数据库和原始运行文件不入库；评测摘要保留源码/原件哈希，开发与新集、首次与复测分栏。

- 前端：React、TypeScript、Vite、Ant Design、TanStack Query。
- API：Python 3.12、FastAPI、Pydantic Settings、Uvicorn。
- 数据：MySQL 8.4、SQLAlchemy async/asyncmy、Alembic；Cookie 会话、Argon2id 密码摘要、CSRF 和来源检查。
- 仿真：沿用 M2 固定步长热模型/能耗，数据库事务内重建和保存当前家庭的独立状态。
- 任务：动态发现设备、范围/保留/保护约束、统一执行与读回、幂等、同家庭执行占用、持久动作和事件。
- AI：LangGraph 显式模型/只读工具/解析图，LangChain Core 消息与工具；DeepSeek 官方非思考 Chat Completions，关闭自动重试和远程追踪。

后续开发先读 [接续记录](CURRENT_CONTEXT.md) 和 [阶段路线](docs/homemind-development-roadmap.md)。接口和状态语义见 [M3 实施设计](docs/superpowers/specs/2026-10-27-m3-accounts-persistence-design.md)。

前端已按用户批准的 [Figma 浅色控制台设计](https://www.figma.com/design/Bo7Jqfnh4NNRQiMwNvXc2O) 同步：浅色侧栏、紧凑页标题、房间感知/设备控制分组、规则任务、家庭配置、偏好与登录/注册，适配桌面和 360/390px 手机。开关和时钟排版已在 React 修复；Figma 稿因 Starter 工具额度限制尚未回写修正。实际检查、截图及差异见 [设计记录](docs/verification/figma-redesign.md)。

## 环境要求

- Python 3.12，由 uv 按 `backend/.python-version` 创建；本次使用 3.12.14。
- Node.js 24.14.1 / npm 11.11.0；精确依赖在两个锁文件中。
- uv 0.12.5，可通过 `python -m uv` 使用。
- Docker Desktop 的 Linux 引擎已运行；初始化脚本不会自动启动 Docker。启动 Docker 引擎可能按已有重启策略恢复其他项目容器。
- 手动控制和规则不需要模型密钥；自然语言需要本项目 DeepSeek API 配置。不需要购买硬件。

## Windows 启动

按“Docker → 数据库 → API → 网页”的顺序启动。先打开 Docker Desktop，等待 Linux 引擎就绪；前后端使用两个独立 PowerShell 终端，运行期间保持打开。

首次获取源码（已有项目目录则跳过）：

```powershell
git clone https://github.com/yaowcui-ai/homemind.git
Set-Location homemind
```

下文命令从克隆后的 `homemind` 根目录执行，不依赖开发者的本机绝对路径。

### 首次准备或依赖变更后

安装锁文件指定的后端与前端依赖，等每条命令成功结束后再继续：

```powershell
python -m pip install uv==0.12.5
python -m uv sync --project backend --frozen
Set-Location frontend
npm.cmd ci --include=dev --include=optional --bin-links=true
Set-Location ..
```

Vite 属于开发依赖，必须安装；Windows 使用 `npm.cmd`。不要在安装尚未完成时同时启动网页。正常日常启动无需重复安装依赖。

### 每次打开项目

终端一：在项目根目录检查/启动数据库、完成迁移，再启动 API：

```powershell
# 在 homemind 根目录执行
python scripts/setup_mysql.py
Set-Location backend
python -m uv run --frozen python -m homemind
```

数据库准备成功会显示“应用库与独立测试库迁移完成。”；新克隆默认API为`http://127.0.0.1:8100`。开发者本机8100已占用，原有配置使用8110并配套修改前端代理；这份本机配置不上传。端口冲突时选择空闲端口，同时修改`backend/.env`的`HOMEMIND_API_PORT`和`frontend/.env`的`HOMEMIND_API_PROXY_TARGET`，重启两端，不停止其他项目。数据库准备失败时先处理终端报错，再启动API。

终端二：启动网页：

```powershell
# 新终端先进入 homemind 根目录
Set-Location frontend
npm.cmd run dev
```

看到 Vite 输出本地地址后，打开 [网页](http://127.0.0.1:5174/)。首次显示登录/注册；用户名使用 3—32 位字母、数字、下划线，密码 12—128 字符。注册创建一次独立家庭，之后登录不会恢复已删除设备。

B 新增了后端运行依赖，C 新增迁移 `0004_product_c` 保存推进幂等记录。更新代码后先执行上面的依赖准备与数据库步骤，再重启API与网页。已配置密钥的用户无需再次发送密钥；模型配置修改后重启后端。

C2没有新增依赖或迁移，旧任务兼容；更新代码后重启API和网页即可使用新诊断与澄清处理，无需重建数据库。模型拒绝或无效方案会解释下一步，技术字段在“运行记录与调用用量”内展开。

D2新增“温控方案比较（实验）”，无新依赖或迁移；更新后重启API和网页。配置模型且开启仿真调试时，在“任务助手→自然语言任务”选择该入口，可输入：“60分钟后客厅26℃，能耗优先，允许调整窗帘，卧室不动”。先查看最多4个候选的截止温度、首次观测达标时间和范围Wh，再确认执行；执行后在原任务推进到目标时刻并独立核验。模型选了偏好次优方案会如实提示，不自动替换。未开放实验的环境仍保留常规助手。

D3在同一位置增加“多 Agent 协作（实验）”。用上述需求可查看舒适/节能的本轮公开建议与协调原选；意见不同是正常取舍。专家格式、证据或调用失败时停止分析，不执行设备；合法澄清可在原任务补答。阶段状态与意见直接显示，模型、调用和Token在“阶段调用记录”中展开；阶段响应完成不等于设备或目标成功。标准助手仍为默认，简单关灯不必调用专家。实验仅支持单房间温度/期限/仿真能耗，没有自动复杂度路由或实时阶段流。

D4首轮完成[6对真实开发评测与定向调优](docs/product/product-d4-evaluation.md)：实际37/40请求，余3停止。保留评分器勘误及首次失败，审计后整例S1为4/6、M为3/6，未证明多Agent收益；共同排序提示优化后，DD02各复测一次均选择能耗最优候选并实际核验，不能外推总体提升。仍有专家格式/建议和保留项失败待修，当前默认策略不变。无新依赖或迁移，重启后端即可应用提示增量；真实评测入口默认只列案例，旧账本不可删除/改目录重跑。

D4后续完成[有限诊断与两项定向修复](docs/product/product-d4-followup.md)：新批次13/24请求，余11停止。定位Plan保留列表不一致及澄清漏options，在原有严格门禁下分别补阶段提示，各一次复测达到预期；旧专家建议失败本次未复现，不追认根治。角色/字段/类别在现有运行记录内可查，不保存被拒raw或非法ID。更新后重启API，无需新依赖或迁移；下一步是新集验收及[简历交付清单](docs/product/resume-delivery-checklist.md)，不扩无关功能。

预测只在克隆上计算，不推进真实家庭时间；读数未知、目标房间多空调/多窗帘、故障或规模超限会解释缺口。数据仍是简化仿真，不是现实节电或预约控制。新增S1流程用受控模型验证工程闭环，真实DeepSeek新场景效果和多Agent收益须后续另批评测，不能从程序通过数推断准确率。

数据库准备脚本保留匹配的容器和卷，不重建已有数据。网页/API 停止时在各自终端按 `Ctrl+C`。

数据库只暴露 `127.0.0.1:13306`，不使用旧项目的 3306。需要停止本项目数据库时，在项目根目录执行：

```powershell
docker compose --project-name homemind --env-file .local/mysql.env --file deploy/compose.mysql.yaml stop mysql
```

这会保留卷。日常操作不需要删除卷或清空数据库。

### 启动常见问题

**`'vite' 不是内部或外部命令，也不是可运行的程序或批处理文件`**

先确认终端位于本项目 `frontend` 目录。该错误表示 npm 找不到本地 Vite 命令，常见于未安装开发依赖或安装目录不完整。2026-10-27 本机实际排查发现：Vite 包存在，但整个 `node_modules/.bin` 缺失；恢复命令入口后又发现原生组件加载失败与构建依赖错误，最终按锁文件完整重装解决。

先在本项目网页终端按 `Ctrl+C` 停止开发服务，再执行以下命令；每条成功后再执行下一条：

```powershell
# 在 homemind/frontend 目录执行
npm.cmd ci --include=dev --include=optional --bin-links=true
npm.cmd run dev -- --help
npm.cmd run build
npm.cmd run dev
```

`npm ci` 会重建 `node_modules` 并沿用 `package-lock.json` 的版本。无需全局安装 Vite、删除锁文件或修改源码。本次修复已实际验证 Vite 命令加载和 TypeScript/Vite 构建通过。若仍失败，保留完整安装报错，不只截取最后一行。

**`npm warn deprecated whatwg-encoding@3.1.1`**

这是间接依赖的弃用提示，本次安装仍成功完成，不是 Vite 命令缺失的原因。以安装命令是否成功结束及后续构建结果为准。

**`GET /auth/session` 返回 503，页面显示“数据库未就绪”**

这表示账号接口尚不能使用数据库，`/health` 成功不能代替数据库检查。确认 Docker 引擎已运行，在项目根目录重新执行 `python scripts/setup_mysql.py`；成功后在后端终端按 `Ctrl+C`，按上面的终端一命令重启 API，再点击网页“重试连接”。后端命令 `python -m uv run --frozen python -m homemind` 本身是正确的。

若仍返回 503，检查后端终端的报错，以及当前终端是否残留其他目标的 `HOMEMIND_DATABASE_URL` / `HOMEMIND_DATABASE_INSTANCE_ID` 环境变量（它们优先于 `backend/.env`）。不要将密码或完整连接串贴入日志，也不要用 `.env.example` 覆盖已生成的配置。

## 数据资源与配置

Compose 项目 `homemind`、服务 `mysql`、卷 `homemind_mysql_data`。容器/卷带安装 UUID 标签；同名但不匹配时脚本拒绝接管。实际安装身份、镜像摘要和容器 ID 保存在忽略的 `.local/`。

- `homemind_app`：应用库与专属账号，用户日常数据保存在这里。
- `homemind_test`：独立测试库与账号，集成/浏览器/重启检查使用它，避免混入用户家庭。
- `.local/mysql.env`：脚本生成的随机数据库凭据及测试目标；不提交、不打印。
- `backend/.env`：本项目应用库连接与安装标识；脚本不会覆盖已有不同数据库目标。
- `backend/.env.example`：字段说明。**不要用模板覆盖已生成的 `.env`。** 前端不配置数据库或模型密钥。

迁移历史为 `0001_m3` → `0002_m3` → `0003_m4` → `0004_product_c`，当前head `0004_product_c`。首次只对确认空的本项目库允许显式初始化；安装标记不匹配时拒绝迁移。0002明确幂等键二进制排序，0003增加任务模式/Agent记录并保留旧规则任务，0004增加可空推进记录，既有任务不改写。

应用启动核对安装标记和迁移版本，业务请求再次检查。数据库缺失或不可用时返回中文 503，不能退回一个新的临时家庭。开发仅运行单个 API 执行进程。

后端固定读取 `backend/.env`，普通应用配置的操作系统环境变量优先。数据库初始化所用的 Compose 变量则由本项目已验证配置明确覆盖终端遗留值，避免随机凭据与实际容器不一致。

前端默认5174、API代码默认8100，当前本机配置使用8110。端口被占用时不会自动切换或停止其他服务。改变 API 端口需同时修改前端的 `HOMEMIND_API_PROXY_TARGET`；改变网页地址/端口还需把准确 Origin 加入后端 `HOMEMIND_ALLOWED_ORIGINS` JSON 数组。修改后重启相应开发服务。普通浏览器测试可通过 `HOMEMIND_E2E_API_PORT` 指定专用端口，本机使用8110，CI默认8100。

`HOMEMIND_SIMULATION_DEBUG_ENABLED` 默认 false。初始化脚本为当前本地演示显式写 true，显示环境事件、故障、时间推进和 reset；关闭后这些调试写入口不可用，普通家庭配置/读取/控制仍需登录。生产 Cookie 使用 Secure，当前 HTTP 本机开发使用 development 配置，完整发布留到 M10。

## 模型配置与最小演示

只编辑本项目 `backend/.env`，保留已有数据库字段，勿用模板覆盖整文件：

```dotenv
HOMEMIND_MODEL_ENABLED=true
HOMEMIND_MODEL_PROVIDER=deepseek
HOMEMIND_MODEL_NAME=deepseek-flash
HOMEMIND_MODEL_BASE_URL=https://api.deepseek.com
HOMEMIND_MODEL_API_KEY=在本地填写你的密钥
```

本机此前填写的 `API_KEY` 已在本项目文件内适配为专用字段；新安装直接使用上述字段。密钥不写入前端或 Git。模型默认关闭；未配置时自然语言入口说明原因，规则仍可用。“已配置”只表示配置齐全，不能保证余额、网络或本次请求成功。

在任务页选择自然语言，可依次尝试“关闭客厅主灯”“准备一下”（回答实际问题后继续原任务）和“60个仿真分钟后回家，客厅准备到26℃”。全屋批量需要先核对范围和例外再确认。局部任务不会附带执行整套规则；模型无效输出、越权、过期事实或窗户未知制冷会被阻断。

未来目标明确使用仿真分钟。任务内推进到目标时刻会同时核验；没有该时刻读数时，不把后来达标补成按时完成。演示调试关闭时，不可完成的未来温度任务会被阻止，规则离家、当前已达标的睡眠和局部控制仍可用。26℃/60分钟只在固定初始条件下作为演示案例，不保证任意配置可达；既有20分钟未达标反例继续保留。

创建/回答/确认/推进失败或超时后先读取原任务，结果未知时保留原体原键，不自动创建新任务。刷新只读服务器事实，不自动发执行请求。C的网页推进携世界ID、预期当前分钟与独立幂等键，记录同事务保存；同键重放不再推进，不同键携旧时刻也被拒绝。未决重试遇家庭busy会保留原键。旧`POST /tasks/{id}/advance {}`无key兼容接口没有此新保证；图自动恢复仍未实现。

可选真实接入检查：`backend/.venv/Scripts/python.exe scripts/check_model.py --real`；会使用合成数据，最多发两次实际模型请求，不操作家庭设备。不带 `--real` 时不调用模型。默认自动测试禁止外部 HTTP；完整效果评测与此基础检查分开，实际证据见 [B 验证记录](docs/verification/product-b-single-agent.md)。

模型未配置：核对专用字段后重启 API；模型服务不可用：检查官方控制台、余额及网络，不把原始供应商错误或密钥贴到日志；格式/工具/预算错误：任务保留失败分类，不执行未校验方案。规则和设备控制可继续使用。

## 一次操作如何流转

`注册/登录 → HttpOnly Cookie + 内存 CSRF → 当前家庭事务 → 规则/能力检查 → 私有仿真引擎 → 独立读回 → 保存状态、任务、动作和事件`

自然语言路径先短事务保存需求/快照，事务外由LangGraph规划，再短事务重读版本、全量校验、必要确认与统一执行。模型调用期间不持家庭数据库锁；事实变化直接阻断旧方案，自动重规划尚未接入。

前端使用同源 `/api` 代理；认证上下文决定 home_id，客户端不能指定其他家庭扩大权限。跨家庭房间、实体、任务及保留/保护引用返回 404；退出会撤销当前会话。切换账号清理查询和待提交状态，迟到响应按会话代次丢弃。标签页通过不含凭据的通知同步身份，恢复焦点也重新核对；同账号核对保留表单和未确认提交的幂等键。

```json
{"status":"ok","service":"homemind-api","version":"0.4.0","stage":"M4"}
```

`GET /health` 只说明 API 进程存活；数据库状态通过实际认证/业务请求确认。其他服务返回 HTTP 200 不会被视为 HomeMind 在线。

## 演示步骤

1. 注册账号 A，查看客厅/卧室各六实体。打开一盏灯并改名一个房间；退出后注册 B，查看独立 ID 和初始状态；重新登录 A，原配置仍在。
2. 在家庭配置中增加书房和阅读灯、迁移或归档实体。移除房间前先清空实体；主温度/占用移除后显示未知，不能把缺失值当作无人/关窗/0℃。
3. 在偏好中保存回家/睡眠温度、风速和准备时间。新任务使用当前默认值，过去任务保留原偏好和快照。
4. 进入“任务助手”，在规则入口选择模板、房间、保留设备和保护房间。回家：开灯、合帘、制冷；睡眠：关灯、合帘、制冷；离家：关闭所选灯/空调、合帘。保留设备和保护房间不产生动作，目标按当前配置发现。切换自然语言可使用上方示例，遇歧义在原任务回答。
5. 验证一个可达的未来目标：默认客厅28℃，回家目标设28℃、准备时间1仿真分钟。提交后为等待核验；在原任务点击“推进至目标时刻…并核验”。核验不重发设备动作；也可仅在已到目标分钟时点“核验目标”。
6. 试开窗或把窗户读数设为未知，再运行需要制冷的模板，查看未执行原因和部分完成；有人信号不代表有人睡觉，窗户传感器没有关窗能力。
7. 注入响应丢失或延迟，观察响应与实际读回分别记录；对未完成/未知条件可显式再次核验。请求结果不明时先读列表，同内容重试保留幂等键，不能把网络错误当作“服务端一定未执行”。
8. 停止并重启 API，重新读取原家庭、偏好和历史；已归档设备不因登录、初始化或运行 reset 复活。

## 时间、结果与保存边界

数据库保存账号、会话、房间、实体配置和环境、偏好版本、任务、动作和事件。读取不推进仿真时间。reset 保留当前用户清单/配置/ID，换 world_id 并清空本次运行状态、能耗、故障和延迟；历史保留原环境和当时名称。

任务有“动作已核验”与“环境目标已达到”两个层次。回家目标需要目标时刻的读数：系统不后台采样，须在该仿真分钟显式核验。第一次到更晚时刻才核验，没有当时证据会保留未知/部分，不能用晚达到的温度宣称按时完成。首次目标时刻证据保存后不因同分钟修改读数而改写；已成功任务再核验也保留完成历史。睡眠没有回家 deadline，可在降温后继续核验。

同家庭最多一个正在规划/执行的规则或Agent任务，其他提交说明忙碌；等待输入/确认/核验释放占用。任务幂等键按家庭隔离且区分大小写，同键同内容返回原任务，异内容409。当前设备执行是纯仿真数据库事务，没有外部设备原子提交、分布式队列或exactly-once承诺。

模型 `m2-decimal-minute-v1` 仍采用室外 32℃、每分钟步长、内部 Decimal 温度 0.001℃、公开读数 0.1℃。窗户换热、占用、窗帘、空调和灯功率都是透明假设；能耗为 Wh，不能外推真实舒适度或节电收益。离线/未知不自动关闭内部物理设备。全部公式见 [M2 设计](docs/superpowers/specs/2026-10-26-m2-simulation-design.md) 和 [仿真实现约定](backend/src/homemind/simulation/README.md)。

## 验证

后端目录运行快速单元/API 测试（显式注入 SQLite，不能据此声称 MySQL 通过）：

```powershell
python -m uv run --frozen pytest -q
python -m uv run --frozen ruff check .
python -m uv run --frozen ruff format --check .
python -m uv run --frozen python scripts/check_compatibility.py
python -m uv pip check --python .venv/Scripts/python.exe
```

没有测试库变量时，五个 MySQL 用例会明确 skip。独立 MySQL 和真实 API 进程重启在项目根目录检查：

```powershell
python scripts/setup_mysql.py
python scripts/verify_m3.py
python -m uv run --project backend --frozen pytest scripts/tests -q
```

重启检查使用独立测试库、临时 18100 API，只停止通过随机 nonce/PID 核实的本轮进程。它核对会话、配置/环境、归档、偏好、历史和重放结果；不会重建用户应用库。测试库会保留受控测试账号与记录供检查。

前端目录运行：

```powershell
npm.cmd test -- --run
npm.cmd run lint
npm.cmd run build
npx.cmd playwright install chromium
$env:HOMEMIND_E2E_API_PORT = '8110'
npm.cmd run test:e2e
npm.cmd run test:e2e:agent
```

普通浏览器验收自行启动/关闭临时 MySQL API 与5174网页，不复用已有服务；本机指定8110需空闲。Agent浏览器验收另用18110/5176、全新显式SQLite及受控模型，只验证界面与程序流程，不发真实模型请求，也不冒充MySQL或模型效果。测试进程仅为自身补充本机 NO_PROXY，保留已有设置。`npm.cmd run preview` 预览构建文件仍需 API，不能当作生产部署。

原始失败/通过日志、重启证明和截图位于忽略的 `output/`。阶段证据见 [M3 验证记录](docs/verification/m3-accounts-persistence.md)，历史记录见 [M2](docs/verification/m2-simulation.md)、[M1](docs/verification/m1-foundation.md)。GitHub Actions 已配置相同迁移和测试，只有实际远端运行后才可声称远端 CI 通过。

## 当前交付与后续边界

C两轮、D3全栈闭环、D4开发调优、D5冻结验收、独立进程重启验证、公开源码与单项目AI全栈简历已交付。D5余22次请求停止，旧余额不转用。Figma新增核心状态和可点击连线因Starter工具额度仍未完成，见[本轮核对记录](docs/verification/figma-final.md)；React核心流程可运行。求职材料只保留AI全栈Markdown，不生成AI产品简历/面试问答。SSE、后台时钟、用户取消/自动重规划、图恢复、真实硬件和公网应用部署仍未做，不为简历扩展这些功能。

在根目录运行 `backend/.venv/Scripts/python.exe scripts/product_eval.py` 只显示案例数，不读取模型配置或联网。C首轮授权的40次真实请求已用满；`--real`、`--resume`或`--retest C04`不会重置同一账本。不要删除账本、换目录或把此开发批次当未见保留集；后续真实批次需先确定新样本和预算。中断遗留的`batch.lock`会保守阻断，先核实无存活评测进程再处理锁，保留已有账本和案例原件。

C2的默认只读命令为`backend/.venv/Scripts/python.exe scripts/product_eval_c2.py`。该轮新授权32请求，实际30，余2未用，已停止；固定独立账本、跨阶段共享上限，旧40账本未动。后续模型批次另定范围/预算，不自动使用余额。C06的“20分钟必定未达标”假设已勘误：低风26.8℃、自动风26.0℃；要复现低风反例须明确输入风速，原件和原评分不覆盖。
