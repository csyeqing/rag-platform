# PRD: RAG Web 平台 MVP

## 1. 产品定位
RAG Web 平台是面向企业/团队的知识问答系统，提供统一的 Web GUI 来配置大模型、管理知识库，并基于 RAG 进行多轮对话。

## 2. 产品目标
- 降低接入不同大模型 API 的工程成本。
- 提供可视化知识库管理能力（目录同步、上传、重建索引、状态跟踪）。
- 提供可追溯的 AI 聊天能力（引用来源默认展示，可关闭）。
- 首版支持小团队生产可用（单节点、可观测、基础安全）。

## 3. 目标用户与角色
- 管理员（admin）
- 普通用户（user）

### 3.1 管理员能力
- 管理模型配置与默认模型。
- 管理共享知识库。
- 管理系统策略和审计查看（MVP 基础审计）。

### 3.2 普通用户能力
- 管理私有模型配置。
- 管理私有知识库。
- 发起聊天与查看历史消息。

## 4. 范围
### 4.1 In Scope (MVP)
- 账号密码登录 + JWT。
- RBAC（管理员/普通用户）。
- 模型中心：Provider 配置、端点 URL、模型名、API Key（密文存储/脱敏展示）、配置验证。
- Provider 适配：OpenAI、Anthropic、Gemini、OpenAI-compatible。
- 知识库：创建、列表、上传文本文件（txt/md/csv）、目录同步、重建索引、任务状态查询。
- 知识库归属：默认私有；管理员可建共享库。
- RAG 聊天：多轮会话、流式输出、混合检索（向量+关键词）、可选重排、引用显示开关。
- 基础可观测：关键操作审计日志。

### 4.2 Out of Scope (MVP)
- OCR/图片/音视频文档处理。
- 多租户计费。
- 复杂工作流 Agent。
- 企业 SSO。

## 5. 用户故事
- 作为管理员，我可以添加不同 Provider 的模型配置并验证可用性。
- 作为普通用户，我可以上传文档到私有知识库并立即被检索。
- 作为用户，我可以在聊天中选择模型与知识库并得到带来源引用的回答。
- 作为管理员，我可以创建共享知识库让团队成员查询。

## 6. 功能需求

## 6.1 认证与权限
- `POST /api/auth/login`：用户名密码登录。
- `GET /api/users/me`：获取当前用户信息。
- 所有业务接口需鉴权。

## 6.2 模型中心
- `POST /api/providers`：新增配置。
- `GET /api/providers`：查询当前用户配置。
- `PUT /api/providers/{id}`：更新配置。
- `DELETE /api/providers/{id}`：删除配置。
- `POST /api/models/validate`：验证 provider 配置。

### 字段要求
- provider_type、endpoint_url、model_name、api_key 必填。
- api_key 后端加密存储。

## 6.3 知识库管理
- `POST /api/kb/libraries`：创建库（private/shared）。
- `GET /api/kb/libraries`：可见库列表（共享+本人私有）。
- `POST /api/kb/files/upload`：上传文本文件并即时索引。
- `POST /api/kb/files/sync-directory`：同步目录下文件并索引。
- `POST /api/kb/index/rebuild`：重建索引。
- `GET /api/kb/tasks/{task_id}`：查询任务状态。

### 文件范围
- MVP 支持：`.txt` `.md` `.csv`

## 6.4 聊天与检索
- `POST /api/chat/sessions`：创建会话。
- `GET /api/chat/sessions`：会话列表。
- `POST /api/chat/sessions/{id}/messages`：发送消息（支持 SSE 流式）。
- `GET /api/chat/sessions/{id}/messages`：消息历史。

### 聊天参数
- `temperature` `top_p` `max_tokens` `top_k` `use_rerank` `show_citations`

## 7. 非功能需求
- 安全：API Key 密文存储；最小权限；关键操作审计。
- 性能：支持小团队并发；索引任务可追踪。
- 可靠性：失败可回退提示；长任务记录状态。
- 可维护性：Provider 插件化；检索策略可配置。

## 8. 验收标准
- Web GUI 可完成登录、Provider 配置、知识库管理、聊天问答全链路。
- SSE 流式响应可正常显示。
- 引用来源可默认展示并可关闭。
- 共享库写权限仅管理员。
- API Key 在列表中仅显示脱敏值。

## 9. 风险与缓解
- 外部 Provider API 不稳定：提供本地降级回复和错误提示。
- 向量检索质量不稳：采用混合检索和可选重排。
- 权限误配置：API 层硬性 RBAC 检查。
