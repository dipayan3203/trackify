import logging
from urllib.parse import quote_plus

import httpx
from sqlalchemy import select

from app.config import settings
from app.models.postgres import Job
from app.services.postgres import get_async_session

logger = logging.getLogger("trackify.airtable")

AIRTABLE_BASE_URL = "https://api.airtable.com/v0"


def _build_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }


def _build_record_payload(job: Job) -> dict:
    return {
        "fields": {
            "Title": job.title,
            "Company": job.company,
            "URL": job.url,
            "Score": job.score,
            "Status": job.status.value,
            "Created At": job.created_at.isoformat() if job.created_at else None,
        }
    }


async def sync_job_to_airtable(job: Job) -> None:
    """Create or update a single Airtable record for a job."""
    escaped_url = job.url.replace("'", "\\'")
search_url = f"{table_url}?filterByFormula={{URL}}='{escaped_url}'"
    payload = _build_record_payload(job)
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(search_url, headers=_build_headers())
            response.raise_for_status()
            records = response.json().get("records", [])
            if records:
                record_id = records[0]["id"]
                await client.patch(f"{table_url}/{record_id}", json=payload, headers=_build_headers())
                logger.info("Updated Airtable record for job %s", job.id)
            else:
                await client.post(table_url, json=payload, headers=_build_headers())
                logger.info("Created Airtable record for job %s", job.id)
        except httpx.HTTPError as exc:
            logger.warning("Airtable sync failed for job %s: %s", job.id, exc)


async def sync_all_jobs() -> None:
    """Sync all jobs from PostgreSQL to Airtable."""
    session = get_async_session()
    stmt = select(Job)
    result = await session.execute(stmt)
    jobs = result.scalars().all()
    for job in jobs:
        await sync_job_to_airtable(job)
