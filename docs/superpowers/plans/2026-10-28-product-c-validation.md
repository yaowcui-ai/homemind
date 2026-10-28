# 产品 C：场景验证与可靠性实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 扩充产品案例并真实验证单Agent，修复推进未知恢复，形成可核对的产品迭代。

**Architecture:** 保留B的LangGraph/只读工具/程序校验/共用执行器。评测独立临时合成数据库，真实请求采用共享持久40次硬上限；推进记录随业务事务持久化，React复用TaskSubmission。

**Tech Stack:** Python/FastAPI/SQLAlchemy/Pytest，React/TypeScript/Vitest/Playwright；不新增服务或框架。

---

## 1. 案例及评测器

- [x] `evaluation/product-c-cases.json`：至少36例，明确 `id/category/goal/setup/text/expected/requirements/source`，真实批次按固定优先序选取；评分在调用前冻结。
- [x] `scripts/tests/test_product_eval.py`：先验证预算重启不清零、默认无网络、成功/异常/未知分开评分、错误目标不误判、账本/结果不覆盖。命令 `backend/.venv/Scripts/python.exe -m pytest scripts/tests/test_product_eval.py -q`，先观察要求缺失再实现。
- [x] `scripts/product_eval.py` 与必要小模块：新建临时SQLite家庭，实际API/图，合成数据、官方端点、每次名额先落盘、只输出公开白名单。`--real`外不加载配置；已有批次只允许显式续跑且不重置名额；预期模型差异作为失败记录，不吞掉。
- [x] 先离线自检，再真实最多40次；原始逐例JSON、案例/提示摘要、实际版本和全局请求账本保存到本项目忽略的output；不运行其他项目或日常家庭。

## 2. 推进可靠性

- [x] 修改 `backend/src/homemind/tasks.py`、`persistence/models.py` 和新Alembic迁移，先在 `backend/tests/test_m4_agent.py`/新测试验证响应丢失后同键重放不重复+10、旧时间拒绝、同键异体拒绝、家庭隔离、真实重新连接记录存在。
- [x] 前端 `api/tasks.types.ts`/`tasks.ts`/`taskSubmission.ts`/校验/任务面板接入新体/key，扩充已有相关单测，验证刷新GET恢复、5xx保key、跨页/迟到状态不回退。保持sessionStorage现有家庭隔离。
- [x] `npm run test -- --run`、lint/build；后端相应单测/Ruff。Playwright补推进响应丢失刷新场景，使用受控模型，仅算程序证据。
- [x] 实际HomeMind MySQL迁移至新head并在专用测试库验证持久行为；应用库保留数据，不做reset。若Docker未运行先检查，不擅自停止别的容器。

## 3. 结果与小范围优化

- [x] 基于原始运行在 `docs/product/product-c-evaluation.md` 写分子分母/证据/局限；在 `docs/product/product-c-cases.md` 提供人可读案例与场景价值，绝不以回归通过数冒充理解率。
- [x] 真实Bad Case列P0/P1/P2，按用户影响、发生证据和成本解释；有修复则先受控RED→GREEN，同口径复测只用剩余请求预算。预算耗尽不再调用，明确未真实复测。
- [x] 必要用户错误/下一步文案按实际情况修改，不增无意义页面；保留无外部研究、无多Agent对比、Figma待补状态。
- [x] 更新 `prd.md`、`validation-plan.md`、`decision-iteration-log.md`、README、路线与接续。独立规格后质量审阅，根代理验证受影响检查、链接与敏感数据不入Git。仅本地提交本阶段文件，不推送/合并。

## 实际交付与边界

36例案例、18例真实初批13/18、5个Bad Case保留；C04一次同条件复测通过，38+2=40请求用满。程序/数据库/浏览器与模型证据分开，详见[C报告](../../product/product-c-evaluation.md)。独立规格后质量审阅批准；已修home_busy原键丢失与评分集合/固定分母问题，原始RED留存。

后端完整214/4条件skip后，最终推进6/Agent56定向通过；真实MySQL迁移0004及5项通过。前端完整66后，busy25/反馈18定向通过，lint/build通过；受控浏览器新增2通过。脚本最终23项通过（含15评测器），根代理131条本地链接与数据/原件SHA核对通过。未全量重跑最终浏览器，未重新执行全部旧阶段检查。

C06/C09/C12/C14未真实复测，C14仍需定位；用户观察、完整在线Figma交互、单多Agent对照与正式保留集未完成。后续先处理这些P1，再进入D。只保留本地分支，不推送/合并/发布。
