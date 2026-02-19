# WBS 全项目任务列表（按实施顺序）

状态说明：
- `DONE` 已完成
- `IN_PROGRESS` 部分完成
- `TODO` 未开始

## 1. 基础设施
| ID | 任务 | 输入 | 输出 | 依赖 | 验收标准 | 风险 | 回滚策略 | 状态 |
|---|---|---|---|---|---|---|---|---|
| INF-01 | 初始化后端工程 | 技术约束文档 | FastAPI 项目骨架 | 无 | 可启动主应用 | 结构混乱 | 保留最小骨架 | DONE |
| INF-02 | 初始化前端工程 | 技术约束文档 | Vue3+Vite+TS 工程 | 无 | `npm run build` 成功 | 依赖冲突 | 回退到锁定版本 | DONE |
| INF-03 | Docker 化基础 | Docker 规范 | backend Dockerfile | INF-01 | 镜像可构建 | 包版本不兼容 | 锁定依赖版本 | DONE |
| INF-04 | 一键编排 | 部署需求 | docker-compose | INF-03 | 一条命令启动服务 | 容器网络问题 | 本机分服务启动 | IN_PROGRESS |

## 2. 认证与 RBAC
| ID | 任务 | 输入 | 输出 | 依赖 | 验收标准 | 风险 | 回滚策略 | 状态 |
|---|---|---|---|---|---|---|---|---|
| AUTH-01 | 登录接口 | 用户模型、JWT 规则 | `/api/auth/login` | INF-01 | 正确签发 token | 密码校验漏洞 | 关闭外部入口并热修复 | DONE |
| AUTH-02 | 当前用户接口 | JWT token | `/api/users/me` | AUTH-01 | 返回用户信息 | token 解析失败 | 强制重新登录 | DONE |
| AUTH-03 | RBAC 依赖 | 角色定义 | 权限守卫函数 | AUTH-01 | 共享库写权限受控 | 误放权 | 默认拒绝策略 | DONE |
| AUTH-04 | 用户管理 API | 管理员权限 | 用户 CRUD | AUTH-03 | 管理员可管理用户 | 权限升级风险 | 审计并禁用接口 | DONE |

## 3. Provider 适配层
| ID | 任务 | 输入 | 输出 | 依赖 | 验收标准 | 风险 | 回滚策略 | 状态 |
|---|---|---|---|---|---|---|---|---|
| PROV-01 | Provider 配置 CRUD | Provider 模型 | `/api/providers/*` | AUTH-03 | 可增删改查 | 配置污染 | 加 owner 过滤 | DONE |
| PROV-02 | API Key 加密存储 | secret key | 加密/解密工具 | PROV-01 | 落库密文 | 密钥丢失 | 提供密钥轮换文档 | DONE |
| PROV-03 | 模型验证接口 | Provider 输入 | `/api/models/validate` | PROV-01 | 返回 valid/message | 误判可用性 | 提示“格式验证”级别 | DONE |
| PROV-04 | 插件化适配器 | Provider 协议 | openai/anthropic/gemini/openai_compatible | PROV-01 | 可统一调用 chat/embed/rerank | 第三方 API 变更 | 适配器单独热更新 | DONE |

## 4. 知识库与索引
| ID | 任务 | 输入 | 输出 | 依赖 | 验收标准 | 风险 | 回滚策略 | 状态 |
|---|---|---|---|---|---|---|---|---|
| KB-01 | 知识库创建/列表 | owner 规则 | `/api/kb/libraries` | AUTH-03 | 私有/共享可见性正确 | 越权读取 | 双重权限校验 | DONE |
| KB-02 | 文本上传索引 | 文件上传 | `/api/kb/files/upload` | KB-01 | 上传即索引 | 编码异常 | 按编码回退解码 | DONE |
| KB-03 | 目录同步 | 目录路径 | `/api/kb/files/sync-directory` | KB-01 | 目录文件可批量索引 | 目录越界 | 限制在 `KB_SYNC_ROOT` | DONE |
| KB-04 | 重建索引 | 库 ID | `/api/kb/index/rebuild` | KB-01 | 可重建并更新任务状态 | 大文件耗时 | 后续异步队列化 | DONE |
| KB-05 | 任务状态查询 | task id | `/api/kb/tasks/{id}` | KB-03 | 状态可追踪 | 长任务中断 | 标记 failed | DONE |
| KB-06 | 知识库编辑与文件管理 | 库/文件 ID | 更新归属与标签、文件删除与列表 | KB-01 | 管理闭环可用 | 误删风险 | 二次确认 + 审计 | DONE |

