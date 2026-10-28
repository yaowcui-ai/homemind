# D2：隔离预测与增强单Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox syntax for tracking.

**Goal:** 自然语言温控任务可在React查看候选仿真预测，确认后经既有执行器和实际deadline核验；建立未来多Agent同工具基线。

**Architecture:** 保留standard旧摘要和旧图。新增single_forecast：严格GoalContract提取→精确隔离预测→模型Selection→目标/候选绑定校验→必要确认。全部角色仍单Agent，预测不写真实家庭。沿用Task JSON无迁移，实验图上限6/轮12/任务65秒，未获授权不调用真实模型。

**Tech Stack:** React/TS/AntD、FastAPI/Pydantic、LangGraph/LangChain Core、SQLAlchemy/MySQL、现有Decimal仿真。

依据：[D1规格](../specs/2026-10-28-product-d1-design.md)。用户本轮强调可展示全栈，故把D3原定的**S1轻量入口/候选展示**提前到D2；专家角色/multi_agent历史等仍属D3。当前独立仓库干净、在codex/product-d2-forecast原目录使用现有独立依赖和配置，避免新worktree复制密钥/虚拟环境。无推送/合并/发布。

## 对外契约（实现间共享）

请求可选strategy=standard|single_forecast。缺省/显式standard都从hash及保存请求删除strategy，旧body的空keep/protected仍保留；single_forecast进入摘要，未知expert策略422。/tasks/agent/config增加strategies可用列表（前端旧配置没有该字段时视只支持standard）。

agent_run只为实验新增strategy=single_forecast、pipeline_version=d2-forecast-v1、goal、forecast、selected_candidate_id及preference_optimal。goal/forecast在澄清或失败时可为null。GoalContract字段与D1一致；cover_constraint使用allow_open_close|keep；kind=goal。Selection使用kind=selection、candidate_id和完整plan。goal保留/保护必须涵盖表单约束。

forecast={model_version,source:{world_id,revision,config_revision,simulated_minutes},energy_scope_entity_ids,candidates:[{id,fan_mode,cover_position_pct,end_temperature_c,first_observed_goal_minute,deadline_met,energy_wh,actions}]}。cover_position_pct可null，actions为现有Intent列表。最多4候选；没有可行候选时同任务澄清/零动作；forecast_unavailable解释读数/实例/上限缺口。初态达标分钟0；Wh是目标空调/存在目标窗帘精确增量且包含移动。

## Task 1：后端预测、图及API（主要业务测试先RED）

文件：新增agent/forecast.py、pipeline.py及tests/test_product_d2.py；修改agent/schemas.py、service.py、graph.py等局部。GoalContract/Selection复用schemas.py，无需额外schema文件或app生命周期修改。

- [x] 固定业务RED：`test_forecast_isolated_and_deadline`以SimulationService默认初态、26℃/20min，验证low26.8/auto26.0与源快照/私有Decimal/队列不变；新模块缺失时实际执行记录output/product-d2-backend-red.txt。
- [x] 定义严格GoalContract、Selection；构建≤4个合法候选。精确clone使用新SimulationService(seed=False)+复制records/queues/Decimal/新锁；不可blind deepcopy引擎或从公共snapshot回填。拒绝所有未知物理输入/故障/pending、缺少感知、多空调/多窗帘及保留/保护冲突。
- [x] 预测实体/房间/归档/步数均有上限，受限worker+实际退出才释放槽、分块单调时钟/取消；测取消后无并发叠加。只返回公开范围，独立重放匹配，不泄露非目标房间。
- [x] LangGraph编排Goal→forecast→planner：共同原文/问答/公共事实、S1同预测资料、严格解析。每轮实际发出≤6且每任务≤12，模型单次≤20/整轮≤65秒；取消/失败实际issued用量保留未知。standard3次逻辑不变。
- [x] API先RED：single_forecast提交必须waiting_confirmation且0动作；同键同体重放、换策略同键409、显式standard匹配旧hash；确认/推进实际达标并存JSON；漂移/错候选/改目标/keep遗漏/额外动作一律零写。必要确认不能被模型或低影响判定跳过。
- [x] 关闭私有输出/继承tracing；失败不保存非法ID/raw；实验元数据可审计且有界。无候选时问放宽要求，不自动改期限/温度；合法但偏好次优不能被程序改成最优，preference_optimal按原选择计。
- [x] 运行定向与完整后端回归、ruff/format；规格和质量独立审阅，修复并复验。模型全部注入，不冒充真实NL评测。

## Task 2：React入口、边界校验与结果卡

文件：api/tasks.types.ts、tasks.validation.ts、tasks.ts、taskSubmission.ts；components/tasks/AgentComposer.tsx、TaskDetail.tsx、新ForecastPanel.tsx；对应测试。

- [x] 先写RED：可识别/拒绝合法/非法forecast，保持旧task兼容；strategy不同待确认body不得复用意图，刷新保留原策略/key。
- [x] 类型对应上述契约；schema验证候选上限/数值与引用关系，不将未知对象强转为React数据。旧draft/pending缺strategy视standard；未知策略不恢复为可执行请求。
- [x] 在模型config明确支持且演示debug允许时显示“温控方案比较（实验）”选择；standard默认。实验给出含期限/优先级/不动项的例子，不显示评测预算/内部schema。
- [x] ForecastPanel展示原目标/偏好、候选风速/帘位/截止温度/首次达标/范围Wh、原选/次优提示；明确仿真预测不是实测，动作仍待确认。不可达/不可预测显示下一步，不伪造角色/进度。
- [x] 前端单测先RED后GREEN，完整vitest/lint/TS/Vite；无新付费服务或UI大改。

## Task 3：全栈验证与交接

文件：scripts/serve_agent_e2e.py仅受控模型分支；frontend/e2e/agent-tasks.spec.ts或新增D2 spec；backend/tests/test_m3_mysql.py新增有条件真实MySQL case；docs/verification/product-d2-forecast.md、README/PRD/路线/迭代/接续。

- [x] 受控browser实际走提交实验→候选→确认→推进→实测→刷新；360/390px及桌面目视。测试fixture明确标受控模型，非真实DeepSeek。
- [x] 独立MySQL验证新JSON重新连接读回/确认重放，使用本项目既有test标识；Docker未就绪则如实记录并继续离线工作，不冒充MySQL通过。
- [x] 独立离线重放每候选、隐藏输入拒绝、边界规模耗时，记录实际值；测试不把同一forecast函数输出当自己的gold。
- [x] 本阶段真实模型请求0，无D预算授权。代码/用例/文档链接/密钥模式/仓库边界审阅，更新未实现边界；本地提交，工作区干净后交付并停止D2。

运行命令（项目根目录）：`backend/.venv/Scripts/python.exe -m pytest backend/tests`需工作目录backend以使用其pytest路径，实际命令在backend中`.venv/Scripts/python.exe -m pytest`；前端`npm.cmd test -- --run`、`npm.cmd run lint`、`npm.cmd run build`。红绿原件写output，本轮报告只列实际执行结果。

## 实际交付核对

D2实现、必要RED/GREEN、独立规格/质量审阅及最终回归已完成；实际结果和边界见[验证记录](../../verification/product-d2-forecast.md)。前端最终使用单worker/15秒测试预算，原5秒超时保留；真实模型0请求。工作保留本地功能分支，不推送、合并或发布。M5/M9与D3—D5未完成。
