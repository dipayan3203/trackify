from pathlib import Path
from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    DATABASE_URL: str = Field(..., env="DATABASE_URL")
    MONGO_URI: str = Field(..., env="MONGO_URI")
    REDIS_URL: str = Field(..., env="REDIS_URL")

    AWS_ACCESS_KEY_ID: str = Field(..., env="AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY: str = Field(..., env="AWS_SECRET_ACCESS_KEY")
    AWS_REGION: str = Field(..., env="AWS_REGION")
    AWS_S3_BUCKET: str = Field(..., env="AWS_S3_BUCKET")

    OPENAI_API_KEY: str = Field(..., env="OPENAI_API_KEY")
    AIRTABLE_API_KEY: str = Field(..., env="AIRTABLE_API_KEY")
    AIRTABLE_BASE_ID: str = Field(..., env="AIRTABLE_BASE_ID")
    AIRTABLE_TABLE_NAME: str = Field(..., env="AIRTABLE_TABLE_NAME")

    API_KEY: str = Field(..., env="API_KEY")
    JOB_URLS: str = Field(default="", env="JOB_URLS")
    TRACKIFY_API_URL: str = Field(..., env="TRACKIFY_API_URL")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
