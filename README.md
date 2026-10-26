# HomeMind

智能家居多 Agent 协同调度网页系统。当前完成 **M2 可配置家庭与设备仿真**：React 控制台可以管理房间和实体、控制灯光/空调/窗帘、注入传感事件、推进确定性仿真并读取故障结果。默认客厅和卧室各六个实体。

## 项目位置与开发边界

本目录是独立 Git 仓库，当前开发分支为 `codex/m2-simulation`。父工作区通过其本地 `.git/info/exclude` 忽略本目录；不要在父仓库中强制添加本项目，也不要把旧项目文件复制进提交。

- 前端：React、TypeScript、Vite、Ant Design、TanStack Query。
- 后端：Python 3.12、FastAPI、Pydantic Settings、Uvicorn。
- 编排：LangGraph 为主、LangChain 为辅，本阶段只验证依赖和无模型的内存状态图。
- 仿真：受锁保护的进程内家庭、独立快照、固定步长十进制热模型和能耗、状态与配置版本。
- 后续：独立 MySQL、账号隔离、专业 Agent、SSE、对照评测和部署。

开始工作请读 [CURRENT_CONTEXT.md](CURRENT_CONTEXT.md) 和 [开发路线](docs/homemind-development-roadmap.md)。

## 环境要求

- Python 3.12，由 uv 按 `backend/.python-version` 创建独立环境。本次使用 3.12.14。
- 本次验证使用 Node.js 24.14.1、npm 11.11.0；Node 要求见 `frontend/package.json`。
- uv 0.12.5。当前 Windows 已可通过 `python -m uv` 使用。
- 首次依赖安装需要网络。本阶段不需要 Docker、MySQL、模型密钥或购买硬件。

## Windows 启动：两个 PowerShell 终端

终端一启动 API：

```powershell
Set-Location 'C:\Users\86139\Documents\ChatGPT\实习项目\homemind\backend'
python -m uv sync --frozen
python -m uv run --frozen python -m homemind
```

终端二启动网页：

```powershell
Set-Location 'C:\Users\86139\Documents\ChatGPT\实习项目\homemind\frontend'
npm.cmd ci
npm.cmd run dev
```

依赖已安装后，日常只需分别执行最后一条启动命令。

