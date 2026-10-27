# HomeMind 产品 B：实现与验证记录

日期：2026-10-27（Asia/Shanghai）。状态：B 核心代码与旅程已交付，Figma 在线新增交互仍待补。依据 [B 设计](../superpowers/specs/2026-10-27-product-b-design.md)、[PRD](../product/prd.md)。完整真实模型效果评测与用户研究尚未开展。

## 基线与验证分类

开发前后端 153 passed、3 MySQL 条件跳过，前端 30 passed。这里的通过数是程序测试数量，不是自然语言准确率或用户任务完成率。

默认程序测试用明确注入的受控模型，不访问供应商。`scripts/local_config.py` 的测试环境显式关闭真实模型；`scripts/serve_agent_e2e.py --controlled-sqlite` 是独立进程、新建 SQLite 的专用浏览器夹具，使用 `controlled-browser-test` 模型标识，不能作为 MySQL 或真实模型效果证据。正常运行的后端没有受控模型降级路径。

追踪隔离 RED 测试中有一次例外：实施者在尚未添加禁用上下文时显式设 `LANGSMITH_TRACING=true`，LangSmith 尝试将纯 SQLite 合成测试 trace 发往 `api.smith.langchain.com`，返回 401 / missing API key。未使用真实家庭、模型密钥或真实供应商调用，但发生了测试数据外发尝试，不能称全部 RED 测试均无外网。原始记录 `output/product-b-backend-red-tracing.txt` 保留；后续修复和网络拦截验证另记，不覆盖这次失败。

修复已验证：图调用包在真实 `tracing_context(enabled=False)` 内；pytest 自动夹具封锁 httpx 真实传输和 requests 的外部请求。继承追踪环境、取消和超时路径的定向 GREEN 通过，无后台追踪警告。浏览器夹具仅访问本机显式 API，真实模型检查仍单独 opt-in。

## 最小真实模型检查（已执行）

命令：项目根目录 `backend/.venv/Scripts/python.exe scripts/check_model.py --real`（Windows）。默认不带 `--real` 时只报告未运行，不读取模型配置或发请求。授权范围内总共执行两次模型请求，未再次补跑。

本次真实结果：

| 项目 | 实际结果 |
| --- | --- |
| 场景 | 内存合成家庭、同名房间，要求读取事实并澄清 |
| 供应商/返回模型 | DeepSeek 官方 / deepseek-flash |
| 模型/只读工具调用 | 2 / 2 |
| 输出 | 严格契约通过的 clarify |
| 供应商返回用量 | 输入 5539 token，输出 219 token |
| 此轮耗时 | 5641 ms，单次观测，不是 P50/P95 |
| 设备动作 | 0；没有读取用户家庭数据库 |

原始公开结果：`output/product-b-real-model-probe.json`。检查脚本只输出公开摘要，不保存私有推理、Authorization 或供应商原始错误；第三次请求由包装器直接阻断。脚本预算/默认不调用/输出过滤测试原始 RED 与 GREEN 保留为 `output/product-b-probe-*`。

这证明当前密钥/API、实际工具调用、结构化澄清基础能力接通；不证明回家/睡眠/离家/局部动作全场景真实模型效果。DEV01—DEV12 真实模型评测、独立验收集、用户观察和单/多 Agent 对照均未开展，不计算完成率、优势或真实节能。

