# HomeMind

智能家居多 Agent 协同调度网页系统。当前阶段为 **M1 工程基础**：已建立 React 网页、FastAPI 服务、真实健康检查和独立依赖环境。家庭模板只作设计预览，设备仿真从 M2 开始。

## 项目位置与开发边界

本目录是独立 Git 仓库，开发分支为 `codex/m1-foundation`。父工作区通过其本地 `.git/info/exclude` 忽略本目录；不要在父仓库中强制添加本项目，也不要把旧项目文件复制进提交。

- 前端：React、TypeScript、Vite、Ant Design、TanStack Query。
- 后端：Python 3.12、FastAPI、Pydantic Settings、Uvicorn。
- 编排：LangGraph 为主、LangChain 为辅，本阶段只验证依赖和无模型的内存状态图。
- 后续：独立 MySQL、可配置仿真家庭、专业 Agent、SSE、对照评测和部署。

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
{"status":"ok","service":"homemind-api","version":"0.1.0","stage":"M1"}
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

测试截图和运行输出位于被 Git 忽略的 `output/`。实际结果记录在 [M1 验证记录](docs/verification/m1-foundation.md)。

## 下一阶段

M2 实现可配置家庭与十二实体仿真。当前没有设备控制、注册登录、业务数据库、真实模型调用或物理设备接入；不要将模板图当作实时户型或设备数据。
