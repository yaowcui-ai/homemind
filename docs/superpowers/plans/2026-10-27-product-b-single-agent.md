# HomeMind 产品 B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 在现有产品上交付自然语言单 Agent、必要澄清/确认和可继续核验的任务流程。

**Architecture:** 显式 LangGraph 规划，只读工具读取冻结事实，程序校验和已有 executor 统一写入。短事务保存任务并在执行前检查版本；现有规则路径保持语义。前端扩展现有任务页，按家庭恢复当前任务和未知提交。

**Tech Stack:** React/TypeScript/Ant Design/Query、Python/FastAPI/SQLAlchemy/MySQL、LangGraph/LangChain、DeepSeek 官方非思考 API。

设计输入：[B 补充](../specs/2026-10-27-product-b-design.md)、[M4](../specs/2026-10-27-m4-single-agent-design.md)、[PRD](../../product/prd.md)。基线 31604e3，分支 codex/product-b-single-agent。复用独立项目工作目录/环境，不新建和复制带密钥的工作目录。

## 1. 后端 AI 受控闭环

Files: 新建 backend/src/homemind/agent/{schemas,model,tools,graph,validation,service,routes}.py；修改 config.py、app.py、tasks.py、persistence/{models,database}.py；新增 migrations/versions/0003_m4.py；测试 backend/tests/test_m4_*.py。

- [x] 先以认证 API 写失败测试：配置未启用不调用模型；单灯计划只修改灯；三个场景使用动态实体；额外字段/未知工具/跨家庭/传感器/窗户/空计划不写；同名澄清沿用 task_id；三轮/调用预算；创建与回复/确认幂等、同家庭占用及执行前过期；无方案 verify 不会成功。运行 `python -m uv run --frozen pytest tests/test_m4_agent.py -q`，保存原始 RED，确认失败来自缺少入口/功能。
- [x] 增加明确 mode 和 agent_run 默认值/迁移，保持旧 rule 行。实现 Pydantic 契约及全量校验，用 `engine._validate_control` 验证能力但不执行；目标转换到现有 actions/constraints/temperatures/due_at_minutes 格式。
- [x] 实现只读 read_home/read_preferences，LangGraph 循环与硬预算、DeepSeek 非思考请求、严格输出解析和安全错误分类。模型网络异常不保存正文；token 未返回为未知。
- [x] 实现短事务受理/模型调用/重读执行，澄清/必要确认及重放，状态使用 waiting_input/waiting_confirmation/running/现有完成状态。任务详情暴露公开方案和真实运行记录；规则模式键不能当自然语言重放。测试逐条转绿，保存 GREEN。
- [x] 增加任务内 advance 原子推进/核验、按提交键只读查找，测试目标时刻证据、越过目标不补造、调试关闭不创建无法完成的未来任务、reset 和不能误推进其他 world。
- [x] Ruff/格式与后端全量回归，规格审阅通过后代码质量审阅；修复可复现问题后再进入界面。

## 2. 前端核心旅程

Files: frontend/src/api/{client,tasks,tasks.types}.ts、components/tasks/{TasksPanel,TaskDetail,labels,Tasks.module.css}、新增 AgentComposer.tsx/所需单测；App.tsx、vite.config.ts；新增 e2e/agent-tasks.spec.ts。

- [x] 先以组件/接口测试观察失败：明确规则/自然语言模式；未配置提示；等待真实响应不显示虚构进度；澄清/确认续接；当前任务刷新定位；未知提交只读恢复并同键重试；目标时间推进；账号隔离。`npm.cmd test -- --run` 保存 RED。
- [x] 对齐已实现 API 返回结构，更新类型/校验器；自然语言请求采用覆盖后端65秒预算的超时，普通接口维持原超时。新增持久提交键和家庭命名空间，刷新后不自动发写请求。
- [x] 沿用浅色布局增加自然语言输入、原任务补充/确认、公开理解与计划、运行记录、任务内仿真时刻与下一步。简单动作无冗余确认；模型关闭不阻断规则。必要状态以真实服务器返回为准。
- [x] 定向组件 GREEN，执行 ESLint/TypeScript/Vite、所有前端单测，浏览器验证规则回归及自然语言受控模型旅程和360/390px操作；保存截图。规格审阅后进行代码质量审阅。

## 3. 真实接入、证据与交付

Files: scripts/check_model.py、项目专属迁移检查；docs/verification/product-b-single-agent.md、docs/product/{decision-iteration-log,validation-plan}.md、README.md、CURRENT_CONTEXT.md、docs/homemind-development-roadmap.md。

- [x] 最小检查脚本默认不调用，显式参数授权最多两次合成家庭模型请求，验证工具读取及结构输出，不访问用户家庭/设备。只打印公开模型标识、调用/用量/时延、安全分类，失败退出码非0。
- [x] 仅在本项目文件内把用户提供的 API_KEY 适配到新后端配置，不打印值；若配置/供应商失败如实记录，不用替身补造真实模型通过。真实12场景和单/多Agent效果评测继续未开展。
- [x] 本项目 MySQL 迁移保留数据并检查旧规则、新自然语言/澄清的持久化；端口/进程只用本项目，临时服务由测试框架收尾。完整自动测试/静态检查通过后保存证据。
- [x] 更新启动/模型配置/最小演示和错误指引，记录真实问题→取舍→验证，区分可控测试、真实模型能力检查、仿真和硬件。Figma在线稿待补，不计已完成。
- [x] 最终规格/代码审阅、diff和敏感文件检查、本地提交与清理；交付B的实际范围/验证/剩余限制，不自动进入C。

## 最终交付记录

2026-10-27：后端209 passed/4 MySQL条件skip、Agent56 passed，真实MySQL4 passed；前端64 passed、lint/TS/Vite通过。完整Agent10/原MySQL21浏览器通过，最终状态补丁后定向5/6复验通过；独立规格、质量及根脚本审阅批准。根代理检查截图、端口退出及敏感值/改动范围，材料以B验证记录为依据。真实模型仅授权范围内2次合成只读工具/澄清检查，不是完整效果评测；在线Figma新增交互因额度仍待补。代码与材料保留本地分支，不自动进入C。
