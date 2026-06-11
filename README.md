# Trackify

Trackify is an AI-powered job application tracker for organizing job leads, scoring fit, syncing to Airtable, and storing interview notes.

## Features

- Job tracking with status, AI fit score, and talking points
- Resume embedding pipeline using OpenAI embeddings
- MongoDB notes storage for interview rounds and job notes
- Redis caching for match results and resume status
- Airtable sync for tracking job records externally
- Lambda scraper for automated job board ingestion
- Local development with Docker Compose

## Architecture

- `api` service: FastAPI backend with PostgreSQL, Redis, MongoDB
- `postgres`: job metadata and resume embedding vectors in PGVector
- `redis`: caching for job match results and resume state
- `mongo`: notes storage for interview notes
- `lambda`: EventBridge-driven scraper that posts jobs to the API

Text-based architecture:

```
[Resume PDF] --> S3 --> Trackify API --> PostgreSQL resume_chunks
               \                        |
                --> RAG scoring pipeline -> Redis cache
                                         \-> Airtable sync

[Job Board URLs] --> Lambda scraper --> Trackify API /jobs

[MongoDB] <-- job notes
```

## Local setup

1. Copy the example env file:

   ```bash
   cp .env.example .env
   ```

2. Update `.env` with your credentials.

3. Build and start services:

   ```bash
   docker-compose up --build
   ```

4. Access the API at `http://localhost:8000`.

## API Endpoints

| Method | Path | Description |
| --- | --- | --- |
| GET | `/health` | Health check |
| POST | `/jobs` | Create a new job and trigger RAG scoring |
| GET | `/jobs` | List jobs with optional status/min_score filters |
| GET | `/jobs/{id}` | Get job details |
| PATCH | `/jobs/{id}/status` | Update job status and sync Airtable |
| POST | `/jobs/{id}/notes` | Add a note for a job |
| GET | `/jobs/{id}/notes` | Retrieve notes for a job |
| POST | `/resume/upload` | Upload a resume PDF to S3 and start embedding |
| GET | `/resume/status` | Check resume embedding status |
| GET | `/matches` | Get top 10 jobs by AI fit score |

> All requests must include header `X-API-Key: <API_KEY>` except `/health`.

## Lambda deployment

1. Package `lambda/scraper_handler.py` with dependencies.
2. Create an AWS Lambda function using Python 3.11.
3. Set environment variables: `JOB_URLS`, `TRACKIFY_API_URL`, `API_KEY`.
4. Configure EventBridge rule with cron expression `cron(0 0 */1 * ? *)` or similar for daily runs.
5. Use the lambda handler `scraper_handler.lambda_handler`.

## n8n workflow setup

To automate job tracking and alerts with n8n:

1. Create an HTTP Request node for Trackify API endpoints.
2. Add header `X-API-Key` using the same key from `.env`.
3. Use Webhook or Schedule trigger for periodic polling.
4. Add nodes to:
   - Create or update jobs in Trackify
   - Fetch `/matches` and send Slack or email alerts
   - Create MongoDB notes via `/jobs/{id}/notes`

## Environment variables

| Variable | Description |
| --- | --- |
| `DATABASE_URL` | Async PostgreSQL connection string |
| `MONGO_URI` | MongoDB connection URI |
| `REDIS_URL` | Redis connection URL |
| `AWS_ACCESS_KEY_ID` | AWS API key ID |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key |
| `AWS_REGION` | AWS region for S3 |
| `AWS_S3_BUCKET` | S3 bucket name for resume uploads |
| `OPENAI_API_KEY` | OpenAI API key for embeddings and generation |
| `AIRTABLE_API_KEY` | Airtable API key |
| `AIRTABLE_BASE_ID` | Airtable base ID |
| `AIRTABLE_TABLE_NAME` | Airtable table name |
| `API_KEY` | API authentication key for X-API-Key header |
| `JOB_URLS` | Comma-separated job board URLs for Lambda scraper |
| `TRACKIFY_API_URL` | Trackify API base URL for Lambda scraper |
