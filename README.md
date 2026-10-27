# HomeMind

智能家居多 Agent 协同调度网页系统，当前实现 **M3：账号隔离、MySQL 持久化与规则基线**。注册后获得自己的两房十二实体模板，可以修改配置、控制设备、保存偏好，并执行回家、睡眠、离家三个明确规则场景。

LangGraph 为主、LangChain 为辅的 Agent 编排从 M4 开始；现在的任务执行使用固定规则，没有模型调用或真实硬件。

## 项目边界与技术栈

本目录是独立 Git 仓库，当前分支 `codex/m3-accounts-persistence`。父工作区通过本地 `.git/info/exclude` 忽略本目录，旧项目不纳入本仓库。

- 前端：React、TypeScript、Vite、Ant Design、TanStack Query。
- API：Python 3.12、FastAPI、Pydantic Settings、Uvicorn。
- 数据：MySQL 8.4、SQLAlchemy async/asyncmy、Alembic；Cookie 会话、Argon2id 密码摘要、CSRF 和来源检查。
- 仿真：沿用 M2 固定步长热模型/能耗，数据库事务内重建和保存当前家庭的独立状态。
- 任务：动态发现设备、范围/保留/保护约束、统一执行与读回、幂等、同家庭执行占用、持久动作和事件。

后续开发先读 [接续记录](CURRENT_CONTEXT.md) 和 [阶段路线](docs/homemind-development-roadmap.md)。接口和状态语义见 [M3 实施设计](docs/superpowers/specs/2026-10-27-m3-accounts-persistence-design.md)。

## 环境要求

- Python 3.12，由 uv 按 `backend/.python-version` 创建；本次使用 3.12.14。
- Node.js 24.14.1 / npm 11.11.0；精确依赖在两个锁文件中。
- uv 0.12.5，可通过 `python -m uv` 使用。
- Docker Desktop 的 Linux 引擎已运行；初始化脚本不会自动启动 Docker。启动 Docker 引擎可能按已有重启策略恢复其他项目容器。
- 当前不需要模型密钥或购买硬件。

## Windows 启动

按“Docker → 数据库 → API → 网页”的顺序启动。先打开 Docker Desktop，等待 Linux 引擎就绪；前后端使用两个独立 PowerShell 终端，运行期间保持打开。

### 首次准备或依赖变更后

安装锁文件指定的后端与前端依赖，等每条命令成功结束后再继续：

```powershell
Set-Location 'C:\Users\86139\Documents\ChatGPT\实习项目\homemind'
python -m uv sync --project backend --frozen
Set-Location frontend
npm.cmd ci --include=dev --include=optional --bin-links=true
```

Vite 属于开发依赖，必须安装；Windows 使用 `npm.cmd`。不要在安装尚未完成时同时启动网页。正常日常启动无需重复安装依赖。

### 每次打开项目

终端一：在项目根目录检查/启动数据库、完成迁移，再启动 API：

```powershell
Set-Location 'C:\Users\86139\Documents\ChatGPT\实习项目\homemind'
python scripts/setup_mysql.py
Set-Location backend
python -m uv run --frozen python -m homemind
```

数据库准备成功会显示“应用库与独立测试库迁移完成。”；随后 API 显示 `Uvicorn running on http://127.0.0.1:8100`。如果数据库准备失败，先处理终端报错，再启动 API。

终端二：启动网页：

```powershell
Set-Location 'C:\Users\86139\Documents\ChatGPT\实习项目\homemind\frontend'
npm.cmd run dev
```

