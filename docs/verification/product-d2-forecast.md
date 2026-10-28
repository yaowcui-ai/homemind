# D2：增强单Agent全栈实现与验证

日期2026-10-28（Asia/Shanghai），基线00e031e，分支codex/product-d2-forecast。应用仍0.4.0/M4；本阶段是未来多Agent的同工具S1基线，未实现专家角色。无新增依赖/迁移；真实模型请求0。执行依据：[D2计划](../superpowers/plans/2026-10-28-product-d2-forecast.md)、[D1规格](../superpowers/specs/2026-10-28-product-d1-design.md)。

## 实际实现和用户价值

React“任务助手→自然语言任务→温控方案比较（实验）”提交目标、期限、优先级和不动项。FastAPI保存原任务与提交键，LangGraph提取严格GoalContract，在精确克隆上生成最多4个候选，再由同一规划角色选择并输出Selection。程序重新绑定目标/动作/候选/版本，用户确认后才进入既有执行器；推进到目标时刻后独立读回温度。MySQL持久化实际公开契约、预测和执行证据，刷新读原任务，不把预测当实测。

产品增量是让取舍可核对，而非增加角色数量。舒适优先只代理首次公开温度达标时间，能耗优先只比较目标空调及存在窗帘的增量Wh。原选合法但偏好次优会提示，程序不替模型选成最优。硬条件无可行候选时澄清、零动作，不偷偷改温度/期限。

| 层 | 实现入口 | 可解释机制 |
| --- | --- | --- |
| React/TS | [表单](../../frontend/src/components/tasks/AgentComposer.tsx)、[预测卡](../../frontend/src/components/tasks/ForecastPanel.tsx)、[解析边界](../../frontend/src/api/forecast.validation.ts) | 选择strategy、候选证据/原选/次优、预测实测分开；拒绝损坏或跨快照绑定的响应 |
| FastAPI/业务 | [服务](../../backend/src/homemind/agent/service.py)、[schemas](../../backend/src/homemind/agent/schemas.py) | standard旧hash兼容；实验强制确认、短事务、家庭占用与版本检查 |
| AI编排 | [pipeline](../../backend/src/homemind/agent/pipeline.py)、[有界模型图](../../backend/src/homemind/agent/graph.py) | goal→forecast→planner，严格输出，原文/问答共享；6次/轮12次/任务、65秒截止、已发调用与未知用量保留 |
| 仿真/并发 | [forecast](../../backend/src/homemind/agent/forecast.py) | 新锁/Decimal/故障/队列/记录精确克隆，2个worker有界计算、实际退出才释放槽，每步检查取消/截止 |
| 数据/执行 | 现有Task.agent_run JSON、Action、executor/deadline核验 | 无新表/DDL；预测规划只保存Task，不调用物理save_engine；确认重读版本后统一执行 |

未配置模型时仍显示原因；调试关闭只公布standard，不能开启等待未来温度的实验。旧任务/请求/草稿/pending无strategy仍兼容standard；single_forecast参与提交摘要，换策略不能复用未决意图的原键。

## 实际案例与反例

默认夹具：客厅28℃、卧室27℃；窗户已知关闭、occupancy=false、灯和空调off、帘100。以下均为仿真，不外推现实节电。D1只重放合帘两项；D2实际扩大到4候选，不能沿用“合帘必定最优”的假设。

| 60分钟内26℃的候选 | 首次观测达标分钟 | 截止℃ | 范围增量Wh |
| --- | --- | --- | --- |
| low、帘0% | 41 | 26.0 | 550.050 |
| low、帘100% | 53 | 26.0 | 550.000 |
| auto、帘0% | 17 | 26.0 | 850.050 |
| auto、帘100% | 18 | 26.0 | 850.000 |

限定这4候选：能耗优先是低风开帘，尽早达标优先是自动风合帘；不是全局节能最优。20分钟合帘低风26.8℃、auto26.0℃仍由实际重放验证。候选Wh精确累积后一次舍入，包含实际帘移动，不能把失败0耗能算节能胜出。

其他实际受控覆盖见[后端用例](../../backend/tests/test_product_d2.py)：

- 1分钟硬期限全部不可行→原任务澄清；实际回答改60分钟后沿原task进入待确认。
- 帘固定50%、初态温度已达标→2候选、first_observed_goal_minute=0，帘不写；其他房间未知信号不泄露。
- 缺窗户/占用、非主感知未知、故障/pending、多空调/多帘/超限→解释不可预测、零写。
- 目标/期限漂移、附带灯动作、漏keep、未知候选/动作不匹配→整批拒绝，非法模型ID不落库。
- 首轮同名房间→程序澄清，不因实验输出是goal而绕过旧歧义保护。
- 已发请求被取消/超时、总预算耗尽→保存实际次数/unknown用量，家庭占用释放；worker未退出仍占计算槽。

这些证明受控工程行为，不是新的真实语言案例通过率；44个旧语言案例仍全属开发集，D4真实调优、D5新集对照尚未运行。

## 审阅发现的实际修复

