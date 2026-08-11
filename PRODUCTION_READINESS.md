# Production readiness checklist

Generated from a full-repo audit (2026-07-14). Work items are ordered by severity. Items marked **DONE** were fixed in this pass.

## Gates (must be green before deploy)

| # | Gate | Command / check | Status |
|---|------|-----------------|--------|
| G1 | Hermetic backend tests | `pytest` (via `pytest.ini`) → 720 passed, 23 skipped | **DONE** |
| G2 | Frontend lint | `npm run lint` | **DONE** |
| G3 | Frontend unit tests | `npm test` | **DONE** |
| G4 | Frontend production build | `npm run build` | **DONE** |
| G5 | No critical/high open security findings | see S* below | **DONE** |
| G6 | Backend deploy (Railway) | CI/CD on `master` → Railway `dogoods-backend` (or `scripts/deploy-railway.ps1`) | **DONE** |
| G7 | Frontend deploy (Netlify) | CI/CD on `master` → Netlify prod https://dogoods.store | **DONE** |
| G8 | GitHub Actions secrets | `NETLIFY_AUTH_TOKEN`, `NETLIFY_SITE_ID`, `RAILWAY_TOKEN` (repo Secrets) | **SETUP** |

## CI/CD (GitHub Actions)

Workflow: `.github/workflows/ci-cd.yml`

1. **CI** on push/PR to `master` / `main` / `develop`: frontend lint+test+build, backend pytest.
2. **CD** on push to **`master` only** (after CI green): Netlify production + Railway production.

### One-time GitHub setup

Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Where to get it |
|--------|-----------------|
| `NETLIFY_AUTH_TOKEN` | [Netlify personal access tokens](https://app.netlify.com/user/applications#personal-access-tokens) |
| `NETLIFY_SITE_ID` | Netlify → Site → Site configuration → Site details → Site ID (`d5f37690-0335-437a-89b9-34a90c3107ed` for dogoods) |
| `RAILWAY_TOKEN` | Railway → Project → Settings → Tokens (project token) |

Optional **Variables** (defaults already baked into the workflow): `RAILWAY_PROJECT_ID`, `RAILWAY_SERVICE_NAME`, `RAILWAY_ENVIRONMENT`.

Create a GitHub **Environment** named `production` (Actions will prompt) if it does not exist.

After secrets are set: **push to `master`** → Actions runs tests → auto-deploys. Manual CLI deploy remains a fallback.

## Security

| # | Finding | Severity | Status |
|---|---------|----------|--------|
| S1 | Hardcoded RDS password defaults in `backend/scripts/*.py` | Critical | **DONE** (env-only) |
| S2 | `/api/user/update-trust-score` self-service mutation | High | **DONE** (admin-only) |
| S3 | `/api/listings/create` auth optional + client `donor_id` | High | **DONE** (JWT required; `sub` wins) |
| S4 | `AI_REQUIRE_AUTH=""` treated as disabled | High | **DONE** (blank/unset → require auth) |
| S5 | OpenAPI `/docs` enabled in production | Medium | **DONE** (`ENABLE_API_DOCS` gate) |
| S6 | Live credentials in committed `netlify.toml` / test scripts | Critical* | **DONE*** (anon/`pk.` only; preference for Netlify UI) |
| S7 | Stale Jekyll GH Pages workflow | High | **DONE** (deleted) |
| S8 | CI deploy stubs / `main` vs `master` / artifact clash | High | **DONE** (rewrote `ci-cd.yml`) |

\*Supabase anon + Mapbox `pk.` are browser-side by design; kept for build continuity. Prefer dashboard overrides for rotation.

## Backend / tests / deps

| # | Finding | Severity | Status |
|---|---------|----------|--------|
| B1 | Live/e2e tests fail offline → poison default suite | High | **DONE** (`pytest.ini` ignores) |
| B2 | No DB driver pin in `requirements.txt` | High | **DONE** (`psycopg2-binary`, `pymysql`) |
| B3 | Pytest not in CI | Medium | **DONE** |
| B4 | Loose `>=` pins (reproducibility) | Medium | tracked |
| B5 | Standing-instructions + voice/CSV changes uncommitted | Info | ship via Railway upload |

## Frontend

| # | Finding | Severity | Status |
|---|---------|----------|--------|
| F1 | Lint/test/build currently pass | — | **DONE** |
| F2 | No TypeScript / typecheck | Medium | tracked (no TS migration this pass) |
| F3 | Bundle size ~1.28 MB | Low | tracked |
| F4 | Thin Netlify security headers | Medium | **DONE** |

## Explicitly out of scope this pass

- Full TypeScript migration
- Dependency lockfile rewrite for entire LangChain stack
- Rotating production DB passwords in AWS (ops; scripts scrubbed of defaults)
- Secret history rewrite (`git filter-repo`) without explicit request
