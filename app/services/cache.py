import json
import logging
from redis.asyncio import Redis

from app.config import settings

logger = logging.getLogger("trackify.cache")
redis_client: Redis | None = None


async def get_redis(close: bool = False) -> Redis | None:
    """Initialize or close the Redis connection."""
    global redis_client

    if close:
        if redis_client is not None:
            await redis_client.close()
            redis_client = None
        return None

    if redis_client is None:
        redis_client = Redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
        await redis_client.ping()
        logger.info("Connected to Redis")

    return redis_client


async def get_cached_match(job_id: str) -> dict | None:
    """Retrieve cached match metadata for a job."""
    client = await get_redis()
    cached = await client.get(f"job_match:{job_id}")
    if cached:
        return json.loads(cached)
    return None


async def set_cached_match(job_id: str, data: dict, ttl: int = 86400) -> None:
    """Cache match metadata for a job."""
    client = await get_redis()
    await client.set(f"job_match:{job_id}", json.dumps(data), ex=ttl)


async def invalidate_match(job_id: str) -> None:
    """Invalidate cached match metadata for a job."""
    client = await get_redis()
    await client.delete(f"job_match:{job_id}")


async def set_resume_status(count: int, last_uploaded_at: str) -> None:
    """Store resume status values in Redis."""
    client = await get_redis()
    await client.hset("resume_status", mapping={"count": str(count), "last_uploaded_at": last_uploaded_at})


async def get_resume_status() -> dict:
    """Get resume upload and embedding status."""
    client = await get_redis()
    status = await client.hgetall("resume_status")
    return {"count": int(status.get("count", 0)), "last_uploaded_at": status.get("last_uploaded_at")}
