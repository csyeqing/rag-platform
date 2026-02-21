# Linux 服务器一键 Docker 部署文档

本文档用于将本项目完整部署到 Linux 服务器（前端 + 后端 + PostgreSQL）.

## 1. 适用范围

- 目标系统：Ubuntu 22.04+/Debian 12+/CentOS Stream 9+（安装 Docker 后均可）
- 部署方式：`docker compose` 单机编排
- 服务组成：
  - `frontend`（Nginx 静态站点 + `/api` 反向代理）
  - `backend`（FastAPI）
  - `postgres`（pgvector）

## 2. 前置条件

- 已安装 Docker Engine 与 Docker Compose 插件
- 至少 4 vCPU / 8 GB RAM（本地 embedding 建议 16 GB RAM）

快速校验：

```bash
docker --version
docker compose version
```

## 3. 部署方式选择

### 方式 A：在线部署（服务器可访问外网）

服务器需要能访问 Docker Hub 和 HuggingFace。

### 方式 B：离线部署（服务器无法访问外网）⭐ 推荐

在本地构建镜像（包含 bge-m3 模型），导出后上传到服务器。

---

## 4. 离线部署（推荐）

适用于服务器无法访问 Docker Hub 或 HuggingFace 的情况。

### 4.1 本地构建镜像

在开发机（Apple M4 或其他可访问 HuggingFace 的机器）上执行：

```bash
# 构建并导出镜像到 deploy/images 目录
./deploy/build-images.sh
```

该命令会：
1. 构建后端镜像（包含 bge-m3 模型，约 5GB）
2. 构建前端镜像
3. 拉取基础镜像（postgres、nginx）
4. 导出所有镜像为 tar 文件

导出文件：
```
deploy/images/
├── rag-backend-latest.tar      # 后端镜像（含 bge-m3）
├── rag-frontend-latest.tar     # 前端镜像
├── postgres-pgvector.tar       # PostgreSQL 镜像
└── nginx-alpine.tar            # Nginx 镜像
```

### 4.2 上传到服务器

```bash
# 方式1：scp 上传
scp -r deploy/images user@server:/opt/rag_web/

# 方式2：rsync 上传（推荐，支持断点续传）
rsync -avz --progress deploy/images user@server:/opt/rag_web/

# 同时上传代码
rsync -avz --exclude 'node_modules' --exclude '.git' \
  --exclude 'backend/.venv' --exclude 'backend/__pycache__' \
  ./ user@server:/opt/rag_web/
```

### 4.3 服务器端加载镜像

```bash
# SSH 到服务器
ssh user@server

# 加载镜像
cd /opt/rag_web
./deploy/load-images.sh deploy/images
```

### 4.4 配置并启动

```bash
# 复制并编辑配置
cp deploy/.env.server.example deploy/.env.server
vim deploy/.env.server

# 离线模式启动（不构建镜像）
OFFLINE_DEPLOY=true ./deploy/up.sh deploy/.env.server
```

### 4.5 Embedding 配置（离线部署）

由于 bge-m3 模型已内置在镜像中，推荐配置：

```env
EMBEDDING_BACKEND=local
EMBEDDING_MODEL_NAME=BAAI/bge-m3
EMBEDDING_LOCAL_DEVICE=cpu
EMBEDDING_FALLBACK_HASH=false
```

---

## 5. 在线部署

### 5.1 获取代码

```bash
git clone <your-repo-url> /opt/rag_web
cd /opt/rag_web
```

### 5.2 配置服务器环境变量

复制模板：

```bash
cp deploy/.env.server.example deploy/.env.server
```

编辑 `deploy/.env.server`（至少修改以下项）：

- `SECRET_KEY`
- `POSTGRES_PASSWORD`
- `DEFAULT_ADMIN_PASSWORD`
- `CORS_ORIGINS`
- `FRONTEND_PORT`（建议 `80`）
- `BACKEND_IMAGE`（默认 `rag-backend:latest`）
- `FRONTEND_IMAGE`（默认 `rag-frontend:latest`）

### 5.3 Embedding 配置

#### 方案 A：本地 embedding（默认）

