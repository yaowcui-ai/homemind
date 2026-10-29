# HomeMind 当前接续

更新日期：2026-10-29（Asia/Shanghai）。

## 当前授权与进度

**D4遗留定位/定向复测进行中。** 用户2026-10-29“开始，并先介绍进度与简历前缺项”授权本阶段，随后明确最多24新真实请求。分支codex/product-d4-followup，基线2b33557。新固定output/product-d4-followup-20261029/budget.json共享24，仅DD01/expert、DD05/single、DD06/expert首次诊断+必要修复后各一次；旧余3/C2余2不转用。脚本scripts/product_eval_d4_followup.py，原始D4精确模板只读复用，默认不加载配置/不联网。

已完成有限records诊断：schema白名单字段+静态错误类别（最多3条），专家role/引用/候选错误和selection静态字段漂移；不存raw/未知字段/非法ID，不放宽解析/执行。8项诊断RED/GREEN、4项新入口测试通过；相关后端161passed/91.22s、根脚本55passed/29.73s，Ruff过。审阅指出repair不能续跑，已修同源码/模型/目标resume，已发无记录仍拒绝重放，复审批准。真实调用即将开始，先读新账本/原件，不重复--real创建或删目录绕额。旧失败确切字段仍未知，不能用新诊断反推。

简历交付剩余：[最小清单](docs/product/resume-delivery-checklist.md)。必要顺序为遗留定位/开发复测→稳定候选与独立新集→E核心Figma流程/演示/启动/双方向简历面试材料；已有PRD/AI方案/迭代不重写，硬件/SSE/自动路由/公开部署非简历前必要项。当前阶段不要提前做D5/E或新增无关页面。

## D4首轮历史（本轮以上方为准）

**D4首轮真实对照与一次定向调优已交付（2026-10-29），遗留待修。** 用户“开始下一步，注意目标、不必要步骤”授权D4，随后明确最多40次真实请求。分支codex/product-d4-evaluation，基线74cec0f；工具/6例在80b95c7冻结。[真实报告](docs/product/product-d4-evaluation.md)、[逐例数据与哈希](evaluation/results/product-d4-20261029.json)。共用固定output/product-d4-real-20261029/budget.json，实际37（首次29+复测8），余3停止，不能自动转用；C2余2同样不能用。6例×S1/M是E端到端开发集，DD04不可行/DD06未知读数仅首轮，无补答恢复/P层/独立集。

首次原评分S1 3/6、M2/6；审计后S1 4/6、M3/6，不能把勘误增分称模型提升。精确SQLite备份同ID/世界/初态、AB/BA，金标只在评分侧，合法偏好次优照原选执行。DD05/M因cover_constraint keep与keep列表冗余表示被评分门禁误挡，原task/原Plan/4次调用不变，在禁用模型app续确认/推进成功，550Wh，账本字节不变；总elapsed_ms=null不假造连续耗时。DD06/S1准确要求恢复窗户读数，开发助手逐字复核并绑定问题SHA，非独立人工研究。原件phase1不覆盖，另存audit-v2与semantic-reviews.json。

唯一应用改动：graph.py对S1/M最终选择共同明确字典序排序与精确比较，不修改候选/校验/物理/standard。DD02/S1原选c1=550.050Wh（温度已达标但偏好次优）；同初态/输入各复测一次，S1 3请求、M5请求均选c2并实测550.000Wh。M首次model_unavailable恢复不能归因prompt，S1一次复测也非总体提升。其余真实DD01/M invalid_advice、DD05/S1 goal_drift、DD06/M invalid_output未修；被拒raw/字段未保存，不能猜具体失败字段。已知36响应输入185047/输出7068token，1次请求用量未知，不估精确费用。M未证优势，标准仍默认、S1保留、M显式实验。

最终相关后端132passed/73.12s，根脚本51passed/27.84s（包含D4新18项），Ruff/format：后端57文件与4评测文件过。独立评分审阅及审计/提示增量复审通过。无前端/依赖/迁移/物理改动，不声称本轮全量后端/浏览器/真实MySQL重跑。原始RED、首次根目录Ruff导入分组误判和审计长行失败保留，正确目录/长行修后过，未批量改旧tests。无新常驻服务，不修改日常家庭，仅合成SQLite；启动不变，重启后端可应用提示。

