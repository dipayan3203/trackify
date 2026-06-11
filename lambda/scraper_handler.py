import asyncio
import json
import logging
import os
import re
from html import unescape
from typing import Any

import httpx

logger = logging.getLogger("trackify.lambda")
logging.basicConfig(level=logging.INFO)

JOB_URLS_ENV = "JOB_URLS"
TRACKIFY_API_URL_ENV = "TRACKIFY_API_URL"
API_KEY_ENV = "API_KEY"


def extract_job_cards(html: str) -> list[dict[str, str]]:
    """Extract basic job fields from a job board HTML page."""
    jobs: list[dict[str, str]] = []
    snippets = re.findall(r"<article.*?</article>", html, re.DOTALL | re.IGNORECASE)
    if not snippets:
        snippets = re.findall(r"<div[^>]+class=[\"'].*?(?:job|position|listing).*?[\"'][^>]*>.*?</div>", html, re.DOTALL | re.IGNORECASE)

    for snippet in snippets[:5]:
        title_match = re.search(r"<h[1-6][^>]*>(.*?)</h[1-6]>", snippet, re.DOTALL | re.IGNORECASE)
        company_match = re.search(r"<div[^>]*class=[\"'].*?(?:company|employer).*?[\"'][^>]*>(.*?)</div>", snippet, re.DOTALL | re.IGNORECASE)
        url_match = re.search(r"<a[^>]+href=[\"']([^\"']+)[\"']", snippet, re.IGNORECASE)
        description_match = re.search(r"<p[^>]*>(.*?)</p>", snippet, re.DOTALL | re.IGNORECASE)

        title = unescape(title_match.group(1).strip()) if title_match else "Unknown role"
        company = unescape(company_match.group(1).strip()) if company_match else "Unknown company"
        url = url_match.group(1).strip() if url_match else ""
        description = unescape(re.sub(r"<[^>]+>", "", description_match.group(1).strip())) if description_match else ""

        if url:
            jobs.append({"title": title, "company": company, "description": description, "url": url})

    return jobs


async def post_job_to_trackify(client: httpx.AsyncClient, api_url: str, api_key: str, payload: dict[str, Any]) -> bool:
    """Send a single job payload to the Trackify API."""
    try:
        response = await client.post(
            f"{api_url.rstrip('/')}/jobs",
            json=payload,
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
            timeout=30.0,
        )
        response.raise_for_status()
        return True
    except Exception as exc:
        logger.warning("Failed to post job %s: %s", payload.get("url"), exc)
        return False


async def scrape_url(client: httpx.AsyncClient, url: str) -> list[dict[str, Any]]:
    """Fetch and scrape job data from a URL."""
    try:
        response = await client.get(url, timeout=30.0)
        response.raise_for_status()
        return extract_job_cards(response.text)
    except Exception as exc:
        logger.warning("Failed to scrape URL %s: %s", url, exc)
        return []


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, int]:
    """AWS Lambda entrypoint triggered by EventBridge."""
    job_urls = os.getenv(JOB_URLS_ENV, "")
    api_url = os.getenv(TRACKIFY_API_URL_ENV, "")
    api_key = os.getenv(API_KEY_ENV, "")

    if not job_urls or not api_url or not api_key:
        logger.error("Missing required environment variables for Lambda scraper")
        return {"scraped": 0, "posted": 0, "failed": 0}

    urls = [url.strip() for url in job_urls.split(",") if url.strip()]
    scraped = 0
    posted = 0
    failed = 0

    async def runner() -> None:
        nonlocal scraped, posted, failed
        async with httpx.AsyncClient() as client:
            for url in urls:
                jobs = await scrape_url(client, url)
                scraped += len(jobs)
                for job in jobs:
                    payload = {
                        "title": job.get("title", "Unknown role"),
                        "company": job.get("company", "Unknown company"),
                        "description": job.get("description", ""),
                        "url": job.get("url", ""),
                        "location": "",
                        "salary": "",
                    }
                    success = await post_job_to_trackify(client, api_url, api_key, payload)
                    if success:
                        posted += 1
                    else:
                        failed += 1

    asyncio.run(runner())
    logger.info("Scraper completed: scraped=%s posted=%s failed=%s", scraped, posted, failed)
    return {"scraped": scraped, "posted": posted, "failed": failed}
