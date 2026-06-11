import logging
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.models.mongo import JobNote
from app.models.postgres import Job, JobStatus
from app.services.airtable_sync import sync_job_to_airtable
from app.services.mongo import get_notes_collection
from app.services.postgres import get_async_session
from app.services.rag_pipeline import score_job

logger = logging.getLogger("trackify.jobs")
router = APIRouter()


class JobCreate(BaseModel):
    title: str = Field(..., description="Job title")
    company: str = Field(..., description="Company name")
    description: str = Field(..., description="Job description")
    url: HttpUrl = Field(..., description="Job posting URL")
    location: Optional[str] = Field(None, description="Job location")
    salary: Optional[str] = Field(None, description="Job salary range")


class JobStatusUpdate(BaseModel):
    status: JobStatus = Field(..., description="Updated job status")


class JobResponse(BaseModel):
    id: uuid.UUID
    title: str
    company: str
    description: str
    url: str
    location: Optional[str]
    salary: Optional[str]
    score: Optional[float]
    talking_points: Optional[List[str]]
    status: JobStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class JobNoteCreate(BaseModel):
    note: str = Field(..., description="Note content")
    interview_round: Optional[str] = Field(None, description="Interview round")


class JobNoteResponse(BaseModel):
    id: str
    job_id: str
    note: str
    interview_round: Optional[str]
    timestamp: datetime


@router.post("/", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(job_request: JobCreate, background_tasks: BackgroundTasks):
    """Create a new job record and queue the AI scoring pipeline."""
    session = get_async_session()
    job = Job(
        title=job_request.title,
        company=job_request.company,
        description=job_request.description,
        url=str(job_request.url),
        location=job_request.location,
        salary=job_request.salary,
        status=JobStatus.SAVED,
    )
    try:
        async with session.begin():
            session.add(job)
            await session.flush()
            await session.refresh(job)
        background_tasks.add_task(score_job, str(job.id), job.description)
        logger.info("Created job %s and queued scoring", job.id)
        return job
    except SQLAlchemyError as exc:
        logger.error("Failed to create job: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to create job")


@router.get("/", response_model=List[JobResponse])
async def list_jobs(
    status: Optional[JobStatus] = None,
    min_score: Optional[float] = None,
    skip: int = 0,
    limit: int = 25,
):
    """List jobs with optional filtering and pagination."""
    stmt = select(Job)
    if status is not None:
        stmt = stmt.where(Job.status == status)
    if min_score is not None:
        stmt = stmt.where(Job.score >= min_score)
    stmt = stmt.offset(skip).limit(limit)
    try:
        async with get_async_session() as session:
            result = await session.execute(stmt)
            jobs = result.scalars().all()
        return jobs
    except SQLAlchemyError as exc:
        logger.error("Failed to list jobs: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to list jobs")


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: uuid.UUID):
    """Fetch a single job by ID."""
    stmt = select(Job).where(Job.id == job_id)
    try:
        async with get_async_session() as session:
            result = await session.execute(stmt)
            job = result.scalar_one_or_none()
    except SQLAlchemyError as exc:
        logger.error("Failed to query job: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to load job")

    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.patch("/{job_id}/status", response_model=JobResponse)
async def update_job_status(job_id: uuid.UUID, status_update: JobStatusUpdate, background_tasks: BackgroundTasks):
    """Update the job status and sync the record to Airtable."""
    session = get_async_session()
    stmt = select(Job).where(Job.id == job_id)
    result = await session.execute(stmt)
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    job.status = status_update.status
    try:
        async with session.begin():
            session.add(job)
            await session.flush()
            await session.refresh(job)
        background_tasks.add_task(sync_job_to_airtable, job)
        logger.info("Updated status for job %s to %s", job.id, job.status)
        return job
    except SQLAlchemyError as exc:
        logger.error("Failed to update job status: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to update status")


@router.post("/{job_id}/notes", response_model=JobNoteResponse, status_code=status.HTTP_201_CREATED)
async def add_job_note(job_id: uuid.UUID, note_request: JobNoteCreate):
    """Save a note for a job to MongoDB."""
    session = get_async_session()
    stmt = select(Job).where(Job.id == job_id)
    result = await session.execute(stmt)
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    collection = get_notes_collection()
    note_payload = JobNote(
        job_id=str(job_id),
        note=note_request.note,
        interview_round=note_request.interview_round,
    ).model_dump()
    try:
        inserted = await collection.insert_one(note_payload)
        logger.info("Inserted note for job %s", job_id)
        return JobNoteResponse(
            id=str(inserted.inserted_id),
            job_id=str(job_id),
            note=note_request.note,
            interview_round=note_request.interview_round,
            timestamp=note_payload["timestamp"],
        )
    except Exception as exc:
        logger.error("Failed to save job note: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to save note")


@router.get("/{job_id}/notes", response_model=List[JobNoteResponse])
async def get_job_notes(job_id: uuid.UUID):
    """Fetch all notes for a given job."""
    collection = get_notes_collection()
    try:
        cursor = collection.find({"job_id": str(job_id)}).sort("timestamp", -1)
        notes = []
        async for doc in cursor:
            notes.append(
                JobNoteResponse(
                    id=str(doc.get("_id")),
                    job_id=doc.get("job_id"),
                    note=doc.get("note"),
                    interview_round=doc.get("interview_round"),
                    timestamp=doc.get("timestamp"),
                )
            )
        return notes
    except Exception as exc:
        logger.error("Failed to fetch notes: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to fetch notes")
