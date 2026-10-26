# HomeMind 当前接续

更新日期：2026-10-26（Asia/Shanghai）。

## 用户授权和当前阶段

用户已批准总体设计，M1 已完成；最新“ok，开始下一步。”授权实施 M2 可配置家庭与设备仿真。M2 已完成，当前停在 M3 开始前，等待用户发起下一阶段。助手负责当前阶段编码、必要验证和修复，不能自动推进全部阶段。

本目录为独立 Git 仓库，当前分支 `codex/m2-simulation`，从 M1 提交 `5a86177` 开始。父工作区的 `.git/info/exclude` 忽略 `/homemind/`，原有项目和未提交修改不纳入本仓库。

## 当前事实

- Python 3.12.14 独立虚拟环境及 uv 锁文件已创建。
- Node 24.14.1 / npm 11.11.0，前端 package-lock 已创建。
- 后端 111 项测试、前端 24 项测试、Playwright 10 项真实浏览器检查通过；包含 M1 基础检查和新增 M2 业务/交互回归。
- LangChain 工具、LangGraph 内存检查点和 MySQL 适配器导入检查通过，未连接 MySQL、未请求模型。
- version=0.2.0，stage=M2。React 已接真实仿真接口，支持默认两房十二实体、六种类型、新增/改名/迁移/停用/归档、主读数绑定、设备控制与传感器事件、故障和 reset。
- 后端为锁保护的本地 `demo-home`，每应用实例独立 ID 与状态，所有读返回独立快照。production 不挂载未鉴权仿真接口。时间按用户推进的整数分钟流动，物理模型使用 Decimal 和固定舍入；状态/配置版本分开。
- 灯、空调、窗帘可控制；传感器只读，人工改变通过独立模拟事件。主读数未绑定/失效或观测未知时返回 null；离线不自动关闭物理设备。
- 五种故障持续到更改；延迟在到期分钟边界应用，再运行该分钟物理模型。配置变更、停用、迁移、归档、故障变化及 reset 取消相关待执行动作。控制后网页独立读取快照，结果区分 verified/failed/unknown。
- reset 保留配置清单、名称、ID、归属、主绑定、启用及初始参数，换 world_id、清空时间/能耗/故障/延迟；归档实体不复活。当前只有进程内保存，重启恢复默认，不使用多个 worker。
- 前端构建、ESLint、后端 Ruff/格式、uv 锁检查与 56 包依赖检查通过；npm ci 已按锁文件重新安装 302 包成功。
- M2 桌面和 390px 手机截图保存在 `output/m2-desktop.png`、`output/m2-mobile.png`，首屏另有 `m2-*-overview.png`。M1 截图继续保留。
- 后端规格/质量、前端规格/质量独立审阅已批准。审阅发现的手机长房间名溢出、配置表单重复提交均有先失败再修复的回归记录；表单通过同步 useRef 锁和 pending 禁用阻止重复保存。M1 的离线重查 networkMode=always 回归继续通过。
- M2 首次浏览器脚本的虚拟下拉选项/中文标签定位失败原样保留；修正后完整十项通过。测试进程继续补充本机 NO_PROXY，不修改系统/终端代理。
- 临时 API、Vite 和浏览器验收进程已退出，5174/8100 没有留下常驻服务；用户需按 README 在两个终端启动。
- GitHub Actions 配置已写入并通过本地 YAML 结构检查，未对外发布，也未声称远端 CI 已执行。

## 启动与检查

完整命令和五分钟演示见 [README](README.md)。默认后端 127.0.0.1:8100，网页 127.0.0.1:5174。前端 `/api/health` 和 `/api/simulation` 分别代理到后端 `/health`、`/simulation`。

不要从旧项目自动读取密钥。当前阶段不需要模型或数据库配置，不创建业务数据库，不启动其他项目容器。

## 下一阶段

等待用户发起 M3，再细化并实现账号隔离、业务持久化与规则基线。本阶段尚无账号、数据库、Agent、SSE、真实模型调用或硬件接入。总体范围见 [开发路线](docs/homemind-development-roadmap.md) 和 [默认实体](docs/superpowers/specs/2026-10-26-homemind-default-entities-design.md)；M2 接口、模型和检查证据分别见 [实施设计](docs/superpowers/specs/2026-10-26-m2-simulation-design.md)、[实施计划](docs/superpowers/plans/2026-10-26-m2-simulation.md) 和 [验证记录](docs/verification/m2-simulation.md)。
