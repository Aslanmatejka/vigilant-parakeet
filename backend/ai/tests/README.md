# FoodMaps AI — Test Suite

Hermetic pytest suite for the AI stack. Runs without MySQL, OpenAI, Twilio, or Mapbox access.

## Layout

| File | Scope |
|---|---|
| `test_ai_engine.py`      | `detect_spanish`, canned responses, rate-limiter, circuit breaker, role prompt |
| `test_notifications.py`  | `_safe_json_loads`, `_as_lower_set`, language/SMS/consent gates, allergen / dietary / category matching, EN + ES templates |
| `test_tool_definitions.py` | OpenAI function-calling schema sanity + required tool coverage |
| `test_tools_dispatch.py` | `execute_tool` dispatcher error paths + `run_safe_query` whitelist / PII / SQL-injection guards |

## Run locally

```bash
cd /home/ec2-user/project
python3 -m pytest backend/ai/tests -v
```

`conftest.py` clears integration env vars before any backend module is imported so
tests never hit real services.

## Live smoke-tests

The `backend/ai/scripts/launch_tests.py` script hits a running server via HTTP and is
**not** part of this suite — run it manually against a live deployment.
