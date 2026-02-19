from fastapi import APIRouter

from app.api.routes import admin_users, auth, chat, kb, models, providers, users

api_router = APIRouter(prefix='/api')
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(admin_users.router)
api_router.include_router(providers.router)
api_router.include_router(models.router)
api_router.include_router(kb.router)
api_router.include_router(chat.router)