```env
EMBEDDING_BACKEND=local
EMBEDDING_MODEL_NAME=BAAI/bge-m3
EMBEDDING_LOCAL_DEVICE=cpu
EMBEDDING_FALLBACK_HASH=false
```

说明：
- 启动时会自动预下载模型到持久化卷 `hf_cache`（约 2GB，首次启动需等待几分钟）
- 模型下载失败时会自动降级到 hash embedding（设置 `EMBEDDING_FALLBACK_HASH=true`）
- 如需 GPU 加速，设置 `EMBEDDING_LOCAL_DEVICE=cuda`（需 NVIDIA GPU + CUDA）

#### 方案 B：远程 embedding API

```env
EMBEDDING_BACKEND=remote
EMBEDDING_PROVIDER_TYPE=openai_compatible
EMBEDDING_ENDPOINT_URL=https://your-embedding-endpoint/v1/embeddings
EMBEDDING_API_KEY=your-api-key
EMBEDDING_FALLBACK_HASH=false
```

### 5.4 一键部署

执行：

```bash
./deploy/up.sh deploy/.env.server
```

该命令会自动：

1. 使用 `deploy/.env.server` 中指定的镜像启动服务（默认 `rag-backend:latest` / `rag-frontend:latest`）
2. 启动 PostgreSQL
3. 启动 backend 并等待数据库就绪
4. 自动执行 `python scripts/init_db.py`（创建扩展、建表、默认管理员）
5. 启动 frontend

如需手动补跑初始化（例如升级后单独执行）：

```bash
docker compose --env-file deploy/.env.server -f deploy/docker-compose.yml exec -T backend python scripts/init_db.py
```

---

## 6. 部署后验证

查看容器状态：

```bash
docker compose --env-file deploy/.env.server -f deploy/docker-compose.yml ps
```

查看后端健康检查：

```bash
curl http://127.0.0.1:${BACKEND_PORT:-8000}/health
```

访问页面：

- 前端：`http://<服务器IP或域名>:<FRONTEND_PORT>`
- 默认管理员：`DEFAULT_ADMIN_USERNAME / DEFAULT_ADMIN_PASSWORD`

部署后请额外验证：
- 管理员进入“系统设置”可看到并管理检索优化配置（小说/故事、公司资料、科学论文、文科论文等）。
- 聊天页面可通过下拉框选择检索优化配置，并在会话中持续生效。
- `curl http://127.0.0.1/api/settings/retrieval-profiles` 不应返回 404（未登录时应返回 401）。

## 7. 常用运维命令

查看日志：

```bash
docker compose --env-file deploy/.env.server logs -f backend
docker compose --env-file deploy/.env.server logs -f frontend
docker compose --env-file deploy/.env.server logs -f postgres
```

重启服务：

```bash
docker compose --env-file deploy/.env.server restart
```

升级部署（拉新代码后）：

```bash
git pull
./deploy/up.sh deploy/.env.server
```

停止服务：

```bash
docker compose --env-file deploy/.env.server down
```

## 8. 首次上线后的必做项

如果这是从旧版本升级（历史知识库已存在），请对每个知识库执行一次"重建索引"，以重算向量。

## 9. 数据备份与恢复

### 备份 PostgreSQL

```bash
docker exec -t "${PROJECT_NAME:-rag}_postgres" \
  pg_dump -U "${POSTGRES_USER:-rag}" "${POSTGRES_DB:-rag_mvp}" > rag_mvp_$(date +%F).sql
```

### 恢复 PostgreSQL

```bash
cat rag_mvp_2026-01-01.sql | docker exec -i "${PROJECT_NAME:-rag}_postgres" \
  psql -U "${POSTGRES_USER:-rag}" "${POSTGRES_DB:-rag_mvp}"
```

## 10. 生产建议

- 建议使用 Nginx/Caddy 在 80/443 层做 HTTPS 终止，再转发到 `FRONTEND_PORT`。
- 将 `BACKEND_PORT` 与 `POSTGRES_PORT` 限制为内网访问，避免公网暴露数据库。
- 定期备份 `postgres_data` 与数据库逻辑备份文件。
