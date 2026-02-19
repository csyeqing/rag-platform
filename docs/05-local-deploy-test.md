# 本地部署与测试文档

本文档用于在本机完成 RAG Web MVP 的部署和关键功能验证。

## 1. 前置环境

必须：
- Python `3.11+`
- Node.js `20+`（已在本机验证 Node 25 可用）
- npm `10+`
- PostgreSQL 16（需 `pgvector` 扩展）

可选：
- Docker（用于快速启动 PostgreSQL）

## 2. 目录准备

在项目根目录执行：

```bash
cd /Users/yeqing/Documents/Project/codex_demo
mkdir -p backend/data/knowledge
mkdir -p backend/data/libraries
```

## 3. 启动 PostgreSQL（推荐 Docker）

如果本机有 Docker：

```bash
docker run -d --name rag_postgres \
  -e POSTGRES_DB=rag_mvp \
  -e POSTGRES_USER=rag \
  -e POSTGRES_PASSWORD=rag \
  -p 5432:5432 \
  pgvector/pgvector:pg16
```

如果使用本机 PostgreSQL，请确保：
- 数据库 `rag_mvp` 已创建
- 用户 `rag/rag` 可访问
- 可执行 `CREATE EXTENSION vector;`

## 4. 配置本地 Embedding（Apple M4 推荐）

Apple Silicon 场景推荐直接使用本地 `sentence-transformers` 加载 `BAAI/bge-m3`，无需额外 embedding 容器。
如果你希望使用托管服务，也可切到远程 API（见文末可选项）。

## 5. 数据库初始化（必须先执行一次）

```bash
cd /Users/yeqing/Documents/Project/codex_demo/backend
python3.11 -m venv .venv311
source .venv311/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

编辑 `.env`，确保以下值正确：

```env
DATABASE_URL=postgresql+psycopg://rag:rag@localhost:5432/rag_mvp
STORAGE_ROOT=./data
KB_SYNC_ROOT=./data/knowledge
DEFAULT_ADMIN_USERNAME=admin
DEFAULT_ADMIN_PASSWORD=admin123456
DEFAULT_EMBEDDING_DIM=1536
EMBEDDING_BACKEND=local
EMBEDDING_MODEL_NAME=BAAI/bge-m3
EMBEDDING_LOCAL_DEVICE=mps
EMBEDDING_FALLBACK_HASH=true
```

注：`bge-m3` 原生向量维度为 1024，当前项目数据库向量列为 1536，后端会自动零填充后写入。

执行初始化程序（会创建扩展、数据表、默认管理员账号）：

```bash
cd /Users/yeqing/Documents/Project/codex_demo/backend
source .venv311/bin/activate
export PYTHONPATH=.
python scripts/init_db.py
```

说明：
- 可重复执行，属于幂等初始化，不会重复创建同名管理员。
- 默认管理员账号取自 `.env` 中：`DEFAULT_ADMIN_USERNAME` / `DEFAULT_ADMIN_PASSWORD`。
- 默认管理员初始字段：`role=admin`、`is_active=true`。

## 6. 启动后端

启动服务：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

健康检查：

```bash
curl http://localhost:8000/health
```

预期返回：

```json
{"status":"ok"}
```

## 7. 启动前端

新开一个终端：

```bash
cd /Users/yeqing/Documents/Project/codex_demo/frontend
cp .env.example .env
npm install
npm run dev
```

访问：
- 前端：http://localhost:5173
- 默认管理员：`admin / admin123456`

## 8. API 快速联调（可选）

## 8.1 登录

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123456"}' | jq -r '.token.access_token')

echo "$TOKEN"
```

## 8.2 创建模型 Provider（聊天）

`endpoint_url` 请填写完整聊天接口路径（OpenAI 风格示例：`/v1/chat/completions`）。

```bash
curl -s -X POST http://localhost:8000/api/providers \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "name":"OpenAI Chat",
    "provider_type":"openai",
    "endpoint_url":"https://api.openai.com/v1/chat/completions",
    "model_name":"gpt-4o-mini",
    "api_key":"sk-xxxx",
    "is_default":true,
    "capabilities":{"chat":true,"embed":true,"rerank":false}
  }'
```

## 8.3 创建知识库

```bash
LIB_ID=$(curl -s -X POST http://localhost:8000/api/kb/libraries \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"demo-lib","owner_type":"private","tags":["demo"]}' | jq -r '.id')

echo "$LIB_ID"
```

## 8.4 上传文件

```bash
echo 'RAG 是检索增强生成技术。' > /tmp/rag_demo.txt

curl -s -X POST http://localhost:8000/api/kb/files/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "library_id=$LIB_ID" \
  -F "file=@/tmp/rag_demo.txt"
```

## 8.5 创建会话并提问（SSE）

```bash
SESSION_ID=$(curl -s -X POST http://localhost:8000/api/chat/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"title":"demo-session","library_id":null}' | jq -r '.id')

echo "$SESSION_ID"

curl -N -X POST "http://localhost:8000/api/chat/sessions/$SESSION_ID/messages" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "content":"什么是RAG？",
    "stream":true,
    "top_k":5,
    "use_rerank":false,
    "show_citations":true
  }'
```

## 9. Web 功能验收清单

登录后依次验证：
1. `模型配置` 页面：新增/删除配置、验证配置。
2. `知识库管理` 页面：创建库、编辑标签与归属、上传文件、查看文件列表、删除文件、触发重建。
3. 若是从旧版本切换到 `bge-m3`：对已有知识库执行“重建索引”（必要），确保历史 chunk 向量完成重算。
4. `知识图谱` 面板：查看节点/关系统计，执行“重建图谱”，确认节点和关系数量变化。
5. `AI 聊天` 页面：创建会话、选择模型/知识库、流式回答、引用显示开关，确认引用中可见 `source=graph` 或图谱命中实体。
6. `系统设置` 页面：本地设置保存；管理员用户管理（创建/禁用/角色切换）。

## 10. 常见问题

### 10.1 后端启动报数据库连接错误
- 检查 PostgreSQL 是否启动。
- 检查 `.env` 中 `DATABASE_URL`。

### 10.2 启动时报 `vector` 扩展错误
- 确认数据库支持 pgvector。
- 执行 `CREATE EXTENSION IF NOT EXISTS vector;`。

### 10.3 Embedding 服务不可用
- 检查后端环境是否安装 `sentence-transformers`（`pip install -r requirements.txt`）。
- 检查 `.env` 中是否设置：`EMBEDDING_BACKEND=local`、`EMBEDDING_MODEL_NAME=BAAI/bge-m3`。
- 若 `mps` 不稳定可改 `EMBEDDING_LOCAL_DEVICE=cpu`。

### 10.4 目录同步失败
- 目录必须位于 `KB_SYNC_ROOT` 之下，默认是 `backend/data/knowledge`。

### 10.5 （可选）本机加载 embedding 模型
### 10.5 （可选）切换到远程 embedding API
- 如需使用远程 API，可将 `.env` 改为：
  - `EMBEDDING_BACKEND=remote`
  - `EMBEDDING_PROVIDER_TYPE=openai_compatible`
  - `EMBEDDING_ENDPOINT_URL=https://your-embedding-endpoint/v1/embeddings`
  - `EMBEDDING_MODEL_NAME=BAAI/bge-m3`
  - `EMBEDDING_API_KEY=your-api-key`
  - 建议 `EMBEDDING_FALLBACK_HASH=false`。
