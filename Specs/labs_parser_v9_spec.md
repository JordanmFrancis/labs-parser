---
date: 2026-04-13
type: deliverable
tags: [dev, claude]
project: learning-python
---

# Lab Parser v9 Spec — Deployment

Related: [[labs_parser_roadmap]] · [[labs_parser_v8_spec]]

By v8 I have a working full-stack app on `localhost`. v9 puts it on the internet at a real URL. The thing isn't real until other people can use it (or at least until I can pull it up on my phone).

## What I Want to Learn

- Docker — what an image is, what a container is, why `Dockerfile` matters
- `docker-compose` — running multiple services together
- Postgres — migrating from SQLite to a real database
- Environment variables and secrets management in production
- Logging — replacing `print()` with structured logs
- A cloud platform — Render (or Fly.io as backup) for backend, Vercel for frontend
- CI/CD basics — GitHub Actions running tests on every push
- Healthchecks, monitoring basics, error tracking (Sentry)

## Why Render + Vercel

Render: Postgres + Docker container backend on a single platform, auto-deploys on git push, free tier covers a portfolio app, no AWS complexity. Vercel: cheapest and best for Vite/React static frontends.

Skip AWS/GCP for now. They teach 80% infrastructure-engineering pain that doesn't help me ship a portfolio app. If v12 ever needs them, I'll learn them then.

## Migrate SQLite → Postgres

SQLite was perfect for v5–v8 (one file, no server). Postgres is what I want in production: real concurrency, real types, hosted backups.

Path:
1. Install `asyncpg` (async Postgres driver) and `sqlalchemy` 2.x async + `alembic` (migrations)
2. Define the same v5 schema as SQLAlchemy models
3. Generate the initial migration with Alembic
4. Update `db.py` to use SQLAlchemy async sessions instead of `aiosqlite`
5. Test locally against a Postgres in Docker before deploying

Alembic is the new concept here. Migrations are versioned schema changes. I generate them from model diffs, commit them to git, and they run on every deploy. No more "did I add that column on prod?"

## Dockerfile (Backend)

```dockerfile
FROM python:3.12-slim AS builder
RUN pip install uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM python:3.12-slim
RUN apt-get update && apt-get install -y poppler-utils && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY . .
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "labs_parser.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Multi-stage build — builder installs deps, final image is slim. `poppler-utils` is the system dep `pdf2image` needs.

## docker-compose.yml (Local Dev)

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: labs
      POSTGRES_PASSWORD: dev_password_only
      POSTGRES_DB: labs_dev
    ports: ["5432:5432"]
    volumes: [pgdata:/var/lib/postgresql/data]

  api:
    build: ./backend
    environment:
      DATABASE_URL: postgresql+asyncpg://labs:dev_password_only@postgres:5432/labs_dev
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
    depends_on: [postgres]
    ports: ["8000:8000"]

volumes:
  pgdata:
```

Local dev becomes `docker-compose up`. Same setup as production except secrets are dev-only.

## Secrets Management

- **Local dev:** `.env` file, `.gitignored`
- **Render production:** environment variables set in the Render dashboard, never in git
- **CI:** GitHub Actions secrets

Rules I'll follow:
- Never commit a `.env` (already in `.gitignore` from v1)
- Never log secret values, even in error messages
- API key rotation is a documented runbook in the README

## Logging

Replace every `print()` in the backend with structured logging. Use `structlog` for JSON output (machine-parseable in Render's log viewer):

```python
import structlog
log = structlog.get_logger()

log.info("draw_imported", draw_id=42, source="labcorp.pdf", rows=87)
log.error("vision_api_failed", marker=marker, error=str(e))
```

Each log line is a JSON object. Searchable in production. Way better than scrolling through unstructured prints.

## Error Tracking — Sentry

Free tier covers a portfolio app. One install:

```python
import sentry_sdk
sentry_sdk.init(dsn=os.environ["SENTRY_DSN"], traces_sample_rate=0.1)
```

Now any unhandled exception in production gets captured with stack trace, request context, and user info. No more "I wonder if anything broke last week."

## Deployment Steps

| Step | What |
|------|------|
| 1 | Create Render account + new Postgres + new Web Service from GitHub repo |
| 2 | Set env vars: `DATABASE_URL` (auto-injected), `ANTHROPIC_API_KEY`, `SENTRY_DSN` |
| 3 | Render auto-detects Dockerfile, builds, runs `alembic upgrade head` on each deploy via release command |
| 4 | Push to `main` → auto-deploy starts |
| 5 | Backend is live at `labs-parser.onrender.com` |
| 6 | Vercel: import frontend repo, set `VITE_API_URL=https://labs-parser.onrender.com`, deploy |
| 7 | Frontend live at `labs-parser.vercel.app` (or my custom domain) |

## CI with GitHub Actions

`.github/workflows/test.yml` runs on every push:

- Backend: `uv sync` → `pytest` → `mypy` → `ruff check`
- Frontend: `npm install` → `npm run typecheck` → `npm run lint` → `npm run build`
- Block PRs that fail

Render auto-deploys on `main` only after CI passes (Render's "wait for CI" setting).

## Healthcheck + Monitoring

`/health` endpoint already exists from v7. Render polls it every 30s. If it returns non-200 for 5 minutes, Render alerts me.

Add basic uptime monitoring: free tier of UptimeRobot pings `/health` from multiple regions.

## Edge Cases

| Case | Behavior |
|------|----------|
| Cold-start latency on Render free tier | Document it in README, accept it. Upgrade to $7/mo if it gets annoying. |
| Database connection pool exhausted | SQLAlchemy default pool (5 connections) is fine for single-user. Monitor. |
| Anthropic API key leaked in a log | Audit logs for the leaked value, rotate the key, redact going forward |
| Migration fails on deploy | Render rolls back automatically, alert me via email |
| Free Postgres tier (1GB) fills up | Set up an alert at 800MB, archive old draws to S3 |
| CORS misconfigured | Frontend can't hit backend, browser console screams. Fix `allow_origins` in v7 config |

## Files to Add

- `Dockerfile`
- `docker-compose.yml`
- `.dockerignore`
- `alembic.ini` + `migrations/` folder
- `.github/workflows/test.yml`
- `render.yaml` (infrastructure-as-code for Render)
- README — "Deployment" section

## What's New vs v8

| Concept | v8 | v9 |
|---------|----|----|
| Where it runs | localhost | live URL on the internet |
| Database | SQLite file | hosted Postgres |
| Logs | print() | structured JSON in cloud log viewer |
| Errors | console traceback | Sentry alerts with stack traces + context |
| Deploy | "did I push to git?" | git push → auto-deploy with CI gate |
| Schema changes | manual SQL | versioned migrations |

## Out of Scope for v9

- Multi-region deployment
- CDN configuration beyond Vercel defaults
- Database read replicas
- Kubernetes (this is a portfolio app, not Netflix)
- Load testing
- WAF / DDoS protection
