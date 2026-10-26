# HomeMind 当前接续

更新日期：2026-10-26（Asia/Shanghai）。

## 用户授权和当前阶段

用户已批准总体设计，并发出“开始”，授权实施 M1 工程基础。M1 已完成，当前停在 M2 开始前；等待用户发起下一阶段。助手负责当前阶段编码、必要验证和修复，不能自动推进全部阶段。

本目录为独立 Git 仓库，分支 `codex/m1-foundation`。父工作区的 `.git/info/exclude` 忽略 `/homemind/`，原有项目和未提交修改不纳入本仓库。

## 当前事实

- Python 3.12.14 独立虚拟环境及 uv 锁文件已创建。
- Node 24.14.1 / npm 11.11.0，前端 package-lock 已创建。
- 后端健康接口与配置 11 项测试通过；前端请求与页面 13 项测试通过；Playwright 4 项浏览器检查通过。
- LangChain 工具、LangGraph 内存检查点和 MySQL 适配器导入检查通过，未连接 MySQL、未请求模型。
- React 页面已实现真实连接检查、失败提示和手动重试；房间仅为明确标注的设计模板预览。
- 前端构建、ESLint、后端 Ruff/格式、uv 锁检查与 56 包依赖检查通过；npm ci 已按锁文件重新安装 302 包成功。
- 桌面和 390px 手机截图已目视检查，保存在 `output/m1-desktop.png`、`output/m1-mobile.png`。
- 独立审阅发现离线时 TanStack 默认策略暂停本机重查的问题；回归用例先失败，再添加 networkMode=always 后通过。另纠正了 Vite preview 的代理说明。审阅复核无剩余当前阶段问题。
- 浏览器就绪检查第一次受系统代理影响而超时；直连 API 200、读取代理的请求超时，检查 Playwright 实现确认代理路径。仅在测试进程中补充本机 NO_PROXY，重跑 4 项全部通过，未修改系统/终端代理。
- 临时 API、Vite 和浏览器验收进程已退出，5174/8100 没有留下常驻服务；用户需按 README 在两个终端启动。
- GitHub Actions 配置已写入并通过本地 YAML 结构检查，未对外发布，也未声称远端 CI 已执行。

## 启动与检查

完整命令见 [README](README.md)。默认后端 127.0.0.1:8100，网页 127.0.0.1:5174。前端通过 `/api/health` 代理到后端 `/health`。

不要从旧项目自动读取密钥。当前阶段不需要模型或数据库配置，不创建业务数据库，不启动其他项目容器。

## 下一阶段

等待用户发起 M2，再开发可配置家庭与十二实体仿真。总体范围见 [开发路线](docs/homemind-development-roadmap.md) 和 [默认实体](docs/superpowers/specs/2026-10-26-homemind-default-entities-design.md)。实际检查与已知边界见 [M1 验证记录](docs/verification/m1-foundation.md)。
