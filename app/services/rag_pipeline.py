import asyncio
import logging
import math
from datetime import datetime
from urllib.parse import urlparse

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from langchain.chat_models import ChatOpenAI
from langchain.embeddings import OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from sqlalchemy import select

from app.config import settings
from app.models.postgres import Job, ResumeChunk
from app.services.cache import set_cached_match, set_resume_status
from app.services.postgres import get_async_session

logger = logging.getLogger("trackify.rag")


def _parse_s3_url(s3_url: str) -> tuple[str, str]:
    """Extract bucket and key from an S3 URL."""
    parsed = urlparse(s3_url)
    bucket = parsed.netloc.split(".")[0]
    key = parsed.path.lstrip("/")
    return bucket, key


async def _download_pdf_from_s3(s3_url: str) -> bytes:
    """Download a file from S3 to memory."""
    bucket, key = _parse_s3_url(s3_url)
    s3_client = boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )

    try:
        response = await asyncio.to_thread(s3_client.get_object, Bucket=bucket, Key=key)
        return response["Body"].read()
    except (BotoCoreError, ClientError) as exc:
        logger.error("Failed to download resume from S3: %s", exc)
        raise


def _parse_talking_points(output: str) -> list[str]:
    """Convert an LLM response into a list of talking points."""
    lines = [line.strip(" -\n\r") for line in output.splitlines() if line.strip()]
    points = [line for line in lines if len(line) > 0]
    if not points:
        return [output.strip()]
    return points[:3]


async def _generate_talking_points(job_title: str, company: str, job_description: str, score: float) -> list[str]:
    """Generate tailored talking points with LangChain."""
    prompt = (
        "Create 3 concise, highly specific talking points for a candidate applying to this job. "
        f"Job title: {job_title}. Company: {company}. "
        f"Score: {score:.1f}. Job description: {job_description}"
    )
    llm = ChatOpenAI(openai_api_key=settings.OPENAI_API_KEY, temperature=0.2, model_name="gpt-3.5-turbo")
    try:
        response = await asyncio.to_thread(llm.predict, prompt)
        return _parse_talking_points(response)
    except Exception as exc:
        logger.warning("Failed to generate talking points: %s", exc)
        return [
            "Review the job description and highlight the most relevant experience.",
            "Mention how your background aligns with the company mission.",
            "Prepare concrete examples that demonstrate your fit for the role.",
        ]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    numerator = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return numerator / (norm_a * norm_b)


async def embed_resume(s3_url: str) -> int:
    """Download a resume from S3, chunk the text, embed it, and store the vectors."""
    logger.info("Embedding resume from %s", s3_url)
    pdf_bytes = await _download_pdf_from_s3(s3_url)
    text = pdf_bytes.decode("latin-1", errors="ignore")
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
    chunks = splitter.split_text(text)
    if not chunks:
        logger.warning("No text extracted from resume %s", s3_url)
        return 0

    embeddings = OpenAIEmbeddings(openai_api_key=settings.OPENAI_API_KEY)
    embedded_chunks = await asyncio.to_thread(embeddings.embed_documents, chunks)
    session = get_async_session()
    try:
        async with session.begin():
            for chunk_text, embedding in zip(chunks, embedded_chunks):
                resume_chunk = ResumeChunk(chunk_text=chunk_text, embedding=embedding)
                session.add(resume_chunk)
        await set_resume_status(len(chunks), datetime.utcnow().isoformat())
        logger.info("Stored %s resume chunks", len(chunks))
        return len(chunks)
    except Exception as exc:
        logger.error("Failed to store resume chunks: %s", exc)
        raise


async def score_job(job_id: str, job_description: str) -> dict:
    """Score a job against the embedded resume and update the job record."""
    logger.info("Scoring job %s", job_id)
    session = get_async_session()
    stmt = select(Job).where(Job.id == job_id)
    result = await session.execute(stmt)
    job = result.scalar_one_or_none()
    if job is None:
        raise ValueError(f"Job {job_id} not found")

    embedder = OpenAIEmbeddings(openai_api_key=settings.OPENAI_API_KEY)
    job_vector = await asyncio.to_thread(embedder.embed_query, job_description)
    chunk_stmt = select(ResumeChunk)
    result = await session.execute(chunk_stmt)
    chunks = result.scalars().all()
    if not chunks:
        score = 0.0
        talking_points = []
    else:
        similarities = [
            _cosine_similarity(job_vector, chunk.embedding) for chunk in chunks if chunk.embedding is not None
        ]
        average_similarity = float(sum(similarities) / len(similarities)) if similarities else 0.0
        score = max(0.0, min(100.0, average_similarity * 100.0))
        talking_points = await _generate_talking_points(job.title, job.company, job.description, score)

    try:
        async with session.begin():
            job.score = round(score, 2)
            job.talking_points = talking_points
            session.add(job)
        await set_cached_match(job_id, {"score": job.score, "talking_points": talking_points})
        logger.info("Updated score for job %s to %s", job_id, job.score)
        return {"score": job.score, "talking_points": talking_points}
    except Exception as exc:
        logger.error("Failed to persist matching data: %s", exc)
        raise
