#!/bin/sh
set -eu

MAX_RETRIES="${DB_WAIT_MAX_RETRIES:-60}"
SLEEP_SECONDS="${DB_WAIT_SLEEP_SECONDS:-2}"

echo "[backend] waiting for database..."
retry=0
while ! python - <<'PY'
from sqlalchemy import create_engine, text
from app.core.config import get_settings

engine = create_engine(get_settings().database_url)
with engine.connect() as conn:
    conn.execute(text("SELECT 1"))
PY
do
  retry=$((retry + 1))
  if [ "$retry" -ge "$MAX_RETRIES" ]; then
    echo "[backend] database is not ready after ${MAX_RETRIES} retries, abort."
    exit 1
  fi
  sleep "$SLEEP_SECONDS"
done

echo "[backend] running database initialization..."
python scripts/init_db.py

# 预下载 embedding 模型（如果配置了本地 embedding）
if [ "${EMBEDDING_BACKEND:-local}" = "local" ] && [ -n "${EMBEDDING_MODEL_NAME:-}" ]; then
  echo "[backend] pre-downloading embedding model: ${EMBEDDING_MODEL_NAME}..."
  python - <<'PY'
import os
model_name = os.environ.get('EMBEDDING_MODEL_NAME', 'BAAI/bge-m3')
try:
    from sentence_transformers import SentenceTransformer
    print(f"[backend] downloading {model_name}...")
    SentenceTransformer(model_name)
    print(f"[backend] model {model_name} ready")
except Exception as e:
    print(f"[backend] model download failed (will use fallback): {e}")
PY
fi

echo "[backend] starting uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
