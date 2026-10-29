# D3：多Agent温控实验与全栈工程验证

日期2026-10-29（Asia/Shanghai），基线5c61fb3，分支codex/product-d3-experts。应用版本仍0.4.0；本阶段实现D1约定的最小专家实验，不新增依赖/迁移。真实DeepSeek请求0，角色调用数字来自注入模型方法，不能当作真实模型效果或费用。依据[D3实施计划](../superpowers/plans/2026-10-29-product-d3-experts.md)、[D1方案](../superpowers/specs/2026-10-28-product-d1-design.md)。

## 可运行链路

React显式选择“多 Agent 协作（实验）” → FastAPI保存multi_agent任务/原提交键 → 协调角色提取GoalContract → 现有精确隔离预测 → LangGraph两个专家节点并行 → join后固定顺序汇总 → 协调选择Selection → 共同程序门禁 → 用户确认 → 既有执行/独立读回/目标时刻核验 → MySQL公开证据与历史恢复。

标准关灯仍走standard短流程，增强单Agent single_forecast保留。多Agent范围仍是单房间温度/期限/仿真能耗，不做自动复杂度路由或新设备。专家不能改目标、期限或写设备；意见分歧是取舍，非法证据、格式、超时或取消不能被包装成成功共识。

| 层 | 实际增量与入口 | 核心约束 |
| --- | --- | --- |
| React | [RolePanel](../../frontend/src/components/tasks/RolePanel.tsx)、[角色解析](../../frontend/src/api/roles.validation.ts)、[策略/未知提交](../../frontend/src/api/taskSubmission.ts) | 意见/阶段状态可见，技术调用记录折叠；multi与single补答/确认/刷新均保原键；预测与实际执行分开 |
| API/持久化 | [service](../../backend/src/homemind/agent/service.py)、[tasks](../../backend/src/homemind/tasks.py) | 实际模式/strategy/hash一致，旧standard摘要不变；multi零动作verify不得变成功；确认仅在execute后同事务save_engine |
| LangGraph | [pipeline](../../backend/src/homemind/agent/pipeline.py)、[图节点](../../backend/src/homemind/agent/graph.py) | goal→forecast→comfort/energy并行→join→coordinator，原文/公开事实/所有候选相同，独立消息和上下文 |
| 专家与预算 | [experts](../../backend/src/homemind/agent/experts.py)、[budget](../../backend/src/homemind/agent/budget.py)、[schema](../../backend/src/homemind/agent/schemas.py) | 严格Advice、每轮6/任务12原子预留、20秒/请求和65秒整轮；预算拒绝不计成已发调用 |

三个Agent角色对应四个实际模型阶段：coordinator_goal、comfort、energy、coordinator_plan；不是四个专家。role_runs是本轮固定四槽，未进入阶段为skipped/0调用；succeeded仅表示结构化阶段响应完成，不能代表设备或目标成功。

历史rounds[].roles仅保存角色指标/状态，无旧Advice；新补答重置当前目标、预测及角色意见，避免用新候选解释旧建议。取消先等待并行子节点结算再保存已发次数；未返回usage保持null，零请求新轮不能把已有已知用量清空。标准、S1、M共用执行器、版本门禁和确认接口。

## 实际开发案例与产品取舍

以下是受控工程场景，设备为仿真、模型为明确的注入夹具；不计入自然语言准确率，也没有独立保留集结果。

| 场景/触发 | 实际机制与结果 | 不能外推的结论 |
| --- | --- | --- |
| 默认客厅28℃、60分钟内26℃，能耗优先，帘允许调整、卧室不动 | 舒适建议auto/帘0%（17分钟/850.050Wh），节能建议low/帘100%（53分钟/550.000Wh）；协调原选后者，确认才执行，到期实际核验。正常夹具4次方法调用 | 这些取舍来自现有仿真和固定角色夹具，不证明真实模型正确、现实节电或M胜过S1 |
| 专家引用candidate:PRIVATE-BAD-ADVICE-ID | 能耗阶段invalid_advice，Advice/raw摘要不保留，协调skipped；总3次方法调用、0动作，前后端verify不能生成成功 | 只证明该字段和程序边界，不保证任意公开文字都事实正确 |
| 专家澄清、补答请求未提交但响应未知 | 原任务waiting_input，刷新只GET；同键原体重试后同task/turn+1，累计7次方法调用，当前四槽重新生成、两轮指标保留，无旧Advice | 本例只到待确认；完整执行核验由正常案例验证，不合并冒充该例已经执行 |
| 两专家先后完成顺序相反 | asyncio.Event证明两个节点均进入后才能完成，join和role_runs按固定角色顺序；不靠“耗时短所以并行”推断 | 没有真实API并行加速百分比或稳定时延分布 |
| 专家格式、角色、重复/外部证据、拒绝、澄清 | 非法分析整轮analysis_incomplete；合法refuse停止、clarify原任务可补答；不裁掉坏专家偷偷继续 | 无“只要增加专家就更安全/更准确”的总体保证 |
| 两个在途peer被取消/其中一个已完成 | 等待实际子任务结算后记录已发/unknown用量；未运行协调0调用，家庭占用释放 | 没有新增用户取消按钮/后台恢复；真实HTTP结果未知仍需原键读事实 |
| 6次/轮、12次/任务边界 | 发送前共享异步锁预留；预算不足阶段failed但0调用，完全未进入skipped；无新请求轮保留历史已知usage | 这是任务执行预算，不是用户账单限额；未来评测另有批次授权账本 |
| 混合历史与新连接 | 同用户rule/standard/S1/M，独立Database连接读取列表/各detail；确认重放与实际推进复用已保存JSON，无模型重跑 | 新app/连接不等于独立OS进程重启；SQLite不冒充真实MySQL |

