#!/bin/sh
set -eu

# 获取脚本所在目录（即 deploy 目录）
DEPLOY_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ENV_FILE="${1:-$DEPLOY_DIR/.env.server}"
PROFILE="${2:-full}"

# 检查环境变量文件是否存在
if [ ! -f "$ENV_FILE" ]; then
  echo "Missing env file: $ENV_FILE"
  echo "Copy template and edit it first:"
  echo "  cp $DEPLOY_DIR/.env.server.example $DEPLOY_DIR/.env.server"
  exit 1
fi

echo "[deploy] using env file: $ENV_FILE"
echo "[deploy] using profile: $PROFILE"

# 直接使用当前目录下的 docker-compose.yml 启动
# 移除 --build，因为我们使用预构建好的镜像
docker compose --env-file "$ENV_FILE" -f "$DEPLOY_DIR/docker-compose.yml" --profile "$PROFILE" up -d

echo "[deploy] done"
