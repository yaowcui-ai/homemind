# D3：专家并行与可审计全栈协作 Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development task-by-task with independent spec and quality reviews; critical business tests first RED then GREEN.

**Goal:** 增加可演示的舒适/节能/协调多Agent实验，并保留共享预测的S1公平对照，零真实模型请求完成工程验收。

**Architecture:** 沿用D2精确预测、GoalContract/Selection、统一执行与独立核验。LangGraph目标提取→预测→并行comfort/energy节点→固定顺序聚合→协调选择；专家只读、原文/事实/候选相同。沿用Task字符串mode及版本化JSON，无新增依赖/迁移。

**Tech Stack:** React/TS/AntD、FastAPI/Pydantic、LangGraph/LangChain Core、SQLAlchemy/MySQL、现有仿真。

2026-10-29，基线5c61fb3，当前独立仓库原目录功能分支codex/product-d3-experts，延续用户逐阶段委托。依据[D1已确认设计](../specs/2026-10-28-product-d1-design.md)；本轮不做D4/D5实际模型质量比较，不绕过Figma额度，不推送/合并/发布。

## 已定接口与角色契约

- AgentRequest.strategy增加expert_forecast；缺省/显式standard仍省略新hash键，S1不变。expert任务实际mode=multi_agent；回放/回答/确认/verify/advance/混合历史及前端恢复必须同时兼容两种Agent。debug关只开放standard。
- expert agent_run.strategy=expert_forecast，pipeline_version=d3-experts-v1；goal/forecast/selected_candidate_id/preference_optimal复用D2。新增本轮role_runs，最多4项且固定顺序coordinator_goal、comfort、energy、coordinator_plan；创建planning或尚未启动的取消可为空，不伪造完成记录。
- 每个RoleRun固定字段：role、status(succeeded|failed|cancelled|skipped)、model_calls、tool_calls、usage（input/output或null）、actual_model（或null）、elapsed_ms、failure_code（或null）、advice（或null）。succeeded仅表示该阶段结构化响应完成，不代表实际设备/目标成功。未运行skipped必须0调用、null用量/模型/Advice。两专家实际并行，不共享可变消息；协调和专家不能写设备。
- Advice固定字段：role(comfort|energy)、outcome(recommend|clarify|refuse)、preferred_candidate_id|null、evidence_refs（≤5唯一项，仅goal或candidate:<真实ID>）、public_summary（≤1000字公开摘要）。recommend必须指向可行候选并引用该候选；clarify/refuse必须null候选。非法schema/角色/引用整轮analysis_incomplete，公开RoleRun只保留有限错误及计数，不存非法raw/ID/私有provider字段。
- 每轮角色记录清楚标“本轮”，新回答重置当前goal/forecast/role_runs。rounds[].roles保留当轮至多4份角色计数/状态/耗时（不保留旧Advice，避免用新候选错误绑定旧意见），总轮数≤4。全任务model_calls/usage与实际所有角色调用汇总一致。
- 共享原子预算：每轮6、整任务12、最多3次补答；目标1，两专家各1，协调最多3（含只读工具续调）。拒绝预算预留不得增加实际调用计数；任何已开始调用即使取消/失败仍计，未知token为null。整轮65秒和单次20秒/剩余deadline沿用；不加后台重试或隐藏降级。
- 同事实专家建议不同是正常取舍；按用户显式priority协调，最终仍绑定原Goal/候选并必要确认。合法偏好次优保留原选与提示。任一专家异常不进入执行；有效refuse停止，有效clarify使用原任务补答（options=[]），不虚构成功共识。

## Task 1：后端协作与兼容

Files：schemas.py、graph.py、pipeline.py、service.py、tasks.py，按职责新增experts.py/budget.py；tests/test_product_d3.py及MySQL条件case。

