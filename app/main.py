"""LinkedIn guest jobs API scraper.

No login, no browser, no session. Hits LinkedIn's public guest endpoint
(/jobs-guest/jobs/api/seeMoreJobPostings/search) which returns HTML job cards,
parses them with BeautifulSoup, and returns JSON. Stateless: every filter is
passed per-request by the caller (n8n).
"""
from __future__ import annotations

import asyncio
import os
import random
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, Query
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

app = FastAPI(title="LinkedIn Job Scraper", version="1.0.0")

GUEST_URL = (
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
)

# Rotating realistic desktop User-Agents — looking human matters far more than
# cron spacing for avoiding the guest-endpoint throttle (HTTP 429 / 999).
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) "
    "Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.3 Safari/605.1.15",
]

# Each guest page returns up to ~25 cards. Last-hour result sets are tiny, so a
# low page cap is plenty and keeps per-run request volume small.
PER_PAGE = 25
MAX_PAGES = int(os.getenv("MAX_PAGES", "2"))
HTTP_PROXY = os.getenv("HTTP_PROXY") or os.getenv("PROXY_URL") or None
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "20"))

_JOB_ID_RE = re.compile(r"(\d{6,})")


def _headers() -> dict:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.linkedin.com/jobs",
    }


def _build_params(
    keywords: str,
    location: str,
    geo_id: Optional[str],
    since: int,
    remote: Optional[str],
    experience: Optional[str],
    job_type: Optional[str],
    start: int,
) -> dict:
    params = {
        "keywords": keywords,
        "f_TPR": f"r{since}",   # posted in the last `since` seconds
        "sortBy": "DD",          # date descending (newest first)
        "start": start,
    }
    if location:
        params["location"] = location
    if geo_id:
        params["geoId"] = geo_id
    if remote:
        params["f_WT"] = remote        # 1 onsite, 2 remote, 3 hybrid
    if experience:
        params["f_E"] = experience     # 1..6
    if job_type:
        params["f_JT"] = job_type      # F/P/C/T/I
    return params


class _Throttled(Exception):
    pass


@retry(
    retry=retry_if_exception_type((_Throttled, httpx.TransportError)),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    stop=stop_after_attempt(4),
    reraise=True,
)
async def _fetch_page(client: httpx.AsyncClient, params: dict) -> str:
    resp = await client.get(GUEST_URL, params=params, headers=_headers())
    # LinkedIn throttles with 429 and the infamous 999.
    if resp.status_code in (429, 999) or resp.status_code >= 500:
        raise _Throttled(f"status {resp.status_code}")
    resp.raise_for_status()
    return resp.text


def _text(node) -> str:
    return node.get_text(strip=True) if node else ""


def _parse_cards(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("li")
    jobs: list[dict] = []
    for li in cards:
        base = li.select_one("div.base-card") or li.select_one("div.base-search-card") or li
        title = _text(li.select_one("h3.base-search-card__title"))
        if not title:
            continue
        company = _text(li.select_one("h4.base-search-card__subtitle"))
        location = _text(li.select_one(".job-search-card__location"))

        link_el = li.select_one("a.base-card__full-link") or li.select_one("a")
        url = (link_el.get("href") if link_el else "") or ""
        url = url.split("?")[0].strip()

        # job_id from data-entity-urn (urn:li:jobPosting:1234) or fall back to URL
        urn = (base.get("data-entity-urn") if base else "") or ""
        job_id = ""
        m = _JOB_ID_RE.search(urn) or _JOB_ID_RE.search(url)
        if m:
            job_id = m.group(1)

        time_el = li.select_one("time")
        posted_iso = (time_el.get("datetime") if time_el else "") or ""

        jobs.append(
            {
                "job_id": job_id,
                "title": title,
                "company": company,
                "location": location,
                "url": url,
                "posted_iso": posted_iso,
            }
        )
    return jobs


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/jobs")
async def jobs(
    keywords: str = Query(..., description="Job title / search terms"),
    location: str = Query("", description="Location text, e.g. 'Bengaluru'"),
    geoId: Optional[str] = Query(None, description="LinkedIn geoId (optional)"),
    since: int = Query(3600, ge=300, description="Lookback window in seconds"),
    remote: Optional[str] = Query(None, description="f_WT: 1 onsite, 2 remote, 3 hybrid"),
    experience: Optional[str] = Query(None, description="f_E: 1..6"),
    jobType: Optional[str] = Query(None, description="f_JT: F/P/C/T/I"),
    limit: int = Query(25, ge=1, le=100),
):
    seen: set[str] = set()
    out: list[dict] = []

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, proxy=HTTP_PROXY, follow_redirects=True) as client:
        for page in range(MAX_PAGES):
            start = page * PER_PAGE
            params = _build_params(
                keywords, location, geoId, since, remote, experience, jobType, start
            )
            try:
                html = await _fetch_page(client, params)
            except Exception as exc:  # surface but don't 500 the whole run
                return {
                    "count": len(out),
                    "jobs": out,
                    "warning": f"fetch failed on page {page}: {exc}",
                }

            page_jobs = _parse_cards(html)
            if not page_jobs:
                break

            for j in page_jobs:
                key = j["job_id"] or j["url"] or j["title"]
                if key in seen:
                    continue
                seen.add(key)
                out.append(j)
                if len(out) >= limit:
                    return {"count": len(out), "jobs": out}

            if page < MAX_PAGES - 1:
                await asyncio.sleep(random.uniform(2, 5))  # human-like jitter

    return {"count": len(out), "jobs": out}
