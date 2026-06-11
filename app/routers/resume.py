import asyncio
import logging
import uuid
from datetime import datetime

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.config import settings
from app.services.cache import get_resume_status, set_resume_status
from app.services.rag_pipeline import embed_resume

logger = logging.getLogger("trackify.resume")
router = APIRouter()


class ResumeUploadResponse(BaseModel):
    message: str
    s3_url: str


@router.post("/upload", response_model=ResumeUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_resume(file: UploadFile = File(...), background_tasks: BackgroundTasks = BackgroundTasks):
    """Upload a resume PDF to S3 and start the embedding pipeline."""
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only PDF uploads are supported")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")

    key = f"resumes/{uuid.uuid4()}.pdf"
    s3_client = boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )
    try:
        await asyncio.to_thread(
            s3_client.put_object,
            Bucket=settings.AWS_S3_BUCKET,
            Key=key,
            Body=file_bytes,
            ContentType="application/pdf",
        )
    except (BotoCoreError, ClientError) as exc:
        logger.error("S3 upload failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to upload resume")

    s3_url = f"https://{settings.AWS_S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/{key}"
    background_tasks.add_task(embed_resume, s3_url)
    await set_resume_status(0, datetime.utcnow().isoformat())
    logger.info("Uploaded resume to %s", s3_url)
    return {"message": "Resume uploaded and embedding started", "s3_url": s3_url}


@router.get("/status")
async def resume_status():
    """Return the current resume embedding status."""
    status_data = await get_resume_status()
    return {
        "chunks_embedded": status_data.get("count", 0),
        "last_uploaded_at": status_data.get("last_uploaded_at"),
    }
