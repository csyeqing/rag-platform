# 部署指南

## 部署模式

| 模式 | 说明 | 用途 |
|------|------|------|
| `dev` | 只启动数据库 | 本地开发（前后端命令行启动） |
| `full` | 启动所有服务 | 生产环境一键部署 |

---

## 本地开发（Apple M4 或其他开发机）

### 1. 启动数据库

```bash
cd /path/to/codex_demo
docker compose --profile dev up -d
```

### 2. 启动后端

```bash
cd backend
cp .env.example .env  # 首次需要
# 编辑 .env，确保数据库连接正确：
# DATABASE_URL=postgresql+psycopg://rag:rag@localhost:5432/rag_mvp

source .venv/bin/activate  # 或你的虚拟环境
pip install -r requirements.txt
python scripts/init_db.py   # 首次需要初始化数据库
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev
```

### 4. 访问应用

- 前端：http://localhost:5173
- 后端 API：http://localhost:8000/docs

---

## 生产部署（Ubuntu 服务器）

### 前置要求

- Ubuntu 20.04+ 或其他 Linux 发行版
- Docker 和 Docker Compose 已安装
- 至少 4GB 内存（推荐 8GB+，首次加载模型需要下载约 2GB）
- 开放 80 端口（或自定义端口）

### 快速部署

#### 1. 上传项目到服务器

```bash
# 方式一：使用 git
git clone <your-repo-url> /opt/rag
cd /opt/rag

# 方式二：使用 scp 上传
scp -r codex_demo user@server:/opt/rag
```

#### 2. 创建环境配置

```bash
cd /opt/rag/deploy
cp .env.server.example .env.server

# 编辑配置文件
nano .env.server
```

**必须修改的配置**：

```bash
# 数据库密码（必须修改）
POSTGRES_PASSWORD=your_secure_db_password

# JWT 密钥（必须修改，至少 32 字符）
SECRET_KEY=your_very_long_random_secret_key_at_least_32_characters

# 管理员密码（必须修改）
DEFAULT_ADMIN_PASSWORD=your_admin_password

# 允许的 CORS 来源（添加你的服务器地址）
CORS_ORIGINS=["http://localhost","http://your-server-ip"]
```

#### 3. 启动服务

```bash
cd /opt/rag
./deploy/up.sh
# 或手动指定 profile
# docker compose --profile full up -d --build
```

首次启动会：
1. 构建前后端镜像
2. 下载 bge-m3 模型（约 2GB，首次需要几分钟）
3. 初始化数据库和管理员账号

#### 4. 验证部署

```bash
# 检查服务状态
docker compose ps

# 查看后端日志
docker compose logs -f backend

# 健康检查
curl http://localhost/health
```

## 访问应用

- **前端**：http://your-server-ip
- **登录**：使用配置的管理员账号

## 常用命令

```bash
# 查看日志
docker compose logs -f

# 重启服务
docker compose restart

# 停止服务
docker compose down

# 更新部署
git pull
docker compose up -d --build

# 查看资源使用
docker stats
```

## 数据备份

```bash
# 备份 PostgreSQL 数据库
docker exec rag_postgres pg_dump -U rag rag_mvp > backup_$(date +%Y%m%d).sql

# 恢复数据库
cat backup_20240101.sql | docker exec -i rag_postgres psql -U rag rag_mvp
```

## 故障排查

### 后端启动失败

```bash
# 查看详细日志
docker compose logs backend

# 常见问题：
# 1. 数据库连接失败 - 检查 POSTGRES_PASSWORD 配置
# 2. 模型下载失败 - 检查网络连接
```

### 前端无法访问

```bash
# 检查 Nginx 配置
docker compose logs nginx

# 检查端口占用
sudo netstat -tlnp | grep 80
```

### 模型加载问题

```bash
# 查看 embedding 服务日志
docker compose logs backend | grep -i embedding

# 如果模型加载失败，会自动使用 hash 回退
# 可以通过设置 EMBEDDING_BACKEND=hash 强制使用 hash 模式
```

## 生产环境建议

1. **HTTPS**：使用 Let's Encrypt 配置 SSL 证书
2. **防火墙**：只开放必要端口
3. **监控**：添加监控和告警
4. **备份**：设置定时数据库备份
5. **资源**：根据负载调整容器资源限制

## 使用 HTTPS（可选）

使用 Caddy 自动配置 HTTPS：

```yaml
# 添加到 docker-compose.yml
  caddy:
    image: caddy:alpine
    container_name: rag_caddy
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./deploy/Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
    networks:
      - rag_network
```

创建 `deploy/Caddyfile`：

```
your-domain.com {
    reverse_proxy /api/* backend:8000
    reverse_proxy frontend:80
}
```
