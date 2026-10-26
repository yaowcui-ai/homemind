# HomeMind M2 Simulation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付可配置家庭和十二实体的确定性内存仿真，连接 React 控制台，完成实际操作与故障验收，停在 M3 之前。

**Architecture:** 后端用受锁保护的仿真服务和薄 FastAPI 路由，快照与操作接口遵循 [实施设计](../specs/2026-10-26-m2-simulation-design.md)。前端只用这些接口，通过 TanStack Query 同步；控制与模拟事件分离。

**Tech Stack:** 已锁定的 Python/FastAPI/Pydantic、React/TypeScript/Ant Design/TanStack Query、pytest/Vitest/Playwright，无新增基础设施。

## Task 1：仿真服务与 API

**Files:** `backend/src/homemind/simulation/{models,defaults,physics,service,routes}.py`；修改 `app.py`、版本与健康测试；新增 `backend/tests/test_simulation*.py`。

- [x] 建立默认快照和控制行为测试，观察缺少仿真接口/行为时的失败，保留检查记录。
- [x] 实现房间/实体类型、独立 ID、默认模板、严格参数、主传感器绑定与归档。
- [x] 实现固定步长热模型、能耗、快照数据质量、故障和延迟动作；错误输入不产生半更新。
- [x] 实现规定接口，所有同步写入串行；production 不挂载调试仿真路由。
- [x] 更新 API stage=M2、version=0.2.0 和锁文件，不创建数据库或模型会话。
- [x] 运行后端测试、Ruff、格式检查，交由独立规范和质量审阅。

核心行为测试示例：

```python
before = client.get('/simulation').json()
assert len(before['rooms']) == 2 and len(before['entities']) == 12
light = next(item for item in before['entities'] if item['type'] == 'light')
result = client.post(f"/simulation/controls/{light['id']}", json={
    'action': 'set_light', 'parameters': {'power': True, 'brightness_pct': 60},
    'expected_world_id': before['world_id'],
})
assert result.json()['outcome'] == 'verified'
after = client.get('/simulation').json()
assert next(e for e in after['entities'] if e['id'] == light['id'])['state']['power'] is True
```

## Task 2：前端契约与控制界面

**Files:** `frontend/src/api/simulation.ts`、相关测试；`frontend/src/components/simulation/` 下的卡片、配置和环境面板；修改 `App.tsx`、样式和页面测试。

- [x] 先写请求错误/契约测试与关键交互测试，观察失败。
- [x] 按实施设计定义 TypeScript 类型及 API 客户端，变更后刷新快照；错误不展示堆栈。
- [x] 显示真实数量、时间、能耗与房间状态，提供灯/空调/窗帘控制和传感器模拟事件。
- [x] 实现增删改、迁移、主读数选择和故障面板；所有实体读取当前配置，不硬编码房间名称。
- [x] 提示内存保存与能力边界，reset 使用确认并保留用户配置。
- [x] 原有连接检查仍有效，包括离线重查；不伪造 Agent 任务功能。
- [x] 前端测试、类型、ESLint、构建通过。

## Task 3：集成与审阅

**Files:** `frontend/e2e/simulation.spec.ts`、调整 M1 的真实健康预期；`docs/verification/m2-simulation.md`。

- [x] 真浏览器验证默认 12 实体、开灯、设温、推进 20 分钟、模拟有人/开窗、故障和读回。
- [x] 验证新房间、第二盏灯、迁移、主传感器删除、归档与 reset 保留配置；手机宽度操作无溢出。
- [x] 查看桌面和手机截图；保存原始失败和最终检查记录。
- [x] 独立进行规范审阅与代码质量审阅，按实际问题修复并复核。

## Task 4：交付

**Files:** `README.md`、`CURRENT_CONTEXT.md`、项目内及父工作区路线、默认实体状态说明。

- [x] 写明内存保存、时钟、模型公式、故障模拟和 API 行为；不声称真实硬件或多用户已接入。
- [x] 运行适当最终检查并核对无遗留测试进程。
- [x] 更新 M2 勾选，提交 `codex/m2-simulation`，给用户演示步骤并停止。

验证命令：后端 `python -m uv run --frozen pytest -q`、`ruff check .`、`ruff format --check .`；前端 `npm.cmd test -- --run`、`npm.cmd run lint`、`npm.cmd run build`、`npm.cmd run test:e2e`。测试运行过程中仅使用本项目临时服务，不停止用户已有进程。