**下一次继续：先清D4遗留三类真实失败，再D5。** 优先复用现有记录补有限字段诊断（不保存raw/非法ID、不增加无关UI/DB），用受控复现定位后有证据地改单因素；再另列最小真实开发批次申请，不用余3或C2余量。可以先离线改进，不为显示调优而盲改prompt。稳定候选后再冻结独立新集，现44旧例+DD01—06都是开发数据。D5/M9、完整M5自动路由/旧多场景、Figma新增在线状态/连线、真人研究、硬件/部署仍未完成。当前阶段交付后停止，不自动扩大范围。

## D3交付历史（D4以上方为准）

**D3多Agent全栈已实现并完成本轮验收。** 用户2026-10-29“继续下一步/继续”按D1设计授权D3，分支codex/product-d3-experts，基线5c61fb3。[计划](docs/superpowers/plans/2026-10-29-product-d3-experts.md)、[实际报告](docs/verification/product-d3-experts.md)、[结果与哈希](evaluation/results/product-d3-20261029.json)。本轮无新依赖/迁移/真实模型请求，不使用C2余2；应用版本仍0.4.0，仅本地提交，不推送/合并/发布。

已实现：expert_forecast→multi_agent；Goal/精确预测后真实LangGraph comfort/energy并行节点+join，再协调选择，同S1资料/硬约束。严格Advice引用goal或candidate:<id>，无效Advice整轮analysis_incomplete，0动作且无raw/非法ID。共享原子6次/轮12次/任务，预算拒绝0请求；peer取消后等待结算。role_runs本轮4槽固定coordinator_goal/comfort/energy/coordinator_plan，rounds.roles仅存当轮指标无旧Advice；0请求补答不抹已有已知usage。M重放/补答/确认/verify零动作保护、混合历史已扩。确认事务save=False，实际execute后同事务显式save_engine，失败不物理回写。

React已支持3策略与multi实际标签、意见分歧/原选、M补答和确认刷新保原key；本轮状态/意见可见，阶段模型/调用/Token折叠。新增roles parser严格绑定失败/执行状态、历史指标与唯一连续turn，空记录仅合法planning或未启动取消且当前字段全空，已用实际RED修反例；非实时SSE。独立后端/前端规格及质量审阅均通过，折叠调用记录后的完整browser也已复验。

最终实际：根完整后端311passed/7 MySQL条件skip（231.32s，output/product-d3-backend-root-final.txt）；另专用真实MySQL7passed/12.06s，包含同户rule/standard/S1/M混合历史、新Database连接逐detail读回、M确认原键重放和实际推进，不是OS进程重启。最初MySQL7项因13306拒绝全setup error，原件output/product-d3-mysql-not-running.txt保留；本项目容器Exited137，setup_mysql保数据启动恢复，不推断退出原因。前端19文件93passed/208.32s（沿用单worker/15秒），lint/TS/Vite通过，测试误用getByRole exact选项已修。受控browser完整17passed/约2.1m，新增3例覆盖分歧确认执行核验刷新、非法证据0动作/verify保护、未知补答原键恢复；后者仅到待确认，不冒称执行。根目视1440/360/390px及展开记录/失败截图。根脚本33passed/25.74s；全部后端56文件、browser脚本ruff/format过。

**下一次继续：D4真实开发评测与调优。** 先细化开发小批执行器/评分/记录与配置预检，再另列最小S1/M真实请求范围和预算申请，未获授权前只做离线准备，不调用模型；建议72只是旧计划未授权上界，C2余2不可转用。保留首次失败、按理解/工具/协调/执行/评分定位，单变量修复及同条件复测；D5新集另冻结/另授权。44旧案例全部开发集，无真实多Agent优势结论。D3原始RED/失败不覆盖（取消测试sleep(0)猜完成失败改明确Event，不冒充真实丢账修复）。Figma在线新增状态/连线仍待额度，无硬件/第三方研究；完整旧M5自动路由/多场景和M9不勾完成。本轮临时18110/5176服务已退出、MySQL保留，实际启动仍README Docker→setup_mysql→API8110/网页5174。

