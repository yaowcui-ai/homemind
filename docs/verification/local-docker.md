# 本机 Docker 全栈部署验证

2026-10-30，分支 `codex/local-docker-deployment`。用户确认 Nginx / FastAPI / MySQL 本机容器化方案。Agent 提示、模型参数、评测集、仿真和任务执行语义均未改动。

## 部署与启动

在仓库根目录、Docker Desktop Linux 引擎运行时：

```powershell
docker compose --env-file .local/mysql.env up -d --build --wait
```

网页 **http://127.0.0.1:18080/**。实际启动成功，`mysql`、`api`、`web` 均 healthy；`migrate` 退出码 0，表示一次性迁移成功，不是服务故障。停止使用同配置 `stop`，保留数据。首次新克隆先用标准库脚本 `python scripts/setup_mysql.py --provision-only` 生成本项目本地凭据和资源身份，无须本机安装 npm 或后端虚拟环境。完整说明见根 README。

根 compose.yaml 扩展原 MySQL 服务，复用同一容器、数据卷、安装标识和数据库凭据。后端连接 `mysql:3306`，不映射宿主端口；Nginx 仅映射 `127.0.0.1:18080`，代理 `/api/` 时剥除前缀、保留 Cookie / Origin，读取超时 85 秒，不重试写请求。API 仍单进程，不宣称多个 API 副本之间有分布式执行锁。

迁移服务等待 MySQL healthy，API 等待迁移成功，web 等待 API healthy。就绪检查 `/ready` 复用现有数据库安装标识/迁移版本校验；数据库不可用时 503，不创建匿名会话；`/health` 仍只表示进程存活。这些依赖条件对应 [Compose 官方启动顺序说明](https://docs.docker.com/compose/how-tos/startup-order/)。

## 实际验证

| 项目 | 本轮实际结果 |
| --- | --- |
| 两个镜像构建 | 成功；Python 3.12、Node 24、Nginx 基础镜像固定摘要；uv/npm 均使用已有锁文件 |
| 就绪与原安全/迁移回归 | 21 passed，包含新增 3 项 readiness；新增测试最初因缺少路由返回 404 而失败，实现后通过 |
| Compose 配置与资源保护回归 | 5 passed，含新增 1 项带引号密钥解析回归；测试只解析合成 Compose 配置，不连接 Docker 引擎 |
| 实际 API 经 Nginx 访问 | 静态首页、缺失静态资源 404、API health/ready、匿名家庭访问 401、注册、两房十二实体、房间与偏好修改通过 |
| CSRF | 合法来源写入成功；不受信来源写入返回 403 |
| 实际浏览器 | 登录、设备写入/读回、刷新后保留、1440px 与 360px 页面验证通过，0 page errors |
| API 重启 | 原会话、合成家庭与偏好保留；原数据记录哈希不变 |
| 整套 stop 后用原命令重启 | 最终配置再次成功；同一个 MySQL 容器、同一个卷和安装标识；原会话、合成家庭、房间、偏好及灯开启状态保留 |
| 原有账号数据 | 部署前记录原有 1 用户、1 家庭、2 房间、12 实体、偏好及安装记录哈希，部署/重启后全部原行不变；只新增 1 个隔离合成验收账号 |
| 镜像与模型配置 | API 使用非 root 用户；镜像配置/历史未包含本项目密钥；应用镜像路径不含本地 .env / Git / output，网页镜像只含构建产物；容器模型开关和密钥与本机解析值完全一致 |

验证日志、原始哈希与合成账号凭据仅在忽略的 `.local/`，不上传。主要日志为 `docker-build.log`、`docker-up-final.log`、`docker-stop-final.log`；浏览器截图 `docker-desktop.png`、`docker-mobile.png`。原有账号未进行设备写入；合成账号保留在本机，凭据不写入本文或仓库。

## 验证中修复的问题

初版 Compose 使用 `env_file: format: raw`，把本机密钥值外层引号一并注入。配置审计发现容器值与 Python dotenv 解析值不同，未实际调用模型。用合成带引号密钥新增回归测试观察到 RED 后，改为标准 dotenv 解析；回归 GREEN，并在实际运行容器中只比较散列确认密钥与开关一致，不输出密钥。本机 `backend/.env` 无须修改。

本轮没有真实 DeepSeek 请求，也没有重跑或改变模型评测结果。验证的是本机容器化交付与配置、数据库和界面闭环，不是新增模型效果证据。没有完成公网、域名、TLS 或真实硬件部署。