| 原问题与真实RED | 修改和复测边界 |
| --- | --- |
| 实验plan_round默认save=True，禁止物理save的测试实际AssertionError | 实验事务save=False，仅保存Task；standard可能立即执行仍保留True，确认执行另用写事务 |
| 合法候选后最终Plan因disabled keep失败，却先保存selected=c1/proposed_plan=null | 所有共同Plan校验通过后才发布选择/偏好/方案；失败仍可由前端识别，零动作 |
| 前端仅验预测形状，接受外部scope/目标参数/不允许fan/错source；原选比较漏room_id | 绑定请求、初始快照、goal、scope、候选动作和完整原选；新增非法体实际RED→GREEN，不把非法数据强转组件 |
| forecast_unavailable无goal时预测卡隐藏，用户只有原因无出口 | 详情首屏说明检查感知/实例/规模，恢复后新建或切常规助手；不可达仍原任务补答 |

原件保留output/product-d2-backend-red.txt、product-d2-ambiguity-red.txt、product-d2-physical-save-red.txt、product-d2-frontend-red.txt等。部分后续RED保留工具输出和本表说明，不补造完整原始日志。独立前端/后端规格和质量均审阅通过，仅证明本阶段实现范围，不是模型或真实硬件效果认证。

## 验证记录与边界

最终后端完整275passed/6skip，145.24s，原件output/product-d2-backend-final.txt；6项MySQL条件跳过另以专用真实MySQL实际运行6passed/11.70s，原件output/product-d2-mysql.txt。包括新增D2独立Database/连接读回JSON、创建/确认同键重放及60分钟目标核验。新连接/新app不是独立操作系统进程重启，不作其声明。SQLite也不冒充MySQL。此前D2定向39passed/22.45s仅为当次定向；旧37passed及272全量原件是早期进度，不作为最终状态。

前端最终`npm.cmd test -- --run --maxWorkers=1 --testTimeout=15000`为17文件84passed/158.23s，断言未改，原件output/product-d2-frontend-full-15s.txt；默认5秒预算全量82passed/2超时（工具输出），单worker5秒83passed/1超时（output/product-d2-frontend-full-serial.txt），未据此宣称修复线上竞态。独立12项定向也通过。最终TS/Vite构建通过（Vite8.27s），ESLint通过；output/product-d2-frontend-{build,lint}-final.txt保留输出。

最终受控浏览器全Agent套件14passed/约1.5分钟，原件output/product-d2-browser-final.txt；含新增D2整程与13个已有场景/恢复/移动检查：提交实验→预测时家庭不变→确认才发动作→到期核验成功→刷新无新POST。桌面及360/390px几何检查通过，root目视桌面/360px截图。受控模型fixture不是DeepSeek，不计作真实模型请求或理解准确率。没有本轮全量真实MySQL浏览器重跑声明。

根脚本33passed/11.37s，原件output/product-d2-root-scripts.txt；后端15文件及受控browser脚本ruff/format通过。可移植[结果与源码/原件哈希](../../evaluation/results/product-d2-20261028.json)分别保存受控模型、真实MySQL、仿真和失败记录口径；代码hash用LF归一化，原件hash按真实字节。无需从测试数量推算模型准确率。

### 有界计算实测

原轻负载：16房/256实体，新增灯全off、单worker，带并发pytest时27728ms/lag66.546ms，不能称最坏负载或与新结果算性能提升。补测[压力脚本](../../backend/scripts/benchmark_forecast_stress.py)，主动混合空调/开灯/窗开/有人及合法归档，无同时请求测试套件：

| 负载 | 候选/步数（每worker） | 实测耗时ms | 事件循环最大lag ms |
| --- | --- | --- | --- |
| 16房256实体，混合启用，单worker | 4/5760 | 20076 | 41.770 |
| 同规模，双worker | 各4/5760 | 35603 / 35599 | 174.523 |
| 同规模，244真实归档，单worker | 4/5760 | 6892 | 40.897 |

全部源快照未变，进程工作集约36.2→41.1MB，峰值约41.2MB，含Python/库及同进程先前批次；不是纯算法内存或普遍最坏耗时保证。两worker仍有GIL争用，不能说CPU完全不影响事件循环。若提取和预测耗尽65秒余量，后续模型请求被截短/停止，不能承诺任意边界家庭总能完成。原件output/product-d2-forecast-stress.json，单worker旧原件不覆盖。

复现（项目backend目录、不加载密钥、不联网）：

```powershell
$env:PYTHONPATH = 'src'
& .venv/Scripts/python.exe scripts/benchmark_forecast_stress.py
```

### 尚未实现/尚未验证

未实现多专家、自动路由/重规划、SSE、图检查点恢复、真实硬件或公开部署；Figma在线新增状态/连线仍待工具额度。新S1真实DeepSeek场景验证/调优、独立保留集和真人研究未开展。程序/数据库/浏览器结果只证明当前合成环境的工程闭环，不写“模型准确率提高XX%”。下一阶段D3接入专家并行和实际角色反馈，再分别做D4/D5真实评测。
