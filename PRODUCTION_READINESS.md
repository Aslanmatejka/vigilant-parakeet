# Production Readiness Checklist

Audit date: 2026-07-09  
Repo: `vigilant-parakeet` (React/Vite frontend + FastAPI backend + Supabase)

## Status legend

- [x] Pass
- [ ] Fail / needs work
- [~] Partial / deferred (documented, not blocking local green gates)

---

## 1. Build & compile

| Check | Status | Notes |
|-------|--------|-------|
| Frontend `npm run build` | [x] | Vite production build succeeds |
| No TypeScript project | [x] | JS/JSX only — N/A |
| Backend importable | [~] | App loads; FastAPI `@app.on_event` deprecation warnings remain |

## 2. Tests

| Check | Status | Notes |
|-------|--------|-------|
| Frontend Jest (`npm test`) | [x] | **53/53 passed** |
| Backend AI suite (`backend/ai/tests`) | [x] | **515 passed** |
| Backend unit subset (`suggestion_chips`, `user_guidance`, `listing_expiry`) | [x] | **44 passed** |
| Live/integration backend tests | [~] | `test_voice_live`, `test_granny_chat`, `test_claim_flow`, `test_share_flow`, and some heavy `test_ai_engine` imports hang / need live services — excluded from gate |

## 3. Lint / static analysis

| Check | Status | Notes |
|-------|--------|-------|
| `npm run lint` | [x] | **0 errors** (130 warnings: unused vars / exhaustive-deps) |
| Hooks correctness | [x] | Fixed conditional hooks in `FoodDietaryTags`, `AdminSidebar`, `useLocation` |
| Real bugs found via lint | [x] | Fixed `onTrade` undefined, `tempMessage` TDZ, emoji regex `/u` flag |

## 4. Dependency security

| Check | Status | Notes |
|-------|--------|-------|
| Critical/high runtime CVEs | [x] | Cleared `shell-quote`, `rollup`, `tar`, `ws`, `yaml`, `postcss` issues via updates |
| Remaining `npm audit` | [~] | Vite/esbuild **dev-server only** advisory; fix requires Vite 8 major bump — deferred |
| Python deps | [~] | Loose `>=` pins remain; no failing install in this pass |

## 5. Secrets & debug leftovers

| Check | Status | Notes |
|-------|--------|-------|
| `.env` / `.env.local` gitignored | [x] | |
| No hardcoded private secrets in source | [x] | Mapbox `pk.` in `netlify.toml` is public client token |
| Remove agent debug ingest / file logs | [x] | Frontend localhost ingest removed; backend debug writers no-op’d |
| Debug log files ignored | [x] | `debug-*.log` added to `.gitignore` |

## 6. Supabase security advisors

| Check | Status | Notes |
|-------|--------|-------|
| Anon EXECUTE on admin DEFINER RPCs | [x] | Revoked `is_admin`, `expire_unclaimed_receipts` from anon/authenticated |
| Permissive users INSERT policy | [x] | Restricted to `service_role` |
| Trigger `search_path` | [x] | Set on `update_user_preferences_updated_at` |
| Impact aggregators for authenticated | [~] | Intentionally left for signed-in users (read-only summaries) |
| Leaked password protection | [~] | **Dashboard action:** enable in Auth → Password security ([docs](https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection)) |
| Postgres version patches | [~] | **Dashboard action:** upgrade project ([docs](https://supabase.com/docs/guides/platform/upgrading)) |

## 7. CI/CD alignment

| Check | Status | Notes |
|-------|--------|-------|
| Workflow branch names | [x] | CI now listens to `main`, `master`, and `develop` |
| Deploy jobs real | [~] | Staging/prod steps still stubs |

## 8. Runtime / ops (deferred)

| Check | Status | Notes |
|-------|--------|-------|
| Bundle size | [~] | Main JS ~1.27 MB — consider route-level code splitting |
| FastAPI lifespan migration | [~] | Replace deprecated `on_event` handlers |
| Live voice / claim flow e2e | [~] | Keep as optional CI job with secrets |

---

## Gate results (this pass)

```
npm run build     ✅
npm test          ✅ 53 passed
npm run lint      ✅ 0 errors
backend/ai/tests  ✅ 515 passed
npm audit high    ⚠️  vite/esbuild only (dev server)
```

## Manual follow-ups (cannot fully automate here)

1. Enable **Leaked Password Protection** in Supabase Auth.
2. Upgrade Supabase Postgres to latest patched version.
3. Schedule Vite 8 upgrade when ready for the breaking change.
4. Wire real deploy steps in `.github/workflows/ci-cd.yml`.
