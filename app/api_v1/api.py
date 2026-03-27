from fastapi import APIRouter
from app.api_v1.endpoints import analysis, auth

api_router = APIRouter()
api_router.include_router(analysis.router, prefix="/analysis", tags=["Analysis"])
api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