- [x] 测试先RED：expert请求被旧schema422；verify零动作multi不得变成功；双专家用asyncio.Event证明同时进入而非依赖耗时阈值。原件写output/product-d3-backend-red.txt。
- [x] 实现严格Advice/RoleRun与只读证据校验、共享调用预留；新增LangGraph真实并行节点/固定聚合。S1共享Goal提取和预测资料、工具/硬约束不增加隐藏能力。
- [x] 补成功/意见分歧/专家clarify或refuse/非法证据/模型timeout或cancel/预算不足/未知usage/相反完成顺序/同名/版本漂移用例；任何异常0动作、实际阶段/计数可核对。不可伪造未运行阶段模型名或0token。
- [x] 实际mode及strategy摘要一致；同键重放/异策略409、原任务补答/确认、规则和S1兼容；zero-action multi后台verify及UI保护，不扩大规则语义。
- [x] Task JSON保留本轮RoleRun，rounds计数有限历史；补真实MySQL专用库新连接、混合历史/确认重放/实际推进case，默认测试用SQLite+注入模型/封外网。
- [x] 后端定向/完整/ruff及独立规格、质量审阅通过再交付。

## Task 2：React角色反馈与恢复

Files：tasks.types.ts、tasks.validation.ts、forecast.validation.ts、taskSubmission.ts、AgentComposer.tsx、TasksPanel.tsx、TaskDetail.tsx、labels.ts；新增RolePanel/role validation及相应测试。

- [x] 先RED覆盖multi响应类型/非法Advice/本轮绑定、失败零动作无核验按钮、未知提交刷新保原strategy/key、混合旧任务/配置兼容。
- [x] 增专家协作实验选项，S1继续可选、standard默认；不以每次关灯调用专家。mode表示实际策略，所有回答/确认/恢复分支同时支持multi。
- [x] 本轮意见与实际阶段/调用/未知用量展示；不同建议按实际candidate ID映射方案号，不声称实时流或既定性能收益。analysis_incomplete有恢复出口、没有确认或核验假成功。
- [x] 验证role/Advice/source/goal/selection引用与计数，旧无角色记录任务兼容，不将不认识的策略恢复为standard。移动布局复用现有组件。
- [x] 前端定向/全量、lint/TS/Vite、独立规格和质量审阅。

## Task 3：全栈验收与真实交付边界

Files：受控browser model、e2e、docs/verification/product-d3-experts.md、evaluation/results/product-d3-20261029.json及README/PRD/路线/迭代/接续。

- [x] 受控browser走M：原文→两位不同建议→协调原选→确认→实际读回/目标时刻核验→刷新。覆盖失败零动作/恢复、360/390px并目视，保留S1旧流程回归。
- [x] 独立真实MySQL条件case实际运行，不以SQLite冒充；首次API规划/确认阶段不变的家庭隔离和原键保护留证据。
- [x] 原始RED/失败保留，新结果明确受控模型/仿真/真实DB；源码与原件hash、链接/敏感信息/仓库范围检查。
- [x] 仅本地提交并交付D3。真实模型请求0；不报告多Agent准确率/节电/延迟优势，不勾M9。后续另授权D4开发真实评测及调优、D5新集验收。

## 实际验收与接续（2026-10-29）

D3完成本轮最小范围：根完整后端311passed/7条件skip，另真实MySQL7passed；前端93passed/19文件，受控浏览器完整17passed，根脚本33passed，Ruff/format/ESLint/TS/Vite通过。独立前后端规格和质量审阅通过；桌面1440/360/390px及展开/失败截图已目视。首次数据库未运行、业务RED和测试同步/编译错误均保留，不将它们改写成模型质量问题。

[验收报告](../../verification/product-d3-experts.md)、[结果与哈希](../../../evaluation/results/product-d3-20261029.json)记录原始证据、实际调用结构和限制。README/PRD/验证/迭代/路线/接续已同步。真实请求0，无新依赖/迁移/物理公式改变；仅本地保存本阶段，下一次D4先离线准备并另授权真实批次，D5新集/完整M9未完成。