依据 [DeepSeek 官方 API](https://api-docs.deepseek.com/) 的 Chat Completions 与[非思考参数](https://api-docs.deepseek.com/guides/thinking_mode/)，调用 `thinking.type=disabled`。LangGraph/LangChain 沿用现有锁版本；HTTP 适配器仅处理官方协议，不另引入不必要的供应商集成包。

## MySQL 迁移（已执行）

用户打开 Docker Desktop 后，执行 `python scripts/setup_mysql.py`，脚本检查既有安装标记及容器/卷归属，启动本项目匹配容器并保留数据，应用与独立测试库均迁移至 `0003_m4`。随后真实连接两库检查 ready 和 Alembic 版本，测试库现有 29 条任务为 rule，应用库无既有任务。证据：`output/product-b-migration-proof.json`。没有以新建 SQLite 冒充真实迁移。

## 已完成的后端与持久化检查

后端实现 `e3a59ec` 加窄修 `0bd2387`，覆盖真实图分支、局部/三场景规划、保留/保护、窗户未知/离线、澄清历史、确认、无方案核验守卫、响应丢失独立读回、过期事实、预算/取消、账号边界、普通模式时间门禁与原子推进。上述自然语言场景使用受控模型输出，不能计作真实模型理解通过。

| 检查 | 实际结果 | 证据 |
| --- | --- | --- |
| Agent 定向最终 | 56 passed | `output/product-b-backend-green-light-contradiction.txt` |
| 后端全量最终 | 209 passed，4 个 MySQL 条件跳过，178.25s | `output/product-b-backend-full-light-contradiction.txt` |
| 独立真实 MySQL 最终代码 | 4 passed，4.52s | `output/product-b-mysql-validated.txt` |
| 原有规则真实进程重启 | 两个独立 API 进程前后，会话/配置/环境/归档/偏好/任务动作及幂等一致 | `output/product-b-rule-restart.txt`、`output/product-b-rule-restart-proof.json` |
| 静态/依赖 | Ruff、格式、uv lock、67 个已安装包兼容及离线工具/图检查通过；离线图检查不代表业务检查点恢复 | 工具实际输出及 `output/product-b-backend-ruff.txt` |
| 独立规格与质量 | 规格复核9项通过；质量先复现竞态，修复后8项通过；灯矛盾窄修3项独立复验批准 | 审阅回报；受控 RED/GREEN 留存 |

新 MySQL 项真实保存 waiting_input，独立创建新 Database/App 读回后在同任务回答，检查 mode、问答/运行 JSON、幂等操作与动作记录；创建/回答重放不增加模型调用或动作。这是数据库/程序测试，不是模型质量评测，也不是 LangGraph 检查点恢复。

质量审阅发现锁外幂等查询与锁内受理之间的调度竞态：创建可能唯一键失败（503），回答/确认可能错误409；原始 RED 为5项竞态失败，真实占用对照通过。修复为家庭锁内再次查询和重放，异内容仍冲突；没有以捕获异常或重复执行掩盖问题。证据：`output/product-b-backend-red-quality.txt`、`output/product-b-backend-green-quality.txt`。另去除失败事件虚假的0ms。

灯参数窄修：通用引擎以亮度优先决定电源，模型同时给出power=true/brightness=0会先写再读回失败。仅在Agent全量预校验拒绝该矛盾，合法动作排前也保持整批0写；通用控制/热模型未改，单设亮度0/70继续合法。真实RED与最终56/209项记录保留，早期53/206日志未覆盖。

## React 与浏览器验收

前端提交 `919d831`，沿用已有浅色页面。自然语言/规则明确区分；用户可表达硬保留/保护、在原任务回答、核对实际范围/动作再确认、查看动作读回与目标状态、推进到核验时刻。运行记录/公开问答和用量折叠展示，未配置只提示配置状态，未伪造连接成功或进度。

| 检查 | 实际结果 | 证据 |
| --- | --- | --- |
| 前端最终单测 | 14文件64 passed，49.13s | `output/product-b-frontend-green-delivery.txt` |
| ESLint / TS / Vite | 通过 | `output/product-b-frontend-{lint,build}-delivery.txt` |
| 完整受控 Agent 浏览器 | 10 passed（1.2m）；fresh SQLite + controlled model | `output/product-b-agent-browser-final.txt` |
| 完整规则/账号/家庭浏览器 | 21 passed（2.2m）；真实专用 MySQL | `output/product-b-mysql-browser-first.txt` |
| 最后状态修复后 Agent 关键复验 | 5 passed，32.7s | `output/product-b-agent-browser-delivery.txt` |
| 最后状态修复后规则任务复验 | 6 passed，41.2s | `output/product-b-mysql-browser-delivery.txt` |
| 独立规格 / 质量 | 规格标签5项通过；质量最终4文件31项通过并批准 | 独立审阅回报 |
| 根脚本 | 独立8 passed、Ruff/格式通过，默认模型检查0call | `output/product-b-root-tests.txt`及独立审阅 |

完整10/21在最终读写竞态补丁前通过；补丁后按影响重验5/6，并完成64单测和独立31项复核，未声称最终代码重新整套跑过31项，也不将重复运行计成更多独立场景。GitHub Actions已配置，未运行远端CI或发布。

前端真实发现并修复：503不能证明没提交；已恢复实例的自动GET标记需只消费一次；晚到写/读不能抢用户选中，写代次避免pending空值ABA；核验/推进忙状态跨页保存；旧GET不能覆盖新确认/回答/核验结果，取消旧查询后仍须复查代次。RED/GREEN在`output/product-b-frontend-{quality-races,stale-read,cancel-gap}-*`等原始文件；无证据任务不显示虚构“最近核验”，稀疏空调参数不补undefined温度/默认风速，亮度按实际引擎优先语义展示。

浏览器首轮澄清房名按钮被AntD自动插入汉字空格，影响可访问名称；为对象选项关闭autoInsertSpace，保留首轮8过/2失败及trace在`output/product-b-agent-browser-first-artifacts`。一次Windows npm筛选正则被cmd误解析，未启动服务，改用精确文件行选择；命令错误单独留存，未算产品失败或掩盖成通过。

截图：[桌面确认](../../output/product-b-agent-confirmation.png)、[局部结果](../../output/product-b-agent-local.png)、[360px](../../output/product-b-agent-mobile-360.png)、[390px](../../output/product-b-agent-mobile-390.png)。根代理目视桌面和360px，实施者另查手机；浏览器对360/390进行实际点击与无横向溢出检查。原Figma/M3截图保留，新回归使用product-b前缀。

本机8100在用户打开Docker后由既有容器占用，因此只改本项目忽略的API/Origin/前端代理为8110。测试使用8110/5174与18110/5176，结束后核实均已退出；原8100容器和本项目MySQL保留。没有将测试库或受控模型用于日常产品配置。

## 剩余边界

用户研究、真实模型完整DEV01—DEV12及独立验收集、多Agent对照均未开展。没有多Agent、SSE、后台时钟、用户取消/重规划、图检查点恢复、真实硬件或生产发布。推进跨刷新没有持久幂等，未知结果须先读当前时刻，不能自动补发；C再按真实Bad Case确定最小可靠性增量。

Figma Starter MCP 额度仍受限，本轮不重试或绕过。既有可编辑画稿保留，新增自然语言/澄清/确认/时间引导的在线交互连线与同步尚待补齐；React 的交付状态单独记录。