打开 [网页](http://127.0.0.1:5174/)，连接卡应显示“后端已连接”；[API 文档](http://127.0.0.1:8100/docs) 可检查接口。停止时在对应终端按 `Ctrl+C`，不停止其他服务。

如端口被占用，启动会报错而不自动切换端口。不要停止其他项目。可更换本项目端口，并同步修改前端代理目标；例如将后端改到 8101 时设置 `HOMEMIND_API_PORT=8101`，前端的 `HOMEMIND_API_PROXY_TARGET` 改为 `http://127.0.0.1:8101`。前端端口可使用 `npm.cmd run dev -- --port 5175`。

## 可选配置

无需配置即可使用默认值。需要修改时，将各目录的 `.env.example` 复制为该目录的 `.env`，仅修改必要字段。

- 后端固定读取 `backend/.env`，操作系统环境变量优先，不随终端工作目录搜索旧项目配置。
- 前端读取 `frontend/.env` 中的代理目标；该配置供 Vite 服务器使用，没有 `VITE_` 前缀。
- 不在前端配置中放模型、数据库或其他服务密钥。本阶段没有这些必填项。
- 修改配置后重启对应开发服务。

## 一次请求的流转

`浏览器 → /api/health → Vite 开发代理 → FastAPI /health → 响应契约校验 → 页面状态`

`GET /health` 返回：

```json
{"status":"ok","service":"homemind-api","version":"0.2.0","stage":"M2"}
```

这表示 API 存活，不表示设备、数据库或模型已连接。前端会校验服务身份和返回结构，5 秒超时后显示提示；只有用户显式重新检查才会重试。其他服务返回的 HTTP 200 不会被视为 HomeMind 在线。

## 验证

在后端目录运行：

```powershell
python -m uv run --frozen pytest -q
python -m uv run --frozen ruff check .
python -m uv run --frozen ruff format --check .
python -m uv run --frozen python scripts/check_compatibility.py
python -m uv pip check --python .venv/Scripts/python.exe
```

在前端目录运行：

```powershell
npm.cmd test -- --run
npm.cmd run lint
npm.cmd run build
npx.cmd playwright install chromium
npm.cmd run test:e2e
```

浏览器测试会自行启动并关闭临时 API 与 Vite，两个默认端口需空闲。它不会复用或停止用户已经运行的服务。Chromium 只需在首次缺少浏览器时安装；可通过 `HOMEMIND_BROWSER_CHANNEL` 显式选择已安装的兼容浏览器。

浏览器测试进程会在自身的代理绕过列表中加入本机地址，保留已有规则，避免系统代理转发本地就绪检查；它不修改系统设置或当前 PowerShell 的代理配置。

`npm.cmd run preview` 可预览已构建文件；当前 Vite 配置下它会沿用 `/api` 代理，仍需单独运行后端。它用于本机预览，不能作为生产部署验收。本阶段日常使用 `npm.cmd run dev`，生产部署和统一入口安排在 M10。

测试截图和原始运行输出位于被 Git 忽略的 `output/`。实际结果见 [M2 验证记录](docs/verification/m2-simulation.md)，历史基础检查见 [M1 验证记录](docs/verification/m1-foundation.md)。

## 五分钟演示

1. 打开家庭概览，查看默认两房十二实体。给客厅主灯设置亮度并点击“应用设置”，读回卡片的实际状态。
2. 将客厅空调模式设为制冷、目标 24℃，应用后推进 20 分钟，观察室温和累计 Wh。时间只在点击推进时流动。
3. 点击有人/窗户卡片的“模拟有人”“模拟开窗”。这些是环境事件，传感器没有设备控制权限。
4. 进入家庭配置，新增书房与阅读灯，修改名称或所属房间；移除实体会归档。房间必须先清空才能移除。房间设置可显式选择主温度/占用传感器，移除主传感器后显示未知。
5. 在设备故障设置中选择离线、执行前失败、响应丢失、指令无效果或延迟。响应丢失返回未知，读回可观察实际状态；延迟通过推进仿真时间生效。
6. “重置运行”会要求确认：保留用户房间、实体、ID、启用状态、主传感器与保存配置，清空本次运行时间、能耗、故障和待执行动作。已归档实体不会复活。

## 保存与模型边界

**目前是未鉴权的本机单家庭演示，数据只保存在当前后端进程。** 重启后恢复默认模板；不要用多个 Uvicorn worker 运行内存演示。`production` 环境不挂载 `/simulation` 路由。注册、家庭归属隔离和数据库保存安排在 M3。

- 模型版本 `m2-decimal-minute-v1`，每分钟更新一次，室外恒定 32℃；室温内部保留 0.001℃，公开显示 0.1℃。单次可推进 1—1440 分钟，读取不会推进时间。
- 关窗/开窗换热系数 0.02/0.10，加上窗帘开度与占用热增益；制冷 auto/low 最多 0.22/0.15℃每分钟，功率为 850/550W，达到目标后按 12/8W 待机。
- 灯功率为 `2 + round(10 × 亮度/100)` W；窗帘实际改变位置耗能 0.05Wh。总能耗包含本次运行中已归档设备先前耗能，重置时归零。它们都是功能验证假设，不能代表真实耗电或节电收益。
- 物理环境和公开观察分开：离线或未知不会自动关掉运行中的设备；公开读数保留 null，不能当作无人、关窗或 0℃。主温度/占用严格读所选实体，没有绑定也显示未知。
- 故障持续到清除；每个实体最多一个延迟动作，在到期分钟开始时应用。配置修改、停用、迁移、归档、故障更改及 reset 会取消相关待执行动作。reset 换 world_id，可拒绝旧环境的控制请求。

完整参数和 API 请求契约见 [M2 实施设计](docs/superpowers/specs/2026-10-26-m2-simulation-design.md)，计算顺序和观察规则见 [仿真实现约定](backend/src/homemind/simulation/README.md)。接口流转为 `浏览器 /api/simulation → Vite → FastAPI /simulation → 仿真服务 → 独立读回快照`；业务错误包含中文说明，不展示堆栈。

## 下一阶段

M3 接入账号隔离、业务持久化与规则基线。当前没有注册登录、业务数据库、Agent 编排、真实模型调用或物理设备接入；按阶段完成后停止，由用户启动下一步。
