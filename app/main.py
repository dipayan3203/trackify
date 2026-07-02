import logging
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.routers import jobs, matches, resume
from app.services.cache import get_redis
from app.services.mongo import get_mongo_client
from app.services.postgres import get_postgres_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("trackify")

app = FastAPI(title="Trackify", description="AI-powered job application tracker.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        api_key = request.headers.get("X-API-Key")
        if request.url.path.startswith("/health"):
            return await call_next(request)

        if api_key != settings.API_KEY:
            logger.warning("Unauthorized request with missing or invalid X-API-Key")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid API Key"},
            )

        return await call_next(request)
    


app.add_middleware(APIKeyMiddleware)
app.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
app.include_router(matches.router, prefix="/matches", tags=["matches"])
app.include_router(resume.router, prefix="/resume", tags=["resume"])


@app.on_event("startup")
async def startup_event():
    logger.info("Starting Trackify API")
    await get_postgres_engine()
    await get_redis()
    await get_mongo_client()
    logger.info("All services connected")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down Trackify API")
    await get_postgres_engine(close=True)
    await get_redis(close=True)
    await get_mongo_client(close=True)
    logger.info("All services disconnected")


@app.get("/health")
async def health_check():
    return JSONResponse({"status": "ok", "timestamp": datetime.utcnow().isoformat()})
