#!/bin/bash
# 服务器端加载镜像
# 使用方法: ./deploy/load-images.sh <images_dir>

set -e

IMAGES_DIR="${1:-./images}"

if [ ! -d "${IMAGES_DIR}" ]; then
  echo "错误: 镜像目录不存在: ${IMAGES_DIR}"
  exit 1
fi

echo "=== 加载镜像 ==="
echo "镜像目录: ${IMAGES_DIR}"
echo ""

# 加载镜像
for tar_file in "${IMAGES_DIR}"/*.tar; do
  if [ -f "$tar_file" ]; then
    echo "加载: $tar_file"
    docker load -i "$tar_file"
  fi
done

echo ""
echo "=== 已加载镜像列表 ==="
docker images | grep -E "rag-|pgvector|nginx"

echo ""
echo "镜像加载完成，可以执行部署: ./deploy/up.sh deploy/.env.server"
