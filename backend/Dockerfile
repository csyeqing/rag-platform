FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# 支持构建时指定 pip 源
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=mirrors.tencentyun.com
RUN pip config set global.index-url ${PIP_INDEX_URL} && \
    pip config set global.trusted-host ${PIP_TRUSTED_HOST} && \
    pip install --no-cache-dir --upgrade pip

COPY requirements.txt ./
# 分步安装：先单独安装 CPU 版 PyTorch，避免下载 CUDA 版本
RUN pip install --no-cache-dir torch>=2.0.0 --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# 预下载 embedding 模型（构建时下载，避免运行时下载）
# 优化：默认不在构建时下载大模型，建议运行时挂载宿主机 ~/.cache/huggingface 目录
ARG EMBEDDING_MODEL_NAME=BAAI/bge-m3
# 支持构建时指定 HF 镜像
ARG HF_ENDPOINT=https://huggingface.co
ENV EMBEDDING_MODEL_NAME=${EMBEDDING_MODEL_NAME}
ENV HF_HOME=/root/.cache/huggingface
ENV HF_ENDPOINT=${HF_ENDPOINT}

# RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL_NAME}')"

COPY app ./app
COPY scripts ./scripts
COPY .env.example ./.env.example
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
