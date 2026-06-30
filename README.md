# LinkedIn Job Scraper

Stateless FastAPI service that scrapes LinkedIn's **public guest jobs API**
(`/jobs-guest/jobs/api/seeMoreJobPostings/search`). **No login, no browser, no
session file** — the guest endpoint returns HTML job cards without auth.

Drives the hourly n8n "Job Hunt - WF-D LinkedIn Poller" workflow.

## Endpoints

### `GET /jobs`
| param        | required | meaning                                   |
|--------------|----------|-------------------------------------------|
| `keywords`   | yes      | job title / search terms                  |
| `location`   | no       | location text, e.g. `Bengaluru`           |
| `geoId`      | no       | LinkedIn geoId (more precise than text)   |
| `since`      | no (3600)| lookback window in seconds (`f_TPR=r…`)    |
| `remote`     | no       | `f_WT`: 1 onsite, 2 remote, 3 hybrid      |
| `experience` | no       | `f_E`: 1 intern … 6 exec                  |
| `jobType`    | no       | `f_JT`: F/P/C/T/I                         |
| `limit`      | no (25)  | max jobs returned                         |

Returns:
```json
{ "count": 2, "jobs": [
  {"job_id":"123","title":"Data Engineer","company":"Acme",
   "location":"Bengaluru","url":"https://www.linkedin.com/jobs/view/123",
   "posted_iso":"2026-06-30"}
]}
```

### `GET /health` → `{"status":"ok"}`

## Run locally
```bash
docker compose up --build
curl 'http://localhost:8000/jobs?keywords=data%20engineer&location=Bengaluru&since=86400'
```

## Deploy on VPS (alongside n8n)
1. Set the `n8n-net` network in `docker-compose.yml` to your n8n container's
   actual docker network (`external: true`).
2. `docker compose up -d --build`
3. From the n8n container: `curl http://linkedin-scraper:8000/health`.

## Anti-throttle
Rotating User-Agents, 2–5s jitter between pages, exponential backoff on 429/999,
page cap (`MAX_PAGES`, default 2). At hourly polling this is low-risk. If the VPS
IP gets blocked, set `HTTP_PROXY` env to a (residential) proxy — do **not** widen
the poll interval (you'd miss jobs).
