# AGENTS.md - Project Specific Instructions for Claude Code

## 🛠️ Tech Stack
- **Frontend**: React 19, TanStack Router v1, Vite 8, Tailwind CSS 4.2, TanStack Query v5, React Hook Form v7 + Zod, Radix UI, Lucide React, Sonner, next-themes, TypeScript 5.9, Biome, Playwright, Bun
- **Backend**: FastAPI 0.141+, Python 3.14, Pydantic v2, SQLModel, PostgreSQL 18 + psycopg[binary], Alembic, Tenacity, emails + Jinja2, PyJWT + pwdlib, Sentry SDK, pydantic-settings, HTTPX, UV, Pytest, Coverage.py, Ruff, MyPy (strict)
- **DevOps**: Docker, Docker Compose, Traefik (via labels), Adminer, GitHub Actions, .env

## 📁 Project Structure (key directories)
```
autoposter/
├── backend/
│   ├── app/ (api, core, email-templates, models, utils)
│   ├── scripts/, tests/
│   ├── Dockerfile, pyproject.toml, alembic.ini
├── frontend/
│   ├── src/ (components, client, hooks, lib, routes)
│   ├── public/, tests/
│   ├── package.json, tsconfig.json, vite.config.ts, biome.json, openapi-ts.config.ts, playwright.config.ts
├── compose.yml, compose.override.yml, compose.traefik.yml
├── .env, .dockerignore, .gitignore
├── pyproject.toml (root), bun.lock, uv.lock, copier.yml
└── README.md, development.md, deployment.md
```

## 🎨 Style & Coding Conventions
### Frontend (Biome)
- Spaces indentation, double quotes, semicolons as needed
- No parameter assignments, use self‑closing elements, no useless else
- Tailwind directives enabled, organize imports on save
### Backend (Ruff & MyPy)
- Ruff: Py314, select E,W,F,I,B,C4,UP,ARG001,T201; ignore E501,B008,W191,B904
- MyPy: strict mode, exclude venv/.venv/alembic
- General: TypeScript strict; Python type hints for public APIs
- Naming: Components PascalCase; functions/vars camelCase (TS)/snake_case (Py); constants UPPER_SNAKE_CASE
- Imports: frontend grouped by type; backend: stdlib → third‑party → local
- Comments: explain why, not what; remove commented‑out code

## ⚡ Performance Considerations
- **Build**: Multi‑stage Docker (frontend built with Bun, Python stage serves static assets); UV/Bun dependency caching
- **Runtime**:
  - Frontend: Vite HMR, production minification/code splitting, Tailwind purging, React 19 auto‑batching, TanStack Query caching
  - Backend: FastAPI + Pydantic v2 validation; SQLModel + PostgreSQL ORM; Uvicorn workers (default 4); connection pooling; async where beneficial (HTTPX, email)
  - Database: PostgreSQL 18 with proper indexing; connection limits via Compose; health checks
- **Coding Practices**:
  - Avoid nested loops; use efficient data structures (maps/sets) or batch operations
  - Prevent N+1 queries: use JOINs, selectinload, or fetch all needed data in one query
  - Cache expensive computations; paginate large lists
  - Keep DB transactions short; consider read replicas for heavy reads
  - Bundle frontend assets; enable gzip/compression via Traefik
  - Monitor slow queries; add indexes on WHERE/JOIN/Order By columns

## 🏗️ Architecture Overview
**High‑Level**: Frontend (React/Vite) ↔ Backend API (FastAPI/Python) ↔ PostgreSQL DB; plus Email Service (SMTP/Jinja2) and Sentry for errors. Adminer and Traefik provide DB admin and SSL/routing.

**Backend Layers**:
1. API Layer – routes, request/response models, dependency injection
2. Service Layer – business logic, CRUD operations
3. Data Access Layer – SQLModel models, relationships, Alembic migrations