## D2交付历史（最新D3以上方为准）

**最新为D2全栈交付（用户本轮“继续推进ai全栈”授权）。** 分支`codex/product-d2-forecast`，基线00e031e；应用仍0.4.0/M4，无新依赖/迁移，真实模型0请求。按[D2计划](docs/superpowers/plans/2026-10-28-product-d2-forecast.md)实现single_forecast和轻量React入口；[实际验证](docs/verification/product-d2-forecast.md)、[可移植结果/哈希](evaluation/results/product-d2-20261028.json)。专家/multi_agent留D3；仅本地提交，不推送/合并/发布。

当前已实现：严格GoalContract→精确隔离forecast→Selection/Plan绑定→必要确认→既有执行/独立核验。≤4候选low/auto×帘0/100，keep固定原位置；目标室恰好1空调/≤1帘，全部物理感知可观测。16房/256实体含归档/256归档/5760步上限；线程槽等实际worker结束归还，取消/截止分块检查。实验每轮6/任务12请求，标准3/轮不变；strategy standard省略新hash字段，旧请求/刷新原键兼容。Task.mode仍single_agent，agent_run新增版本化goal/forecast/选择/偏好标志，不存被拒raw/非法ID。预测规划事务save=False只保存Task，不写物理表。

React已做实验选择/候选卡/偏好次优提示、预测与实测区分、不可预测恢复说明；API解析绑定请求/本轮快照/目标/作用域/完整原选动作（含room_id）。独立前端/后端规格和质量均批准。已修实际RED：同名goal猜测、实验plan_round仍save_engine、最终Plan失败却先存selected、前端候选/原选room引用缺口；旧RED保留output。

最终：后端完整275passed/6 MySQL条件skip（145.24s），另实际专用MySQL6passed/11.70s含D2新JSON新连接/确认原键/推进（不是OS进程重启）；前端显式单worker/15秒预算84passed/158.23s、lint/TS/Vite过；受控模型browser全Agent14passed（约1.5m）含D2和移动/恢复，root目视桌面/360px截图、360/390几何过；根脚本33passed/11.37s、后端15文件和browser脚本ruff/format过。初后端272/6skip、定向37/39及前端默认5秒82过2超时/串行83过1超时均留历史，不覆盖或称修复线上竞态。最终原件output/product-d2-{backend-final,mysql,frontend-full-15s,browser-final,root-scripts}.txt。

边界压力原件output/product-d2-forecast-stress.json：16房/256实体/每worker5760步，混合启用单worker20076ms/lag41.77ms；双worker35603/35599ms、lag174.523ms；244真实归档6892ms/lag40.897ms；全部源不变。进程工作集约36.2→41.1MB含Python/库，不是纯算法内存。之前单worker关闭灯负载27728ms/lag66.546ms在并发pytest条件下，不能互算性能提升或称普遍最坏保证。

**下一次继续：进入D3专家并行/协调及实际角色反馈，先写细化实施计划，复用S1预测与React候选卡。** 扩multi_agent时必须覆盖check_creation_replay/check_turn、verify/TaskDetail零动作保护、混合历史与session恢复；D1指出的这些兼容项不能漏。按已定Advice/预算/65秒/失败零写设计，不引入队列/向量库/SSE等无关模块。D4/D5真实调优/新验收仍未做，真实请求另授权，C2余2禁止转用。Figma在线新状态/连线待额度，44例全开发集，无访谈/真实硬件/多Agent收益。Docker本轮在已安装路径隐藏启动，setup_mysql成功；受控browser临时API/网页已退出，MySQL保留。启动仍README8110/5174。

## D1设计交付历史（最新D2以上方为准）

**最新为D1设计交付，以下C2/C1/B是历史。** 用户要求同时面向AI全栈和AI产品、评测调优不能少；“继续”延续本轮D1。当前分支`codex/product-d1-design`，基于C2 e95e0be；应用仍0.4.0/M4、迁移仍0004_product_c。本轮无业务代码/依赖/迁移更改、0真实模型请求，无新常驻服务，只本地保存不推送/合并/发布。