看到 Vite 输出本地地址后，打开 [网页](http://127.0.0.1:5174/)。首次显示登录/注册；用户名使用 3—32 位字母、数字、下划线，密码 12—128 字符。注册创建一次独立家庭，之后登录不会恢复已删除设备。

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
Set-Location 'C:\Users\86139\Documents\ChatGPT\实习项目\homemind\frontend'
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

迁移历史为 `0001_m3` → `0002_m3`，当前 head `0002_m3`。首次只对确认空的本项目库允许显式初始化；非本项目表或安装标记不匹配时拒绝迁移。0002 将任务幂等键列明确设为二进制排序规则，避免数据库默认排序规则忽略键的大小写。

应用启动核对安装标记和迁移版本，业务请求再次检查。数据库缺失或不可用时返回中文 503，不能退回一个新的临时家庭。开发仅运行单个 API 执行进程。

后端固定读取 `backend/.env`，普通应用配置的操作系统环境变量优先。数据库初始化所用的 Compose 变量则由本项目已验证配置明确覆盖终端遗留值，避免随机凭据与实际容器不一致。

前端默认 5174、API 8100。端口被占用时不会自动切换或停止其他服务。改变 API 端口需同时修改前端的 `HOMEMIND_API_PROXY_TARGET`；改变网页地址/端口还需把准确 Origin 加入后端 `HOMEMIND_ALLOWED_ORIGINS` JSON 数组。修改后重启相应开发服务。

`HOMEMIND_SIMULATION_DEBUG_ENABLED` 默认 false。初始化脚本为当前本地演示显式写 true，显示环境事件、故障、时间推进和 reset；关闭后这些调试写入口不可用，普通家庭配置/读取/控制仍需登录。生产 Cookie 使用 Secure，当前 HTTP 本机开发使用 development 配置，完整发布留到 M10。

## 一次操作如何流转

`注册/登录 → HttpOnly Cookie + 内存 CSRF → 当前家庭事务 → 规则/能力检查 → 私有仿真引擎 → 独立读回 → 保存状态、任务、动作和事件`

前端使用同源 `/api` 代理；认证上下文决定 home_id，客户端不能指定其他家庭扩大权限。跨家庭房间、实体、任务及保留/保护引用返回 404；退出会撤销当前会话。切换账号清理查询和待提交状态，迟到响应按会话代次丢弃。标签页通过不含凭据的通知同步身份，恢复焦点也重新核对；同账号核对保留表单和未确认提交的幂等键。

```json
{"status":"ok","service":"homemind-api","version":"0.3.0","stage":"M3"}
```

`GET /health` 只说明 API 进程存活；数据库状态通过实际认证/业务请求确认。其他服务返回 HTTP 200 不会被视为 HomeMind 在线。

## 演示步骤

1. 注册账号 A，查看客厅/卧室各六实体。打开一盏灯并改名一个房间；退出后注册 B，查看独立 ID 和初始状态；重新登录 A，原配置仍在。
2. 在家庭配置中增加书房和阅读灯、迁移或归档实体。移除房间前先清空实体；主温度/占用移除后显示未知，不能把缺失值当作无人/关窗/0℃。
3. 在偏好中保存回家/睡眠温度、风速和准备时间。新任务使用当前默认值，过去任务保留原偏好和快照。
4. 在规则任务选择模板、房间、保留设备和保护房间。回家：开灯、合帘、制冷；睡眠：关灯、合帘、制冷；离家：关闭所选灯/空调、合帘。所有动作明确展示，保留设备和保护房间不产生动作；作用目标按当前配置发现。
5. 验证一个可达的未来目标：默认客厅 28℃，回家目标设 28℃、准备时间 1 分钟。提交后为等待核验；到概览推进 1 分钟，再回任务选择原记录、点击“核验目标”。核验不会再发设备动作。
6. 试开窗或把窗户读数设为未知，再运行需要制冷的模板，查看未执行原因和部分完成；有人信号不代表有人睡觉，窗户传感器没有关窗能力。
7. 注入响应丢失或延迟，观察响应与实际读回分别记录；对未完成/未知条件可显式再次核验。请求结果不明时先读列表，同内容重试保留幂等键，不能把网络错误当作“服务端一定未执行”。
8. 停止并重启 API，重新读取原家庭、偏好和历史；已归档设备不因登录、初始化或运行 reset 复活。

## 时间、结果与保存边界

数据库保存账号、会话、房间、实体配置和环境、偏好版本、任务、动作和事件。读取不推进仿真时间。reset 保留当前用户清单/配置/ID，换 world_id 并清空本次运行状态、能耗、故障和延迟；历史保留原环境和当时名称。

任务有“动作已核验”与“环境目标已达到”两个层次。回家目标需要目标时刻的读数：M3 不后台采样，须在该仿真分钟显式核验。第一次到更晚时刻才核验，没有当时证据会保留未知/部分，不能用晚达到的温度宣称按时完成。首次目标时刻证据保存后不因同分钟修改读数而改写；已成功任务再核验也保留完成历史。睡眠没有回家 deadline，可在降温后继续核验。

同家庭最多一个正在执行的规则任务，其他提交说明忙碌；等待核验释放占用。任务幂等键按家庭隔离且区分大小写，同键同内容返回原任务，异内容 409。当前规则执行是纯仿真数据库事务，没有外部设备原子提交、分布式队列或 exactly-once 承诺。

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

没有测试库变量时，三个 MySQL 用例会明确 skip。独立 MySQL 和真实 API 进程重启在项目根目录检查：

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
npm.cmd run test:e2e
```

浏览器验收自行启动/关闭临时 API 和 Vite，不复用已有服务；后端明确接独立测试库，两个默认端口需空闲。测试进程仅为自身补充本机 NO_PROXY，保留已有设置。`npm.cmd run preview` 预览构建文件仍需 API，不能当作生产部署。

原始失败/通过日志、重启证明和截图位于忽略的 `output/`。阶段证据见 [M3 验证记录](docs/verification/m3-accounts-persistence.md)，历史记录见 [M2](docs/verification/m2-simulation.md)、[M1](docs/verification/m1-foundation.md)。GitHub Actions 已配置相同迁移和测试，只有实际远端运行后才可声称远端 CI 通过。

## 下一阶段

M4 接入 LangGraph 单 Agent 自然语言闭环，继续共用当前约束与执行边界。本阶段没有真实模型、Agent、SSE、后台时钟、重规划/取消或检查点恢复，也没有真实设备和公网部署；按阶段交付，等待用户启动下一步。
