# 技术栈规则、架构与约束

## 1. 技术栈

### 1.1 前端
- Vue 3 + TypeScript
- Vite
- Tailwind CSS
- Element Plus
- Pinia
- Vue Router
- Axios

### 1.2 后端
- Python 3.11（Docker 基线）
- FastAPI
- SQLAlchemy 2.x
- Pydantic v2
- PostgreSQL 16 + pgvector
- JWT（python-jose）

### 1.3 部署
- 本机先验证
- Docker Compose 一键部署（backend + frontend + postgres）

## 2. 架构分层
- `api`：HTTP 路由层，参数校验与鉴权。
- `services`：业务层（Provider、KB、Chat）。
- `db`：ORM 模型与会话管理。
- `schemas`：输入输出契约。
- `core`：配置、安全、加密等基础能力。

## 3. 核心接口约束

### 3.1 Provider 适配器协议
统一接口：
- `validate_credentials(config)`
- `chat_stream(config, req)`
- `chat(config, req)`
- `embed(config, req)`
- `rerank(config, req)`

新增 Provider 必须实现完整协议，不允许绕过适配层直连 API。

### 3.2 API 稳定性
MVP 固定以下主路径：
- `/api/auth/*`
- `/api/users/*`
- `/api/admin/users/*`
- `/api/providers/*`
- `/api/models/*`
- `/api/kb/*`
- `/api/chat/*`

## 4. 数据与存储约束
- 主数据库：PostgreSQL。
- 向量字段：pgvector（固定维度 1536）。
- 文件存储：本地目录。
- KB 同步目录必须受配置项 `KB_SYNC_ROOT` 约束。

## 5. 安全约束
- 禁止明文存储 API Key。
- API Key 必须加密后落库，前端仅显示掩码。
- 所有业务接口必须 JWT 鉴权。
- RBAC 在 API 层强制执行：共享库写权限仅管理员。
- 审计日志记录关键写操作（登录、Provider 改动、KB 改动、聊天请求）。

## 6. 检索与生成约束
- 检索策略：向量检索 + 关键词匹配（混合召回）。
- 可选重排：通过 Provider rerank 或本地降级策略。
- 聊天默认展示引用，可关闭。
- 流式输出采用 SSE。

## 7. 可观测与失败策略
- 长任务（同步/重建）写入任务表并可查询状态。
- 外部模型调用失败时必须返回可读错误或降级文本。
- 所有异常不得泄露敏感密钥。

## 8. 工程约束
- 前后端均采用 Type/Schema 明确接口。
- 禁止在路由层直接写复杂业务逻辑。
- 每个新增模块需包含最少单元测试（MVP 可先覆盖核心算法与安全函数）。

## 9. 兼容性
- 本地开发可使用 Python 3.9 运行最小功能，但正式基线为 Python 3.11。
- Docker 镜像统一以 Python 3.11 构建。
