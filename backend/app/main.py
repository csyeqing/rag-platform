from __future__ import annotations

from pathlib import Path
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import ORJSONResponse

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.init_db import init_db

settings = get_settings()
configure_logging()
logger = get_logger('app.request')
app = FastAPI(title=settings.app_name, default_response_class=ORJSONResponse)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.parsed_cors_origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.on_event('startup')
def on_startup() -> None:
    Path(settings.storage_root).mkdir(parents=True, exist_ok=True)
    Path(settings.kb_sync_root).mkdir(parents=True, exist_ok=True)
    init_db()


@app.middleware('http')
async def request_logging_middleware(request: Request, call_next):
    request_id = request.headers.get('X-Request-ID', str(uuid4()))
    started = perf_counter()
    response = await call_next(request)
    elapsed_ms = round((perf_counter() - started) * 1000, 2)
    response.headers['X-Request-ID'] = request_id
    logger.info(
        'request_id=%s method=%s path=%s status=%s elapsed_ms=%s',
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


@app.get('/health')
def health() -> dict[str, str]:
    return {'status': 'ok'}


app.include_router(api_router)
