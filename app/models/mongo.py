from datetime import datetime
from pydantic import BaseModel, Field


class JobNote(BaseModel):
    job_id: str = Field(..., description="ID of the related job")
    note: str = Field(..., description="Interview note or journal entry")
    interview_round: str | None = Field(None, description="Optional interview round")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class JobNoteInDB(JobNote):
    id: str | None = Field(None, alias="_id")

    model_config = {
        "populate_by_name": True,
    }