默认仿真假设及全部候选数值已在[D2](product-d2-forecast.md)公开。协调有公开rationale及原始candidate_id；合法偏好次优仍保留并标preference_optimal=false，不能由程序换成最优后计作Agent成功。

## 真实问题与修复记录

- 初始三项RED：旧schema拒绝expert、multi零动作可能被verify改成功、旧流程没有专家Event并行屏障；原件output/product-d3-backend-red.txt。
- 原子预留和取消账本之外，还实际复现“零请求新轮抹掉已有已知usage”并修复；不将未知用量记零。
- 确认失败分支仍save_engine：真实RED后改save=False，仅实际execute后显式同事务保存物理状态。标准确认、S1、M均回归。
- 一条取消测试用30次sleep(0)猜peer已结构化完成而失败；改用明确完成Event后通过。保留原失败，不把测试同步缺陷写成实际丢账修复。
- 前端审阅复现失败分析可伪装确认/成功、历史夹带旧Advice和重复turn计数；新增反例RED，绑定顶层状态/四槽成功/引用/历史唯一连续轮次。空RoleRun只能合法未启动planning或早取消且当前字段全空，不能绕过analysis_incomplete约束。
- 另修测试自身getByRole误用exact选项的TypeScript错误；没有修改产品语义来通过该编译检查。

独立前后端规格与质量审阅均通过。真实模型质量调优、收益仍未运行；这些修复是工程正确性和记录可信度的优化。

## 运行证据

根最终完整后端311passed/7 MySQL条件skip，231.32s，原件output/product-d3-backend-root-final.txt；另以本项目专用真实MySQL实际运行7passed/12.06s，原件output/product-d3-mysql-final.txt。含同户rule/standard/S1/M混合历史、新Database连接逐detail读回、M确认原键重放及60分钟实际推进核验；新app/连接不冒充OS进程恢复。实现方之前311passed/7skip原件也保留，条件skip不当成真实库通过。

MySQL首批7项均在fixture.ready失败，尚未注册测试账号；连接127.0.0.1:13306被拒。查到本项目容器已Exited(137)，setup_mysql保留已有数据启动后健康/迁移通过。原件output/product-d3-mysql-not-running.txt保留，不推断原退出原因或改写成业务失败。

前端最终19文件93passed/208.32s，继续沿用D2已明确的单worker/15秒测试预算，原件output/product-d3-frontend-full.txt；定向12passed/26.16s也保留。ESLint、TypeScript/Vite最终构建通过（构建29.64s），原件output/product-d3-{lint,build}-final.txt。没有因这次检查修改测试断言或扩大既定超时。

阶段调用记录折叠后的完整受控Agent浏览器17passed/约2.1分钟，原件output/product-d3-browser-final.txt，含D3新增3例及原14例。桌面1440/360/390px几何检查和截图目视通过，展开阶段记录可见实际注入模型名/调用/未知Token，失败详情无确认或核验按钮。截图output/product-d3-roles-{desktop,360,390,expanded}.png及product-d3-analysis-incomplete.png。临时18110/5176服务已退出，本项目MySQL保留。没有本轮全部真实MySQL浏览器套件重跑声明。

根资源/评测脚本33passed/25.74s（output/product-d3-root-scripts.txt）；后端全部src/tests Ruff和格式检查通过（56文件），受控browser脚本Ruff/格式通过。可移植[结果与源码/原件哈希](../../evaluation/results/product-d3-20261029.json)将LF归一化源码与原始字节日志分开；日志/截图在忽略的本机output目录，摘要随仓库保存。没有将注入模型调用或测试数量计作DeepSeek准确率、成本或架构提升。

复现核心检查（后端测试封锁默认外网，真实MySQL需另由本项目配置注入专用test库环境；不能复制其他项目连接串）：

```powershell
# backend目录
& .venv/Scripts/python.exe -m pytest -q
& .venv/Scripts/python.exe -m ruff check src tests
& .venv/Scripts/python.exe -m ruff format --check src tests
# frontend目录
npm.cmd test -- --run --maxWorkers=1 --testTimeout=15000
npm.cmd run lint
npm.cmd run build
npm.cmd run test:e2e:agent
# 项目根目录
& backend/.venv/Scripts/python.exe -m pytest scripts/tests -q
```

MySQL使用scripts/local_config.py的test_environment()在子进程注入环境，运行backend/tests/test_m3_mysql.py；不将该环境或连接串打印。无需新迁移/装包，实际打开步骤仍见[README](../../README.md)。在线Figma本轮没有更新，不能把React截图当成已补齐Figma原型。

交付核对：本轮修改文档152个本地链接有效，28份变更源码LF哈希及46份日志/截图原字节哈希一致；仅检查本项目已配置敏感值，未进入变更文件或这些原件。独立仓库/分支与修改范围核对通过，无依赖锁、迁移、仿真物理公式或其他项目文件更改。原始output仅本机保留，提交可移植摘要，不推送/合并/发布。

## 面试能讲什么

可以展示React→FastAPI→LangGraph并行专家→MySQL→统一执行/独立核验的可运行闭环；解释为什么专家只读、不同意见如何按偏好协调、调用预算怎样原子预留、取消/失败怎样准确记账、为何混合历史和零动作verify也要扩展，以及前端为什么不能只按字段形状信任响应。

不能声称多Agent质量/效率提升、真实节电、已完成用户研究/线上运营、完整Figma在线新状态或图检查点恢复。相同预测资料的S1仍可用；D4/D5将验证专家额外调用是否值得，允许无收益或退化。新模型批次需另授权，本轮未使用C2余量。
