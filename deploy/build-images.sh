#!/bin/bash
# 本地构建并导出镜像（用于离线部署）
# 使用方法: ./deploy/build-images.sh [output_dir]

set -e

OUTPUT_DIR="${1:-./deploy/images}"
PROJECT_NAME="rag"
VERSION="${VERSION:-$(git describe --tags --always --dirty 2>/dev/null || echo 'latest')}"

echo "=== 构建镜像 ==="
echo "项目: ${PROJECT_NAME}"
echo "版本: ${VERSION}"
echo "输出目录: ${OUTPUT_DIR}"
echo ""

# 创建输出目录
mkdir -p "${OUTPUT_DIR}"

# 构建后端镜像（包含 bge-m3 模型）
echo "[1/3] 构建后端镜像（包含 bge-m3 模型）..."
docker build \
  --build-arg EMBEDDING_MODEL_NAME=BAAI/bge-m3 \
  -t "${PROJECT_NAME}-backend:${VERSION}" \
  -t "${PROJECT_NAME}-backend:latest" \
  ./backend

# 构建前端镜像
echo "[2/3] 构建前端镜像..."
docker build \
  --build-arg VITE_API_BASE_URL=/api \
  -t "${PROJECT_NAME}-frontend:${VERSION}" \
  -t "${PROJECT_NAME}-frontend:latest" \
  ./frontend

# 拉取基础镜像
echo "[3/3] 拉取基础镜像..."
docker pull pgvector/pgvector:pg16
docker pull nginx:alpine

# 导出镜像
echo ""
echo "=== 导出镜像 ==="
echo "这可能需要几分钟..."

docker save -o "${OUTPUT_DIR}/${PROJECT_NAME}-backend-${VERSION}.tar" \
  "${PROJECT_NAME}-backend:${VERSION}"
echo "✓ 后端镜像已导出: ${OUTPUT_DIR}/${PROJECT_NAME}-backend-${VERSION}.tar"

docker save -o "${OUTPUT_DIR}/${PROJECT_NAME}-frontend-${VERSION}.tar" \
  "${PROJECT_NAME}-frontend:${VERSION}"
echo "✓ 前端镜像已导出: ${OUTPUT_DIR}/${PROJECT_NAME}-frontend-${VERSION}.tar"

docker save -o "${OUTPUT_DIR}/postgres-pgvector.tar" pgvector/pgvector:pg16
echo "✓ PostgreSQL 镜像已导出: ${OUTPUT_DIR}/postgres-pgvector.tar"

docker save -o "${OUTPUT_DIR}/nginx-alpine.tar" nginx:alpine
echo "✓ Nginx 镜像已导出: ${OUTPUT_DIR}/nginx-alpine.tar"

# 计算总大小
TOTAL_SIZE=$(du -sh "${OUTPUT_DIR}" | cut -f1)
echo ""
echo "=== 构建完成 ==="
echo "镜像文件位于: ${OUTPUT_DIR}"
echo "总大小: ${TOTAL_SIZE}"
echo ""
echo "下一步："
echo "  1. 将 ${OUTPUT_DIR} 目录上传到服务器"
echo "  2. 在服务器上执行: ./deploy/load-images.sh <images_dir>"
