# HomeMind M1 工程基础 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking. Final independent review follows requesting-code-review.

**Goal:** 建立独立 React 网页与 FastAPI 服务，真实打通健康检查，锁定依赖并交付 Windows 启动方式，停在 M2 之前。

**Architecture:** 一个独立仓库包含 `backend/` 和 `frontend/`。后端只提供无外部依赖的 `/health` 活性接口；前端通过 Vite `/api` 代理访问它。UI 明确当前为 M1，不伪造设备、对话或 Agent 执行数据。

**Tech Stack:** Python 3.12、uv、FastAPI、Pydantic Settings、Uvicorn；Node.js 24、npm、React、TypeScript、Vite、Ant Design、TanStack Query；pytest、HTTPX、Vitest、Playwright、Ruff、ESLint。

---

## 文件结构与职责

- `AGENTS.md`、`CURRENT_CONTEXT.md`：阶段边界与接续事实。
- `backend/pyproject.toml`、`uv.lock`、`.python-version`、`.env.example`：后端运行要求和精确依赖。
- `backend/src/homemind/app.py`：FastAPI 工厂和健康响应。
- `backend/src/homemind/config.py`、`__main__.py`：固定项目配置位置、校验与开发启动入口。
- `backend/tests/test_health.py`、`test_config.py`：活性语义与配置边界。
- `backend/scripts/check_compatibility.py`：只做版本/import/内存状态图检查，不连接 MySQL 或模型。
- `frontend/package.json`、`package-lock.json`、Vite/TypeScript/ESLint/Vitest 配置：前端工具链。
- `frontend/src/api/health.ts`：请求、超时和响应契约检查。
- `frontend/src/App.tsx`、`App.module.css`、`main.tsx`、`index.css`：中文响应式入口和真实连接状态。
- `frontend/src/api/health.test.ts`、`App.test.tsx`：接口边界、连接失败与恢复。
- `frontend/e2e/foundation.spec.ts`、`playwright.config.ts`：真实后端连通、离线恢复和手机宽度验证。
- `.github/workflows/checks.yml`：独立依赖安装、检查和构建。
- `README.md`、`docs/verification/m1-foundation.md`：复现步骤、实际证据与范围。

## Task 1：隔离与配置

- [x] 在 `homemind/` 初始化独立仓库及 `codex/m1-foundation` 分支，父仓库仅通过本地 `.git/info/exclude` 忽略它，不修改父项目源码或已有 `.gitignore`。
- [x] 复制已批准设计文档到项目内相同相对目录，保留六个本地文档链接。
- [x] 固定 Python 3.12；前端 Node 24。选取兼容版本，使用 `uv lock` 和 npm 生成锁文件；不直接采用已知不兼容的 TypeScript/Node 依赖组合。
- [x] 后端配置使用项目 `backend/.env`，环境变量优先。允许缺少模型和数据库配置，端口范围 1—65535，环境值限定 development/test/production。
- [x] 配置测试至少覆盖默认无密钥启动、非法端口、非法环境和独立于当前工作目录的配置路径。

核心配置约束：

```python
environment: Literal["development", "test", "production"] = "development"
api_host: str = "127.0.0.1"
api_port: int = Field(default=8100, ge=1, le=65535)
```

## Task 2：后端健康接口

- [x] 先建立无健康路由的最小 FastAPI 工厂与行为测试，运行下列断言，观察 404 与预期 200 的失败。

```python
response = await client.get("/health")
assert response.status_code == 200
assert response.json() == {
    "status": "ok", "service": "homemind-api", "version": "0.1.0", "stage": "M1"
}
```

- [x] 添加 `/health` 响应模型与路由，不导入模型或创建数据库连接。
- [x] 验证健康接口、未知设备路由 404、配置验证和 OpenAPI；`/health` 只表示 API 存活，不表示数据库/Agent 已就绪。
- [x] 运行 `python -m uv run --frozen pytest -q` 与 `python -m uv run --frozen ruff check .`。

## Task 3：前端请求契约

- [x] 先写健康客户端测试，覆盖正确服务、HTTP 失败、错误服务或无效结构、超时，并观察功能未实现时的失败。
- [x] 请求固定相对路径 `/api/health`；5 秒超时，错误不展示上游正文，不自动重试。
- [x] 对 `status`、`service`、`version`、`stage` 进行运行时类型检查，不能将其他服务的 200 当作 HomeMind 在线。
- [x] Vite 使用 127.0.0.1:5174 且 strictPort，`/api` 代理到 127.0.0.1:8100 并移除 `/api` 前缀；可通过前端自己的非 VITE 前缀代理配置修改目标，不暴露后端密钥。

## Task 4：中文入口与状态交互

- [x] 先写页面测试：正在检查、后端在线、连接失败、点击重新检查后恢复；不把静态模板数据当作设备实时读数。
- [x] 实现有品牌标识、阶段说明、真实后端连接卡和可用重试按钮的响应式页面。房间和实体只作为默认设计概览，不实现 M2 操作。
- [x] 使用 TanStack Query 管理健康状态，关闭自动重试和窗口聚焦重查，保留显式刷新；按钮加载期间禁用重复提交。
- [x] 运行 `npm.cmd test -- --run`、`npm.cmd run lint`、`npm.cmd run build`。

## Task 5：依赖兼容与浏览器验收

- [x] 在锁定环境导入 LangChain、LangGraph 及 `AsyncMySaver`，构建并运行一个无模型调用的最小内存状态图，检查 Python 包依赖。
- [x] 报告明确区分依赖解析/import/内存状态图验证与尚未运行的 MySQL 检查点恢复。
- [x] Playwright 启动临时 API 和 Vite，检查真实健康响应、连接失败与再次连接、桌面和 390px 手机视口无横向溢出。
- [x] 保存桌面和手机截图，目视检查布局。临时验证进程结束后关闭，只清理本次创建的进程。

## Task 6：交付与范围核对

- [x] 写清 Windows 两终端启动方式、可选配置、验证命令和 Ctrl+C 停止方法。
- [x] 加入 GitHub Actions 的 Python 检查与前端检查/构建；不配置付费模型或发布操作。
- [x] 依据 requesting-code-review 进行一次独立代码审阅，解决影响当前阶段的实际问题。
- [x] 更新接续记录和 M1 勾选，记录真实版本、验证计数、截图、已知边界和 M2 入口。
- [x] 运行必要最终检查并提交到当前独立开发分支；保留本地分支，不对外发布，不进入 M2。

## 验收命令

后端工作目录为 `backend/`：

```powershell
python -m uv sync --frozen
python -m uv run --frozen pytest -q
python -m uv run --frozen ruff check .
python -m uv run --frozen python scripts/check_compatibility.py
python -m uv pip check --python .venv/Scripts/python.exe
```

前端工作目录为 `frontend/`：

```powershell
npm.cmd ci
npm.cmd test -- --run
npm.cmd run lint
npm.cmd run build
npm.cmd run test:e2e
```

预期：检查通过；浏览器显示真实 HomeMind API 在线，关闭后端能看到连接失败，恢复后端并重新检查可恢复。当前阶段不含设备仿真、注册登录、业务数据库或真实模型调用。
