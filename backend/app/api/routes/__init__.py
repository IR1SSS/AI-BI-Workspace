from fastapi import APIRouter

from app.api.routes import (
    chat_routes,
    dashboard_routes,
    dataset_routes,
    health_routes,
    job_routes,
    llm_routes,
)

api_router = APIRouter()
api_router.include_router(health_routes.router)
api_router.include_router(dataset_routes.router)
api_router.include_router(dashboard_routes.router)
api_router.include_router(job_routes.router)
api_router.include_router(llm_routes.router)
api_router.include_router(chat_routes.router)
