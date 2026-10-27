# HomeMind M3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付认证独立家庭、MySQL 持久化、三模板规则基线并真实验证，停在 M4 前。

**Architecture:** 关系仓库在家庭事务内重建/保存 M2 引擎，Cookie/CSRF 上下文限定全部业务访问；规则和手动控制共享能力与执行边界。MySQL Compose 与凭据均独立。

**Tech Stack:** FastAPI、Pydantic、SQLAlchemy 2.0/asyncmy、Alembic、Argon2id、MySQL 8.4、React/Ant Design/Query、pytest/Vitest/Playwright。契约以 [M3 设计](../specs/2026-10-27-m3-accounts-persistence-design.md) 为准。

## Task 1：基础设施与迁移边界

Files：`deploy/compose.mysql.yaml`、`deploy/mysql/init/01-test-db.sh`、`scripts/setup_mysql.py`、`scripts/serve_e2e.py`、`.gitignore`；后端配合 `persistence/{models,database,codec}.py`、`migrate.py`、`migrations/versions/{0001_m3,0002_m3}.py`。

- [x] 检查空闲端口和同名资源标签；创建 `.local` 安装 UUID 与随机凭据，仅给本项目文件写入。用 `docker compose ... config --quiet` 验证，无凭据输出。
- [x] 首次启动本项目 MySQL，核验标签、服务器版本、健康；不重建既有同名不匹配卷。
- [x] 添加关系模型和初始迁移，迁移先核验库名/空库或安装标记，配置/连接错误只显示脱敏说明。
- [x] 实际升级 app/test 库；重复运行不播种/清库；记录镜像摘要和迁移版本。

## Task 2：后端认证、家庭与持久规则闭环

Files：`backend/src/homemind/{config,app,auth,preferences,rules,executor,tasks}.py`、`persistence/` 与已有 simulation routes/service；`tests/conftest.py`、`tests/test_m3_{accounts,security,migrations,tasks,mysql}.py`，以及原 M2 测试/版本/锁文件。

- [x] 先写并运行隔离、认证/CSRF、codec、幂等/规则关键失败用例，保留原始 red 记录。
- [x] 实现 Argon2id/不透明会话及轮换，事务注册独立模板；所有配置/控制/调试/任务均取认证 home_id。
- [x] 实现模型与 codec 的完整存取，Decimal/归档/待执行动作和时钟保留；主绑定不隐式重建。迁移已有 M2 用例到认证测试客户端。
- [x] 实现三模板、保留/保护和能力限制，统一绝对动作执行与独立核验；未来目标保留等待状态。
- [x] 实现同家庭幂等、立即占用/事务锁、任务/动作/事件保存与只读查询和无动作重发的 verify。
- [x] 运行后端 pytest/Ruff/格式；独立规格、质量审阅并修复。

核心认证/幂等验收序列：

```python
bootstrap = client.get('/auth/session').json()
client.headers.update({'Origin':'http://testserver','X-CSRF-Token':bootstrap['csrf_token']})
account = client.post('/auth/register', json={'username':'test_owner','password':'OnlyForTests_12345'}).json()
client.headers['X-CSRF-Token'] = account['csrf_token']
home = client.get('/simulation').json()
body = {'scenario':'away','room_ids':[r['id'] for r in home['rooms']]}
first = client.post('/tasks', json=body, headers={'Idempotency-Key':'task-key-0001'}).json()
again = client.post('/tasks', json=body, headers={'Idempotency-Key':'task-key-0001'}).json()
assert first['id'] == again['id']
```

## Task 3：网页认证与规则任务

Files：`frontend/src/api/{client,auth,tasks,preferences}.ts` 与 types/tests；`components/auth/`、`components/tasks/`；App、SimulationDashboard、Query keys；`frontend/e2e/{helpers,auth,tasks}.ts` 及原浏览器用例/config。

- [x] 先写 Cookie/CSRF 处理、401 清理、任务幂等重试与关键表单失败用例。
- [x] 统一同源客户端，内存持有 CSRF、请求超时/脱敏错误，退出取消旧请求并清空用户缓存。
- [x] 实现注册/登录、账号退出和持久化提示；按 home_id 分键，保留 M2 家庭功能。
- [x] 实现三模板表单、偏好最小编辑、任务列表/动作结果与目标核验；同内容重试复用幂等键。
- [x] 跑前端单元、类型、lint/build，独立审阅并修复。

## Task 4：真实集成、重启与交付

Files：`scripts/verify_m3.py`、浏览器用例、`.github/workflows/checks.yml`、`docs/verification/m3-accounts-persistence.md`、README、CURRENT_CONTEXT、两份路线及默认实体状态。

- [x] 独立 test 库真实验证双账号、所有跨家庭 ID、Cookie/CSRF、退出、幂等、并发占用及模板只初始化一次。
- [x] 实际启动自己的 API 进程，创建/更改配置/环境/偏好/任务，停止并重启同配置进程后核对原 ID 与结果；只停止身份核实的本轮进程。
- [x] 真实浏览器验登录/注册、切换账号无旧数据、原 M2 操作、三模板/故障与等待核验、390px 无溢出；查看截图并保留失败。
- [x] 最终静态/构建/锁/合适测试通过，检查服务资源状态；更新阶段证据、启动/停止/演示命令和限制。
- [x] 提交 `codex/m3-accounts-persistence`，仅提交父仓库本项目接续文档，停止在 M4 前。

主要命令：后端 `python -m uv run --frozen pytest -q`、`ruff check .`、`ruff format --check .`；根目录 `python scripts/setup_mysql.py`、`python scripts/verify_m3.py`；前端 `npm.cmd test -- --run`、`npm.cmd run lint`、`npm.cmd run build`、`npm.cmd run test:e2e`。MySQL 验证缺配置时明确跳过/失败，不能显示伪通过。