交付：[D1全栈规格](docs/superpowers/specs/2026-10-28-product-d1-design.md)、[分步交付与需求映射](docs/product/product-d-delivery-plan.md)、[评测调优契约](docs/product/product-d-evaluation-design.md)、[核对记录](docs/verification/product-d1-design.md)。主对照S1为增强单Agent，同样获得预测资料；实验M为舒适/节能并行建议+协调，所有角色只读、程序统一执行/独立核验。当前三角色/预测工具都未实现；有限候选最优不能包装成多Agent必要性。

现有引擎离线4重放：20min低风26.8/auto26.0；60min均26.0，低风550.050Wh/auto850.050Wh，首次达标41/17分钟。只针对默认初态、帘合/其他负载off的仿真；新复现脚本与原JSON一致，[证据](evaluation/results/product-d1-tradeoff-20261028.json)。不能外推真实节电、用户收益或多Agent效果。

独立技术/方法审阅通过仅限设计，重点补入：verify/TaskDetail零动作multi保护，创建重放/回合兼容，完整物理输入/多空调窗帘边界、CPU/线程取消与实际worker结束才释放并发槽。S1/M共享原文/GoalContract/预测，不能程序偷换模型原选；固定能耗scope、初态达标0、等价解。D1口径冻结，候选实现和新验收样本还未冻结。

**下一次继续：D2隔离预测+增强S1，先写具体实施计划/关键业务RED，再实现；不一口气做D3—D5。** 上限16房间/256实体（含归档）/4候选5760步需实测，不是已实现承诺。D3做专家+React/JSON持久化/旧历史；D4实际开发调优，D5新集验收/重复。44例仍全为开发集；无独立集/真人研究/多Agent收益/硬件。Figma在线新状态连线继续待额度，不重试绕过。

当前没有D真实请求授权。预算文档的开发72硬止资金池、正式12×2×12=288和重复3×2×2×12=144均是未来建议上界（合504），不能自动发请求或承诺用满。使用前另列最小批次并获授权；C2余2已停止、C1额度用满，均不可转用。启动仍README的Docker→setup_mysql→API8110/网页5174。

## C第二轮历史（最新D1以上方为准）

**最新为C第二轮交付，以下C首轮/B是历史。** 用户“开始”授权C遗留P1清理，另明确本轮最多32真实请求。当前分支`codex/product-c2-stabilization`，版本仍0.4.0/M4，head迁移仍0004_product_c；无新依赖/迁移，仅本地提交，未推送/合并/发布。[C2报告](docs/product/product-c2-evaluation.md)、[44例案例库](docs/product/product-c-cases.md)。

C2实现有限agent_run.diagnostic（阶段/输出类型/code/path/引用类型/当前家庭可定位），不存无效ID、被拒问题/label/raw输出，不查询别家庭；校验与执行安全不放宽。页面首屏解释无效引用/读数缺口/重复选项和下一步，诊断折叠、旧task兼容。重复(kind,id)拒绝为duplicate_option；互斥硬要求问用户放宽哪条，非对象取舍用options=[]+自由回答。

真实C2阶段1：原C14/C06/C09/C12完全原样+新8例C37—44，共12例、24请求；原判9/12，但C06是oracle假设缺陷，另2个实际交互问题C12(refused)与C40(同一实际灯的重复选项)。阶段2仅C12/C40同输入/预期/归一化初始事实各复测一次，均过：C12只证明waiting_input/空options/零动作，C40实际回答后原task关指定灯、读回成功。共30/32请求，余2未用，已停止，不自动使用余额。输入90755/output3055 token，无费用估算。

重要勘误：C06未限定fan，合法auto在20min读26.0且deadline verified；受控API和独立物理重放仅改fan得到low26.8/auto26.0。热模型/成功定义/冻结案例及原评分都没改；旧C1“可达10/12”分母解释撤销，历史全部执行目标10/13保留。C2不能把9/12直接称为产品失败率，更不能用定向2/2推整体准确率提升。

