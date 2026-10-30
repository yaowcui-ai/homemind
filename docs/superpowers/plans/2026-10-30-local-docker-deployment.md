# 本机 Docker 部署 Implementation Plan

> 按 executing-plans 在本会话顺序执行。用户已确认部署方案，无须再次审批。

**Goal:** 一条 Compose 命令启动本机网页、API 和现有 MySQL。

**Architecture:** 根 compose.yaml 扩展既有 MySQL，新增受保护迁移、API 与 Nginx 网页。数据库数据卷和安装标识保留。模型配置仅运行时注入。

**Tech Stack:** Docker Compose、Python 3.12 / uv、Node 24、Nginx、既有 React/FastAPI/MySQL。

### Task 1: 就绪检查

- [x] 新建 backend/tests/test_readiness.py：无数据库返回503；数据库就绪返回200；故障返回503且不泄漏；探针不创建会话。运行 .venv/Scripts/python.exe -m pytest tests/test_readiness.py -q 观察 RED。
- [x] 在 backend/src/homemind/app.py 增加 /ready，调用现有 Database.ready，不改变 /health。运行相同测试确认 GREEN。

### Task 2: 容器编排

- [x] 新建 backend/Dockerfile、backend/.dockerignore：uv 按锁文件仅安装运行依赖，非 root 单进程运行，复制范围仅源码/锁文件。
- [x] 新建 frontend/Dockerfile、frontend/.dockerignore 和 deploy/nginx.conf：锁定 npm 依赖，多阶段构建，仅静态产物进入 Nginx；代理保留 Cookie/Origin，禁用 POST 重试，85秒读取超时。
- [x] 新建 compose.yaml，使用 mysql service extends、同名同标签卷；migrate→api→web 就绪门禁，web 仅绑定127.0.0.1:18080。
- [x] 用 docker compose --env-file .local/mysql.env config --quiet 验证；不要输出解析后秘密。

### Task 3: 实际部署验收与文档

- [x] 记录现有 MySQL 容器/卷身份和用户ID集合到忽略的 .local；执行 python scripts/setup_mysql.py --provision-only。
- [x] 执行 docker compose --env-file .local/mysql.env up -d --build --wait，观察真实构建与健康结果。
- [x] 通过 Nginx 对新建合成家庭验收注册、状态、设备操作、CSRF、匿名权限，浏览器登录与刷新；重启 API 以及整套 stop/up 后核对会话、设备和原有用户记录。
- [x] 检查镜像构建上下文与文件不含 .env、Git、output、本机数据库；本轮无模型调用。
- [x] 更新 README、CURRENT_CONTEXT、路线和 docs/verification/local-docker.md，写实际命令、验证和边界。保留 README 既有编辑的目的并修正错误启动目录。
- [x] 额外修复实际配置审计发现的raw dotenv引号问题；scripts/tests/test_docker_config.py以合成配置RED/GREEN覆盖，实际运行容器散列确认，不调用模型。
