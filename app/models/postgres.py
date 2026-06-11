import enum
import uuid
from sqlalchemy import Column, String, Text, Float, DateTime, JSON, Enum as SAEnum, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from pgvector.sqlalchemy import Vector

Base = declarative_base()


class JobStatus(str, enum.Enum):
    SAVED = "saved"
    APPLIED = "applied"
    INTERVIEW = "interview"
    REJECTED = "rejected"
    OFFER = "offer"


class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    company = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    url = Column(String(1024), nullable=False)
    location = Column(String(255), nullable=True)
    salary = Column(String(255), nullable=True)
    score = Column(Float, nullable=True)
    talking_points = Column(JSON, nullable=True)
    status = Column(SAEnum(JobStatus, name="job_status"), nullable=False, default=JobStatus.SAVED)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ResumeChunk(Base):
    __tablename__ = "resume_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chunk_text = Column(Text, nullable=False)
    embedding = Column(Vector(1536), nullable=False)