C14本次正确拒绝未知窗户，没复现not_found；旧输出丢失，仍不能追认具体原因。受控API证明非法clarify选项可定位$.options[0].id，但不当作旧故障证据。C40阶段1未提交回答而rawsame_task_after_reply=True仅因ID不变，现加reply_submitted门控，旧原件不覆盖。C42首次处置通过，但后续回答未测且问句措辞待改善；保留P2。

证据`output/product-c2-real-20261028/{phase1,phase2}`、30次budget、风速对照、受控错误复现；可移植`evaluation/results/product-c2-20261028.json`。旧40账本SHA核对未动。本轮模型只用临时SQLite合成家庭；实际MySQL原5项回归5passed（不冒充新字段独立进程重启）。后端相关77passed、前端首阶段全74passed/末次定向26+lintbuild、受控browser新增1passed，root目视截图；独立规格/质量及数据方法审阅批准。原始RED/GREEN全保留。无新常驻API/网页，MySQL保留；启动仍README8110/5174。

**下一次继续：可进入D的最小分工与公平对照设计，先冻结风速等控制参数、指标与新样本，再执行。** 44案例全是开发集，不可作保留集；没有用户访谈/上线数据/多Agent收益。模型新批次另定范围预算，不自动使用C2余额。既有Figma在线新状态/连线仍待额度，不绕过/重建文件；U01仅本人自述少量设备偶用。本轮不自动做D/E。

## C首轮历史（最新C2以上方为准）

用户“继续，注意这次我要往产品稍微靠一下，所以案例应多点”授权C首轮；另明确允许最多40次真实请求。已完成[36案例](docs/product/product-c-cases.md)、[C评测与Bad Case报告](docs/product/product-c-evaluation.md)、推进持久恢复、busy保原键、范围prompt及失败反馈的有限优化。保留原架构，版本仍0.4.0/M4。分支`codex/product-c-validation`，仅本地提交，不推送/合并/发布。

真实首批C01—18在新建临时SQLite合成家庭运行，真实DeepSeek/实际API和图，设备/时间仿真；初批38请求，13/18符合验收，C04/C06/C09范围/保留冲突、C12拒绝代澄清、C14未知窗户not_found共5失败。优化后原输入/初始条件/期望的C04一次复测通过，另2请求。**共40/40已用满，不能再调用真实模型；不能换目录/删账本/重跑旧check_model绕过预算。** C06/C09/C12/C14尚未真实复测，不称全部已解决，不将C04一次通过外推总体提升。实际输入115313/output6030 token；无费用推算、用户研究或单多Agent对照。

证据：`output/product-c-real-20261028`原baseline/18案例/C04-r2/manifest/40次budget均保留；审阅修评分ID集合与C11固定分母后另存scores-v2，原评分不覆盖，汇总不变。可移植摘要`evaluation/results/product-c-20261028.json`有源码及原件hash，不能将受控程序通过数转为模型准确率。默认`scripts/product_eval.py`只列案例不加载密钥/联网；显式真实入口固定本次授权账本，耗尽停止。

推进新契约：POST body世界ID+预期当前分钟+Idempotency-Key，nullable Task.advance_records+0004_product_c；同键同体返回原证据、不推进，异键旧时刻409；记录/时钟同事务，reset后原键历史只读。React sessionStorage冻结advance，刷新GET按key/body记录确认，未决可原键重试；home_busy保键。legacy空体无key仍兼容且无此保护。没有取消在途/后台时钟/自动重规划/图恢复。

检查：后端完整214passed/4当时MySQL skip；收集后只新增测试，最终推进6passed；prompt后Agent图/API56passed。真实MySQL迁移后5passed（含0004新连接和reset原键）。前端完整66passed，随后busy修复25项、反馈18项定向过，lint/TS/Vite过；新增受控browser2项过，root目视推进截图。独立规格及质量审阅批准，home_busy与评分原始RED留存。未再次声称全量浏览器重跑。

