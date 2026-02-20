# RAG Web 平台 MVP

基于 `Vue3 + Tailwind + Element Plus + Vite`（前端）和 `FastAPI + PostgreSQL + pgvector`（后端）的 RAG 项目骨架，实现了模型配置、知识库管理、聊天问答（SSE）和基础 RBAC。

## 目录结构

```text
.
├── backend/
│   ├── app/
│   ├── scripts/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   └── Dockerfile
├── deploy/
│   ├── docker-compose.yml
│   ├── .env.server.example
│   └── up.sh
├── docs/
│   ├── 01-prd.md
│   ├── 02-tech-architecture-constraints.md
│   ├── 03-frontend-prototype.md
│   └── 04-wbs-task-list.md
└── README.md
```

## 阶段交付文档
- PRD: `docs/01-prd.md`
- 技术栈规则/架构约束: `docs/02-tech-architecture-constraints.md`
- 前端原型说明: `docs/03-frontend-prototype.md`
- WBS 任务清单: `docs/04-wbs-task-list.md`
- 本地部署测试文档: `docs/05-local-deploy-test.md`
- Linux 服务器 Docker 部署文档: `docs/06-linux-server-docker-deploy.md`

## 本机启动

## 1) 启动 PostgreSQL（需启用 pgvector）
推荐直接使用 Docker 启动数据库：

```bash
docker run -d --name rag_postgres \
  -e POSTGRES_DB=rag_mvp \
  -e POSTGRES_USER=rag \
  -e POSTGRES_PASSWORD=rag \
  -p 5432:5432 \
  pgvector/pgvector:pg16
```

## 2) 配置 Embedding（Apple M4 推荐本地模型）

Apple Silicon 场景建议直接使用本地 `sentence-transformers` 方式加载 `BAAI/bge-m3`，无需额外 embedding 容器。

## 3) 启动后端

```bash
cd backend
python3.11 -m venv .venv311
source .venv311/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 建议在 .env 中配置本地 embedding
# EMBEDDING_BACKEND=local
# EMBEDDING_MODEL_NAME=BAAI/bge-m3
# EMBEDDING_LOCAL_DEVICE=mps
export PYTHONPATH=.
python scripts/init_db.py
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

默认管理员：`admin / admin123456`

## 4) 启动前端

```bash
cd frontend
npm install
npm run dev
```

访问：`http://localhost:5173`

## Docker 一键部署

```bash
cp deploy/.env.server.example deploy/.env.server
# 编辑 deploy/.env.server
./deploy/up.sh deploy/.env.server
```

- 前端: `http://localhost:5173`
- 后端: `http://localhost:8000`
- 健康检查: `http://localhost:8000/health`

## 已实现 API（MVP）
- `POST /api/auth/login`
- `GET /api/users/me`
- `GET /api/admin/users`（管理员列表）
- `POST /api/admin/users`（管理员创建用户）
- `PUT /api/admin/users/{id}`（管理员更新用户）
- `POST /api/providers`
- `GET /api/providers`
- `PUT /api/providers/{id}`
- `DELETE /api/providers/{id}`
- `POST /api/models/validate`
- `POST /api/kb/libraries`
- `GET /api/kb/libraries`
- `PUT /api/kb/libraries/{id}`
- `DELETE /api/kb/libraries/{id}`
- `GET /api/kb/libraries/{id}/files`
- `GET /api/kb/libraries/{id}/graph`
- `POST /api/kb/libraries/{id}/graph/rebuild`
- `POST /api/kb/files/upload`
- `DELETE /api/kb/files/{id}`
- `POST /api/kb/files/sync-directory`
- `POST /api/kb/index/rebuild`
- `GET /api/kb/tasks/{task_id}`
- `POST /api/chat/sessions`
- `GET /api/chat/sessions`
- `DELETE /api/chat/sessions/{id}`
- `PATCH /api/chat/sessions/{id}`
- `POST /api/chat/sessions/{id}/messages`（支持 SSE）
- `GET /api/chat/sessions/{id}/messages`
- `GET /api/settings/retrieval-profiles`
- `POST /api/settings/retrieval-profiles`（管理员）
- `PUT /api/settings/retrieval-profiles/{id}`（管理员）
- `DELETE /api/settings/retrieval-profiles/{id}`（管理员）

## 当前限制
- 文档解析仅支持 `txt/md/csv`。
- 重排目前为基础实现（可继续增强为模型级重排）。
- `bge-m3` 输出维度为 1024；当前数据库向量列为 1536，系统会自动零填充到 1536 后入库。
- Docker compose 需本机已安装 Docker（当前环境未内置 docker 命令）。

## 可选：远程 API embedding

如需改为远程 API，可将 `.env` 设置为：

```env
EMBEDDING_BACKEND=remote
EMBEDDING_PROVIDER_TYPE=openai_compatible
EMBEDDING_ENDPOINT_URL=https://your-embedding-endpoint/v1/embeddings
EMBEDDING_MODEL_NAME=BAAI/bge-m3
EMBEDDING_API_KEY=your-key
EMBEDDING_FALLBACK_HASH=false
```

## 可选：TEI 远程 embedding 容器（x86_64）

`docker-compose` 中保留了可选 `embeddings` 服务（`profile=tei`，`linux/amd64`）。

```bash
docker compose -f deploy/docker-compose.yml --profile tei up --build
```

## 升级提示
- 如果你是在旧版本数据库上升级到图谱增强版，请在知识库页面对每个库执行一次“重建图谱”。
- 如果你从 hash embedding 切到 `bge-m3`，请对每个知识库执行一次“重建索引”，以重算历史 chunk 向量。
- 如果你升级到了“检索优化配置”版本，请执行一次数据库初始化脚本：

```bash
cd backend
python scripts/init_db.py
```

该步骤会自动补齐 `chat_sessions.retrieval_profile_id` 字段，并创建内置优化配置：
- `general_default`（通用）
- `novel_story_cn`（小说/故事）
- `enterprise_docs`（公司资料）
- `scientific_paper`（科学论文）
- `humanities_research`（文科研究论文）
