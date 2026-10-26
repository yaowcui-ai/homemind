# M1 工程基础验证记录

日期：2026-10-26（Asia/Shanghai）。状态：M1 工程基础完成，本地验收通过；停在 M2 之前。

## 最终检查结果

| 检查 | 实际结果 |
| --- | --- |
| 后端 pytest | 11 通过 |
| 前端 Vitest | 13 通过 |
| Playwright 浏览器 | 4 通过 |
| ESLint / TypeScript / Vite 构建 | 通过 |
| Ruff / Ruff 格式检查 | 通过 |
| uv 锁文件离线检查 | 57 包解析通过 |
| 已安装 Python 依赖一致性 | 56 包检查通过 |
| npm ci 锁文件重装 | 302 包安装成功 |
| 离线 Agent 依赖检查 | 工具、内存状态图、内存检查点、MySQL 适配器导入通过 |
| 代码独立审阅 | 两项意见核实并修复，复核无剩余当前阶段问题 |
| 桌面与手机视觉检查 | 已查看截图，无明显遮挡；390px 无横向溢出 |

浏览器四项为：经真实 Vite 代理确认 API；浏览器离线及恢复后的显式重查；其他服务的 200 响应不能误报在线；手机视口操作与宽度检查。临时服务在测试结束后关闭，端口释放。

本地原始检查输出在被 Git 忽略的 `output/`：`m1-backend-tests.txt`、`m1-frontend-tests.txt`、`m1-browser-tests.txt`（首次就绪检查超时）、`m1-browser-tests-after-local-proxy-fix.txt`（4 通过）、`m1-npm-ci.txt`。桌面/手机截图为 `m1-desktop.png`、`m1-mobile.png`，可通过重跑浏览器检查再生成。

## 已执行的行为验证

- 后端最初 `/health` 返回 404，健康契约测试 2 失败、1 通过；添加路由后完整后端测试 11 通过。
- 配置校验测试先观察到非法端口、非法环境、空绑定地址未被拒绝的 5 个失败；增加边界后通过。
- 前端客户端及页面在功能接入前 12 项失败；完成实际请求和交互后 12 项通过。
- 依赖检查实际运行 LangChain 工具与 LangGraph 内存状态图，检查点值读回正确；社区 MySQL 适配器导入成功。检查中阻止 socket 连接，模型调用为 0，MySQL 实际连接和恢复未运行。
- 新增浏览器测试时曾因 Node 类型项目缺少 DOM 类型导致构建失败；确认 TypeScript 有效配置后给该项目补充 DOM 类型，再执行构建。
- 独立审阅指出默认 online 网络模式会暂停离线后的手动本机请求。新增回归用例实际观察到 fetch 只有 1 次而非预期 2 次的失败，改用 networkMode=always 后 13 项前端测试通过；真实浏览器离线/恢复检查也通过。
- Playwright 首次等待 API 就绪超时。对比同一 API：HTTPX trust_env=false 得到 200，trust_env=true 超时，Node 原生直连得到 200；检查安装版本的 Playwright 确认就绪检查读取代理环境。测试配置在自身进程的 NO_PROXY/no_proxy 中保留旧规则并追加本机地址，再跑浏览器 4 项通过；未改用户系统或父终端配置。
- 用 Vite resolveConfig 核实 server.proxy 与 preview.proxy 均含 `/api`，修正 README 中 preview 不含代理的错误说法。

## 固定环境

- Python 3.12.14、uv 0.12.5；Node.js 24.14.1、npm 11.11.0。
- FastAPI 0.162.0、Starlette 1.10.0、LangGraph 1.2.17、LangChain 1.4.7、langgraph-checkpoint-mysql 3.0.0、asyncmy 0.2.17。
- React 19.3.1、Ant Design 6.6.8、Vite 8.3.5、TypeScript 5.9.3、Vitest 5.0.5、jsdom 26.1.0。
- 选用 TypeScript 5.9.3 以符合 typescript-eslint 支持范围，选用 jsdom 26.1.0 以兼容当前 Node 小版本。

## 验证边界

此阶段验证 API 活性、前后端请求和基础交互，不代表设备仿真、模型效果、数据库运行、检查点持久化恢复或生产部署通过。GitHub Actions 配置已写入，尚未在远端运行。开发服务器与静态 preview 的区别见 README。