本轮Docker最初未运行，用户再次回复启动后，`setup_mysql.py`保留数据将本项目app/test迁0004。API本地8110、网页5174；受控18110/5176验收进程已退出，MySQL保留。8100其他项目容器不停止/接管。完整启动见README，先Docker→setup_mysql→API→前端；密钥不打印/提交/复制前端。

**下一次继续：先清理C遗留P1并稳定单Agent基线，再进入D的按需多Agent/公平对照。** 首选定位C14（现公开记录未保存被拒计划，不能推断具体引用）、复测C06/C09/C12/C14及更多改写。新请求先明确新预算；36例均为开发集，正式保留集须另建冻结。Figma在线新增状态/连线仍受额度未补，未重试或绕过；第三方观察仍无，U01仅本人自述“有少量设备，偶尔使用”。本轮不自动做D/E。

## B交付历史（以下保留当时事实，最新状态以上方C为准）

**当时委托：用户在 A 交付后“继续下一步”，授权产品 B；核心代码与旅程已实现、验证并交付。** 方案：[B 设计](docs/superpowers/specs/2026-10-27-product-b-design.md)、[计划](docs/superpowers/plans/2026-10-27-product-b-single-agent.md)、[验证记录](docs/verification/product-b-single-agent.md)。

B 最终：后端209passed/4 MySQL条件skip，Agent56passed；真实MySQL最新4passed/4.52s；前端64passed，lint/TS/Vite通过。完整受控Agent浏览器10项、真实MySQL原21项通过；最后状态竞态修复后又定向复验Agent关键5项、规则任务6项通过。root已目视桌面与360px截图，360/390px几何/点击均过。独立后端规格/质量、前端规格/质量、根脚本审阅均批准。selectionVersion/writeEpoch、一次性restore、controller跨页忙锁、exact cancelQueries和取消await后代次复查均有真实RED/GREEN，不再有已知未修复质量阻塞。

**本轮真实模型两次预算已用完且通过，不再补跑真实调用。** 仅合成家庭2模型/2只读工具→严格clarify，5539输入/219输出token，5641ms、0设备动作。不是完整真实场景或模型准确率。追踪RED曾向LangSmith尝试发合成trace、401，已明确关闭追踪并封默认测试HTTP；原始失败必须保留，详见B验证。

工程历史：M3 与 Figma 浅色改版/React 同步此前完成；M4现已按产品B对齐PRD实现。用户已批准“按此方向同步，代码中修复排版”。现在执行 A—E 产品路线，不机械顺排所有旧技术模块。

本目录为独立 Git 仓库，当前分支 `codex/product-b-single-agent`：A 31604e3、B设计7655943、后端e3a59ec、灯预校验0bd2387、前端919d831；根脚本/CI/材料一并本地保存。不推送、合并或发布。父仓库通过 `.git/info/exclude` 忽略本目录，旧项目未提交改动不纳入提交。

## B 新实现

- v0.4.0/M4；迁移0003_m4增加mode/agent_run，旧任务rule。API仍单执行进程，LangGraph控制模型/工具/严格解析，服务短事务校验执行，模型时不持家庭锁。
- DeepSeek只读read_home/read_preferences、严格plan/clarify/refuse；当前只有一个规划Agent。每轮3模型/6工具、单20秒/轮65秒、输出2048token；最多3回答。保留/保护、归属、能力、窗户、重复/矛盾动作、版本过期全量检查后才执行；全屋/影响较大必要确认。
- 同task回答/确认、每轮幂等与锁内二查；取消/超时保留已发调用数与未知用量；公开问答/计划/分阶段耗时，关闭LangSmith继承追踪。复用executor独立读回，不把响应成功当目标成功。
- React任务助手自然语言/规则两入口；家庭sessionStorage保存草稿、选中及创建/回答/确认冻结body/key。刷新只读恢复；5xx保原键；晚到读/写不抢用户选择或倒退状态。
- 任务内到deadline原子推进/核验，sleep每次明确10仿真分钟；仅debug启用。普通模式阻止未来homecoming/会等待sleep，local/away可用。推进没有跨刷新持久幂等，未知结果先读当前时刻，不自动补发；这是C可靠性后续项。

## M3 工程基线（历史，B 新实现见上方与验证记录）

