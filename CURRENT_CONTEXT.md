# HomeMind 当前接续

更新日期：2026-10-27（Asia/Shanghai）。

## 当前授权与进度

用户按阶段授权；最新“现在继续下一步”授权 M4。**M3 已完成，M4 细化设计已写，待用户审阅后实现**。助手负责阶段内实现、必要检查和修复，不自动推进 M5。

本目录为独立 Git 仓库，分支 `codex/m3-accounts-persistence`，基线 M2 提交 `8ad99fd`。父仓库通过 `.git/info/exclude` 忽略本目录，旧项目未提交改动不纳入提交。

## 当前实现

- Python 3.12.14 / uv；Node 24.14.1 / npm 11.11.0。版本 0.3.0、stage=M3，依赖锁已更新。
- 独立 MySQL Compose 项目 `homemind`，服务 mysql、卷 homemind_mysql_data、127.0.0.1:13306。实际 MySQL 8.4.11，app/test 分库分账号；容器/卷安装标签、镜像摘要与身份保存在 `.local/`。
- 随机凭据只在忽略的 `.local/mysql.env` 与 `backend/.env`；不可打印、提交或复制到前端，不读取旧项目密钥。Compose 显式项目环境覆盖父终端遗留值，同名资源或安装标记不匹配时拒绝接管。
- 关系表保存用户、会话、家庭、房间、实体/归档/物理状态、偏好、任务、动作与事件。迁移 `0001_m3` → `0002_m3`；后者仅将任务幂等键列明确二进制排序。应用无内存/SQLite 降级，测试 SQLite 仅显式注入。
- Cookie/Argon2id/CSRF/Origin；注册一次模板，每账号一独立家庭。全部业务、调试和任务引用限定认证 home_id；退出撤销会话。
- 保留 M2 可配置两房十二实体、控制/感知分开、Decimal 分钟热模型与能耗、故障/延迟、归档、主读数未知与保留配置的 reset。全部状态通过家庭事务重建/保存；登录或重启不播种已移除设备。
- 规则基线三个模板：homecoming/sleep/away，按配置发现实体，遵守保留/保护、窗口/主读数质量，统一绝对动作与独立核验；按家庭幂等及执行占用。任务/动作/初始偏好和快照持久保存。
- 回家目标要求恰好目标分钟的显式核验证据，首次证据不可覆盖；没有该时刻证据时不以晚达标冒充按时完成。成功历史 verify 为只读重放，其他部分/失败条件可继续核验但不重发动作。
- 网页含注册登录/退出、家庭配置、规则表单/结果、偏好。查询按 home_id 分键，代次丢弃迟到响应；标签页通知及焦点/pageshow 重新核对。核对期间页面、弹窗和浮层都 hidden/inert；同账号保留草稿和未知提交键，不同账号清缓存并重挂载。
- 调试开关默认 false；本项目本地初始化显式 true，开启模拟事件/故障/时间推进/reset。生产普通配置/读取/控制仍鉴权，Cookie Secure。

## 已验证

- 根代理独立最终后端：153 passed、3 MySQL-gated skips；前端 30 passed；真实浏览器最终 21 passed。
- 独立测试库实际 MySQL：3 passed；两个真实 API 进程前后比较会话、完整环境/配置、归档、偏好、任务/动作及幂等重放，一致；证据 `output/m3-restart-proof.json`。
- 根资源防护 3 passed；后端 Ruff/格式 36 文件、根脚本 6 文件、前端 ESLint/TypeScript/Vite 通过；uv 锁/67 包兼容、离线工具/图/适配器/RSA 检查通过。
- 后端规格/质量与前端/根脚本规格/质量分别独立只读审阅，问题修复后复核批准。保留冷认证依赖缺项、deadline、大小写、历史、重试键、跨标签、焦点、portal 等原始 red/green 记录。
- 桌面/手机、登录、任务结果和任务手机表单截图在 `output/m3-*.png`，已目视检查。旧 M1/M2 证据继续保留。
- CI 已配置专属 MySQL、迁移、后端/脚本/浏览器检查；本轮未发布或运行远端 CI。

## 启动与服务状态

完整步骤见 [README](README.md)。先确认 Docker 引擎已运行；项目根目录 `python scripts/setup_mysql.py` 保留数据并检查迁移；API/网页分别在自己的终端启动，默认 8100/5174。

验收的临时网页/API、18100 重启检查进程已退出。本项目 MySQL 保留运行、数据卷保留；只停止本轮身份核实的进程。

**Docker 原未运行，本轮启动引擎时触发了既有容器按原策略自动恢复。** 已如实记录该环境副作用；后续未对旧容器执行停止/重建或数据库操作，不能声称旧服务状态完全未变。

## 下一步

用户已发起 **M4：LangGraph 单 Agent 自然语言闭环**。[M4 细化设计](docs/superpowers/specs/2026-10-27-m4-single-agent-design.md)已写并自查，尚未修改业务代码或运行真实模型。按 brainstorming 技能的书面设计审阅要求，等待用户确认后编写实施计划并执行；不将已授权 M4 误记成尚未授权。

已异步询问本项目模型供应商/模型名/API 地址，目前未收到答复，不读取旧项目密钥。缺少真实模型配置不妨碍后续代码与离线测试，但真实接入必须单独实际验证。上一轮已修复前端安装目录不完整造成的 Vite 命令缺失及原生依赖错误；README 已补首次/日常启动与排错步骤。

当前仍没有模型调用、Agent、SSE、后台时钟、取消/重规划、图检查点恢复或真实硬件；这些依阶段接入，不用纯仿真事务冒充外部设备 exactly-once。

入口：[路线](docs/homemind-development-roadmap.md)、[M3 设计](docs/superpowers/specs/2026-10-27-m3-accounts-persistence-design.md)、[计划](docs/superpowers/plans/2026-10-27-m3-accounts-persistence.md)、[验证记录](docs/verification/m3-accounts-persistence.md)。