**Frontend Layers**:
- Application (router, query, theme providers)
- Routing (type‑safe routes with loaders/guards)
- State (TanStack Query server/client state, cache)
- Presentation (reusable UI components, page‑specific components, hooks, utils)

## 🔧 Development Workflow
### Prerequisites
Docker Engine, Docker Compose, Bun, UV, Git

### Setup
1. Copy/adjust `.env` (see existing `.env`)
2. Fill required vars: POSTGRES_*, SECRET_KEY, FIRST_SUPERUSER, SMTP_*, DOMAIN, ENVIRONMENT=local

### Run
- **Docker Compose (recommended)**:
  ```bash
  docker compose up --build   # build & start
  docker compose up -d        # detached
  docker compose logs -f      # follow logs
  docker compose down         # stop & remove
  ```
  Access: http://localhost (frontend+backend), http://localhost:8000/docs (Swagger), http://localhost:8080 (Adminer), http://localhost:1080 (Mailcatcher)

- **Hot Reload (dev)**:
  ```bash
  # Backend
  cd backend; uv sync --dev; uv run fastapi run --reload
  # Frontend (another tab)
  cd frontend; bun install; bun dev
  ```

### DB Management
```bash
cd backend
uv run alembic revision --autogenerate -m "msg"
uv run alembic upgrade head
uv run alembic downgrade -1
```

## 🧪 Testing Strategy
- **Backend**: Pytest + Coverage.py; `uv run pytest`; HTML cov with `--cov-report=html`
- **Frontend**: Playwright; `bun test` or `bun test:ui`
- **Lint/Format**:
  - Frontend: `bun run lint` (Biome fixes --write errors)
  - Backend: `uv run ruff check --fix . && uv run ruff format .`
  - Type checking: `uv run mypy .` (backend), `bun run tsc --noEmit` (frontend)

## 📜 Behavioral Guidelines (from andrej-karpathy-skills/CLAUDE.md)
> Bias toward caution over speed; for trivial tasks use judgment.

1. **Think Before Coding**
   - State assumptions; ask if unsure.
   - Present multiple interpretations; don’t pick silently.
   - Note simpler approaches; push back when warranted.
   - If unclear, stop, name confusion, ask.

2. **Simplicity First**
   - Minimum code that solves the problem.
   - No extra features, abstractions, flexibility, or error handling for impossible cases.
   - Rewrite if 200 lines could be 50.

3. **Surgical Changes**
   - Touch only what you must; don’t “improve” adjacent code/comments/formatting.
   - Match existing style even if you’d do differently.
   - Mention unrelated dead code; don’t delete unless asked.
   - Remove only imports/vars/functions made unused by your changes.

4. **Goal‑Driven Execution**
   - Define verifiable success criteria.
   - Transform tasks: “Add validation” → write failing tests then make pass; “Fix bug” → write reproducing test then fix; “Refactor X” → ensure tests pass before/after.
   - Multi‑step: list steps with verification:
     ```
     1. [Step] → verify: [check]
     2. [Step] → verify: [check]
     3. [Step] → verify: [check]
     ```
   - Strong criteria enable independent looping; weak ones need constant clarification.

These guidelines work when diffs have fewer unnecessary changes, fewer rewrites from overcomplication, and clarifying questions come before implementation.

## 🚀 Running the Application (Quick Start)
### Docker Compose (Recommended)
```bash
git clone <repo-url> && cd autoposter
# Edit .env with your values (POSTGRES_*, SECRET_KEY, etc.)
docker compose up --build          # build and start
# Visit:
#   Frontend + Backend: http://localhost
#   API Docs: http://localhost:8000/docs
#   Adminer: http://localhost:8080
#   Mailcatcher: http://localhost:1080
```
### Development Mode (Hot Reload)
```bash
# Backend
cd backend; uv sync --dev; uv run fastapi run --reload
# Frontend (separate terminal)
cd frontend; bun install; bun dev
```