- Python 3.12.14 / uv；Node 24.14.1 / npm 11.11.0。版本 0.3.0、stage=M3，依赖锁已更新。
- 独立 MySQL Compose 项目 `homemind`，服务 mysql、卷 homemind_mysql_data、127.0.0.1:13306。实际 MySQL 8.4.11，app/test 分库分账号；容器/卷安装标签、镜像摘要与身份保存在 `.local/`。
- 随机凭据只在忽略的 `.local/mysql.env` 与 `backend/.env`；不可打印、提交或复制到前端，不读取旧项目密钥。Compose 显式项目环境覆盖父终端遗留值，同名资源或安装标记不匹配时拒绝接管。
- 关系表保存用户、会话、家庭、房间、实体/归档/物理状态、偏好、任务、动作与事件。迁移 `0001_m3` → `0002_m3`；后者仅将任务幂等键列明确二进制排序。应用无内存/SQLite 降级，测试 SQLite 仅显式注入。
- Cookie/Argon2id/CSRF/Origin；注册一次模板，每账号一独立家庭。全部业务、调试和任务引用限定认证 home_id；退出撤销会话。
- 保留 M2 可配置两房十二实体、控制/感知分开、Decimal 分钟热模型与能耗、故障/延迟、归档、主读数未知与保留配置的 reset。全部状态通过家庭事务重建/保存；登录或重启不播种已移除设备。
- 规则基线三个模板：homecoming/sleep/away，按配置发现实体，遵守保留/保护、窗口/主读数质量，统一绝对动作与独立核验；按家庭幂等及执行占用。任务/动作/初始偏好和快照持久保存。
- 回家目标要求恰好目标分钟的显式核验证据，首次证据不可覆盖；没有该时刻证据时不以晚达标冒充按时完成。成功历史 verify 为只读重放，其他部分/失败条件可继续核验但不重发动作。
- 网页含注册登录/退出、家庭配置、规则表单/结果、偏好。查询按 home_id 分键，代次丢弃迟到响应；标签页通知及焦点/pageshow 重新核对。核对期间页面、弹窗和浮层都 hidden/inert；同账号保留草稿和未知提交键，不同账号清缓存并重挂载。
- 用户批准的 Figma 浅色视觉已同步 React：白色 224px 侧栏、按视图标题、蓝灰主题变量、传感/可控实体分组与类型图标、明确草稿/应用操作、流式时钟控件、任务双栏、偏好说明和桌面登录双栏。360/390px 手机布局与注册已真实检查；没有修改 API、鉴权、幂等、依赖或业务数据库结构。
- 调试开关默认 false；本项目本地初始化显式 true，开启模拟事件/故障/时间推进/reset。生产普通配置/读取/控制仍鉴权，Cookie Secure。

## M3 与 Figma 历史验证

- 根代理独立最终后端：153 passed、3 MySQL-gated skips；前端 30 passed；真实浏览器最终 21 passed。
- 独立测试库实际 MySQL：3 passed；两个真实 API 进程前后比较会话、完整环境/配置、归档、偏好、任务/动作及幂等重放，一致；证据 `output/m3-restart-proof.json`。
- 根资源防护 3 passed；后端 Ruff/格式 36 文件、根脚本 6 文件、前端 ESLint/TypeScript/Vite 通过；uv 锁/67 包兼容、离线工具/图/适配器/RSA 检查通过。
- 后端规格/质量与前端/根脚本规格/质量分别独立只读审阅，问题修复后复核批准。保留冷认证依赖缺项、deadline、大小写、历史、重试键、跨标签、焦点、portal 等原始 red/green 记录。
- 桌面/手机、登录、任务结果和任务手机表单截图在 `output/m3-*.png`，已目视检查。旧 M1/M2 证据继续保留。
- CI 已配置专属 MySQL、迁移、后端/脚本/浏览器检查；本轮未发布或运行远端 CI。
- 本次界面同步：30 前端单测、ESLint、TypeScript/Vite 构建通过；21 真实浏览器回归通过。额外 2 项视觉检查覆盖各页截图及 360/390px 溢出/开关/时钟边界/手机注册；注册切换的过渡截图另做稳定样式确认，定向 1 项通过。独立规格与代码质量审阅均批准。证据、原始失败和截图在 `output/figma-sync-*`，旧 `m3-*` 保留。

