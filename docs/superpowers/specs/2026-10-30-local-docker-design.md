# 本机完整 Docker 部署

用户已确认将现有应用部署到本机 Docker，不改变 Agent、仿真或数据模型。

根目录 compose.yaml 扩展既有 MySQL 服务，同属 homemind 项目、同一安装标识和 homemind_mysql_data 卷。新增一次性 migrate、单进程 api 和 web。migrate 等 MySQL 健康并执行现有受保护迁移；api 等迁移成功；web 等 api 健康。后端通过 mysql:3306 连接，网页由 Nginx 提供构建产物，/api/ 代理剥除前缀。

本机网页默认 http://127.0.0.1:18080，避免占用当前 Vite 5174；后端不映射宿主端口。保留开发模式 Cookie、原有 CSRF 精确来源检查，只允许两个本机网页来源。模型设置由 backend/.env 运行时注入，构建上下文排除密钥、输出、虚拟环境和 node_modules。

首次准备仍用 python scripts/setup_mysql.py --provision-only（仅标准库），生成安装标识与凭据并确认已有资源归属；现有安装直接复用。日常使用 docker compose --env-file .local/mysql.env up -d --build --wait。停止使用同配置 stop，不删卷。新 /ready 只检查数据库与迁移就绪，不创建会话，不调用模型；/health 保持存活语义。

验收：真实镜像构建、服务健康、Nginx 静态文件/API 路径与超时、注册登录/CSRF、合成家庭设备操作、API 重启和整套停止/启动后数据与会话保留；未登录越权拒绝。检查数据库容器/卷身份不变和既有用户记录保留。真实 DeepSeek 调用为零。