## 5. RAG 与聊天
| ID | 任务 | 输入 | 输出 | 依赖 | 验收标准 | 风险 | 回滚策略 | 状态 |
|---|---|---|---|---|---|---|---|---|
| CHAT-01 | 会话管理 | 用户输入 | `/api/chat/sessions*` | AUTH-03 | 会话可创建与列表 | 会话归属错乱 | user_id 强绑定 | DONE |
| CHAT-02 | 混合检索 | query + library_ids | vector+keyword 结果 | KB-02 | TopK 有序输出 | 召回不稳 | 调整权重/阈值 | DONE |
| CHAT-03 | 可选重排 | use_rerank | rerank 结果 | CHAT-02, PROV-04 | 开关生效 | 重排耗时 | 超时降级 | DONE |
| CHAT-04 | SSE 流式聊天 | message payload | `/api/chat/sessions/{id}/messages` | CHAT-01 | 前端可见增量输出 | SSE 断连 | 回退非流式 | DONE |
| CHAT-05 | 引用来源展示 | 检索结果 | citations | CHAT-02 | 默认显示可关闭 | 引用错位 | 回退原始片段 | DONE |

## 6. 前端 GUI
| ID | 任务 | 输入 | 输出 | 依赖 | 验收标准 | 风险 | 回滚策略 | 状态 |
|---|---|---|---|---|---|---|---|---|
| FE-01 | 登录页与鉴权流 | auth API | `/login` + 路由守卫 | AUTH-01 | 登录后可进入系统 | token 失效处理 | 自动登出 | DONE |
| FE-02 | 仪表盘 | 基础 API | `/` 页面 | FE-01 | 指标可展示 | 请求失败 | 友好提示 | DONE |
| FE-03 | 模型配置页 | provider API | `/providers` 页面 | PROV-01 | 可创建/验证/删除 | 表单误填 | 增加校验提示 | DONE |
| FE-04 | 知识库页 | kb API | `/knowledge-base` 页面 | KB-01 | 可创建、上传、同步、重建 | 目录参数错误 | 错误提示与重试 | DONE |
| FE-05 | 聊天页 | chat API + SSE | `/chat` 页面 | CHAT-04 | 可流式对话并看引用 | 流式解析异常 | 回退非流式接口 | DONE |
| FE-06 | 系统设置页 | 本地存储 | `/settings` 页面 | FE-01 | 偏好可保存 | 配置失效 | 默认值兜底 | DONE |
| FE-07 | 管理员用户管理页 | admin API | 在设置页完成用户管理 | AUTH-04 | 可创建/禁用/切换角色 | 越权操作 | 仅 admin 可见 | DONE |

## 7. 测试与质量
| ID | 任务 | 输入 | 输出 | 依赖 | 验收标准 | 风险 | 回滚策略 | 状态 |
|---|---|---|---|---|---|---|---|---|
| QA-01 | 后端核心单测 | 安全/算法函数 | pytest 用例 | INF-01 | 测试可执行 | 本机无 pytest | 文档注明环境安装 | DONE |
| QA-02 | 前端类型检查与打包 | TS/Vite | `npm run build` | FE-01..06 | 构建成功 | 大包体警告 | 后续按路由分包 | DONE |
| QA-03 | 后端 API 自动化 | TestClient + DB | API 集成测试 | CHAT-05 | 关键 API 覆盖 | 测试依赖重 | 分阶段补齐 | TODO |
| QA-04 | 安全回归测试 | RBAC/Key 加密 | 检查脚本 | AUTH-03 | 关键路径通过 | 漏测 | 加 CI 阶段门禁 | TODO |

## 8. 部署与运维
| ID | 任务 | 输入 | 输出 | 依赖 | 验收标准 | 风险 | 回滚策略 | 状态 |
|---|---|---|---|---|---|---|---|---|
| OPS-01 | 本机运行指南 | 环境参数 | README 说明 | INF-01, INF-02 | 可按步骤启动 | 环境差异 | 提供示例 .env | DONE |
| OPS-02 | Docker 一键部署 | compose 配置 | `docker-compose.yml` | INF-04 | 启动后可访问前后端 | 端口冲突 | 可配置端口映射 | IN_PROGRESS |
| OPS-03 | 基础监控/日志策略 | 日志输出 | 运维文档 | OPS-01 | 能定位请求失败 | 日志不足 | 增加 trace id | TODO |