## 启动与服务状态

完整步骤见 [README](README.md)。B本轮用户自行打开Docker后，`python scripts/setup_mysql.py`已保留数据迁移应用/测试库到0003_m4。已有容器N-Tester-backend占8100（不停止或接管），本项目忽略的backend/.env API端口、允许Origin及frontend/.env代理已配套改8110；网页5174。代码默认端口仍8100。普通MySQL浏览器指定HOMEMIND_E2E_API_PORT=8110；受控Agent独立夹具18110/5176、显式fresh SQLite，不是MySQL或真实模型证据。

验收临时8110/5174、18110/5176、18100进程均已退出；MySQL保留运行/数据。8100既有容器继续运行，勿接管或停止。

M3阶段历史：当时启动Docker引擎触发既有容器按原策略自动恢复，环境副作用已记录。本次B由用户自行打开引擎，助手只启动匹配安装标记的HomeMind MySQL并解决本项目端口冲突。

## B交付时记录的下一步（现已启动并交付C首轮）

下一阶段 **C：体验与可靠性**，由用户发起后基于B的真实Bad Case与现有已知限制细化；优先验证真实模型场景表现/失败解释、推进未知结果恢复、任务中断反馈与必要确认/取消等最小需求，不自动铺开全部旧M6/M7模块。Figma新状态/连线仍待额度可用后在既有文件补齐。访谈和完整模型对照仍未开展，不能伪造；真实调用需先明确数量/预算和可核验条件。

用户补充使用背景 U01：“有少量设备，偶尔使用”。仅本人自述，未获知平台/类型，不算第三方访谈或需求验证。当前研究与真实 AI 评测均未开展，验证计划 DEV01—DEV12 为开发场景草案，保留集尚未准备/冻结。

用户已选择 **DeepSeek 官方 API**；默认 `deepseek-flash`、`https://api.deepseek.com`、非思考模式。本轮已在本项目backend/.env把用户API_KEY适配为HOMEMIND_MODEL_API_KEY并启用模型；未输出密钥、不读取旧项目密钥。基础真实接入已按上方两次合成调用通过，完整效果评测未做。此前Vite/原生依赖修复与首次/日常启动步骤保留在README。

已完成 [Figma 改版与同步](docs/superpowers/specs/2026-10-27-figma-redesign-brief.md)。插件已安装且账号连接成功，已创建 [HomeMind 设计](https://www.figma.com/design/Bo7Jqfnh4NNRQiMwNvXc2O)：5 个桌面、5 个手机主页面、手机注册、十种状态板、基础变量与设备组件，均为可编辑图层。用户已批准后实际修改 12 个前端源文件，并完成上述检查。详见 [设计记录](docs/verification/figma-redesign.md)。

Figma 灯卡开关宽度、手机时钟高度及非空房间删除禁用样式仍待回写；三次修正被 Starter MCP 额度拒绝，whoami 已核实方案，不重复写入或绕过限额。**React 中这些问题已修复/保留正确禁用，并实际验证**。这是用户批准的差异，不影响网页同步交付。Figma 文件、sessionId、节点和详细审计在 `output/figma-design-progress.json`，后续补稿复用会话，勿新建重复文件。临时验收 API/Vite 已由 Playwright 退出，本项目 MySQL 保留；没有启动常驻网页/API。

B已接入单规划Agent；多Agent、SSE、后台时钟、用户取消/自动重规划、图检查点恢复及真实硬件仍未实现，不用纯仿真事务冒充外部设备exactly-once。

入口：[路线](docs/homemind-development-roadmap.md)、[PRD](docs/product/prd.md)、[B设计](docs/superpowers/specs/2026-10-27-product-b-design.md)、[B计划](docs/superpowers/plans/2026-10-27-product-b-single-agent.md)、[B验证](docs/verification/product-b-single-agent.md)。M3历史资料从相应记录追溯。
