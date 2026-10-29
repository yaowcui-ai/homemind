# HomeMind 最终工程与简历交付

日期：2026-10-29。当前用户范围：可演示AI全栈项目、一份单项目简历Markdown、公开源码；不制作AI产品简历或面试问答，不为求职额外扩技术范围。产品PRD/方案/迭代保留。

## 实际验证

| 验证 | 真实结果 | 本机原始日志（忽略目录，不入库） |
| --- | --- | --- |
| 后端完整测试 | 322 passed，7条件skip | output/release-backend-full.txt |
| 独立真实MySQL测试 | 7 passed | output/release-mysql-tests.txt |
| 根脚本最终测试 | 78 passed | output/release-root-final.txt |
| 前端完整测试 | 19文件，93 passed | output/release-frontend-full.txt |
| 前后端静态检查/格式与构建 | Ruff、format、ESLint、TS/Vite通过 | output/release-backend-ruff.txt、release-frontend-lint.txt、release-frontend-build.txt |
| 受控Agent浏览器 | 17 passed，360/390px与异常恢复 | output/release-browser-agent.txt |
| 实际API进程重启 | 会话、配置/环境、归档、偏好、任务/动作与同键重放一致 | output/release-mysql-restart-final.txt、release-restart-proof.json |
| 真实模型新集 | 36运行，98/120请求，余22停止，失败保留 | [D5报告](../product/product-d5-evaluation.md)与公开JSON |

受控浏览器测试覆盖产品交互，不冒充供应商真实推理。真实模型来自独立D5批次。MySQL测试另跑，不能将后端7个skip记成通过。设备与热过程仍为确定性仿真。

公开证据导出固定LF换行，已直接以Git暂存blob重新计算SHA256并确认与汇总一致，避免Windows换行转换造成下载后哈希不符；本机原件哈希仍指向保留的原始字节，不混同公开投影。

本机MySQL容器起初未运行，使用本项目setup_mysql保数据启动，实际迁移和app/test检查通过；不判断退出原因。重启验证的固定18100端口被既有进程占用，原失败`output/release-mysql-restart.txt`保留，没有杀该进程。验证副本仅替换端口为18130、日志名前缀为release，其余重启流程不变，真实启动并停止两次本轮创建的API进程。未修改应用数据库恢复机制以迁就测试。

## 云端检查与修复

源码正常上传到 [yaowcui-ai/homemind](https://github.com/yaowcui-ai/homemind)，公开仓库，无强推覆盖其他仓库。Git历史和当前待发布文件扫描密钥、本机配置及账号库，未发现匹配；`.env`、`.local`、output、虚拟环境和数据库不入库。CI临时凭证只用于隔离服务，非本机凭证。

首次[CI运行](https://github.com/yaowcui-ai/homemind/actions/runs/40865502013)在干净检出时发现`verify_m3.py`依赖已有output目录。补日志目录初始化，回归先RED后GREEN；修复提交`d6caf15`的[CI运行](https://github.com/yaowcui-ai/homemind/actions/runs/40866913208)已全绿：后端329项（含真实MySQL）、根脚本78项、API实际进程重启、前端93项/检查/构建、规则浏览器21项和受控Agent浏览器17项。云端CI不调用付费模型。链接记录该次实际运行，不预言后续提交状态。

## 使用与边界

云端增量复验：`1074c2d`整套通过，`9c13ac7`在360px即时宽度断言出现425px，受控Agent浏览器16过1失败。本机3次普通与5次CPU降速未复现同一溢出（降速另有2次后续刷新断言超时，不混为同一错误）。[云端8次诊断](https://github.com/yaowcui-ai/homemind/actions/runs/40871036093)实际6过2失败，两次均记录`measuredWidth=425`、`settledWidth=360`、`overflow=[]`：视口切换后即时读取了过渡尺寸，随后布局恢复，未发现持续溢出。原失败和诊断日志保存在output/release-cloud-9c13ac7-failed.txt与release-cloud-width-diagnostic.txt。

最小修复仅将该断言改为最多2秒的布局轮询，仍要求scrollWidth不超过viewport，持续溢出仍失败；不是重跑测试或模型任务。应用CSS、功能、D5冻结源码/评分均不变。本机同案例8/8通过（output/release-width-fixed-eight.txt），ESLint通过；云端结果以随后实际运行记录为准。临时8次定位步骤已撤下，CI跳过纯Markdown提交，避免每次补文档重复运行应用全套测试；源码、工作流和评测数据变动仍触发检查。

按[README](../../README.md)从公开仓库获取，安装锁定依赖，打开Docker Desktop，再启动MySQL→API→网页。已保留vite缺失、依赖安装警告和数据库503排查步骤；模型密钥只放本项目backend/.env，公开源码不含密钥。README核心演示路径是规则与温控预测/确认/推进/核验，模型输出可能失败，失败状态有真实说明。

唯一求职交付：[AI全栈项目描述](../resume/homemind-ai-fullstack.md)。不承诺简历通过筛选或面试结果。

未完成：[Figma新增状态与可点击连线](figma-final.md)因工具配额受阻，本轮无画布更新；已有React界面不受影响。无真实硬件、公开应用部署、自动路由、SSE、图恢复或真人调研成果。新集M未证明优势，不把多Agent数量当作性能收益。
