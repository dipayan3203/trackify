import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.models.postgres import Job
from app.services.postgres import get_async_session

logger = logging.getLogger("trackify.matches")
router = APIRouter()


@router.get("/")
async def list_matches():
    """Return top jobs ranked by AI fit score."""
    session = get_async_session()
    stmt = select(Job).order_by(Job.score.desc().nullslast()).limit(10)
    try:
        result = await session.execute(stmt)
        jobs = result.scalars().all()
        return [
            {
                "id": str(job.id),
                "title": job.title,
                "company": job.company,
                "score": job.score,
                "talking_points": job.talking_points,
                "status": job.status,
            }
            for job in jobs
        ]
    except SQLAlchemyError as exc:
        logger.error("Failed to load matches: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to load matches")
