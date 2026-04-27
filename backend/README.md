# SequelSpeak Backend

FastAPI backend for SequelSpeak: PostgreSQL connection testing, profile management, conversation state, and the entry point for the Router/Personas pipeline.

For the project-wide overview see the [root README](../README.md).

## Stack

| Layer | Technology |
|-------|-----------|
| Web framework | FastAPI + Uvicorn |
| Database driver | psycopg 3 (binary) + psycopg-pool |
| Internal ORM | SQLModel |
| Migrations | Alembic |
| Auth | Clerk JWT (via `clerk-backend-api`) |
| Conversation state | Redis (`redis.asyncio`) with in-memory fallback |
| Credential cache | Redis + AES-256-GCM (`cryptography`) |
| Rate limiting | slowapi |
| Metrics | prometheus-client |
| Settings | pydantic-settings |
| Tests | pytest, pytest-asyncio, pytest-cov, pytest-mock, httpx |

Full dependency list: [requirements.txt](requirements.txt).

## Endpoints

All endpoints under `/api/v1/...`. Auth column indicates whether a Clerk JWT is required.

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/` | GET | No | Liveness check |
| `/api/v1/health` | GET | No | Database connectivity + latency |
| `/api/v1/version` | GET | No | App version, environment, build date |
| `/api/v1/status` | GET | No | Operational status, uptime, circuit breaker state |
| `/api/v1/utils/test-connection` | POST | Yes | Test a PostgreSQL connection (raw URL or `profile_id`); rate-limited |
| `/api/v1/query` | POST | Yes | Initialize a Router query and persist `ConversationState` |
| `/api/v1/profiles` | GET | Yes | List the authenticated user's profiles |
| `/api/v1/profiles` | POST | Yes | Create a profile (optional password is encrypted into Redis cache) |
| `/api/v1/profiles/{id}` | PUT | Yes | Update a profile |
| `/api/v1/profiles/{id}` | DELETE | Yes | Delete a profile |
| `/metrics` | GET | No (network-level only) | Prometheus text exposition |
| `/docs`, `/redoc`, `/openapi.json` | GET | No | Interactive API docs |

> The Router persona pipeline (SchemaExpert → SQLWriter → SQLGuardian → Executor → Explainer) is in development. `/api/v1/query` currently performs **initialization only**: it validates the request, generates/looks up the conversation, and persists the initial `ConversationState`.

## Project Layout

```
backend/
├── main.py                          # App factory, middleware, lifespan, exception handlers
├── config.py                        # Pydantic Settings + field validators
├── logging_config.py                # Structured JSON logging
├── exceptions.py                    # DatabaseConnectionError + custom hierarchy
├── conftest.py / pytest.ini         # Test configuration
├── alembic.ini / alembic/           # Migrations
│   └── versions/0001_create_profiles_table.py
├── api/v1/                          # Routers: connection, health, meta, query, profiles
├── services/
│   ├── db_connection_service.py     # Test PostgreSQL connections + retry
│   ├── connection_pool.py           # One pool per unique URL
│   ├── conversation_state.py        # ConversationStateManager (Redis + memory)
│   ├── router_service.py            # Router initialization
│   ├── profile_service.py           # CRUD with SQLModel
│   └── credential_cache.py          # AES-256-GCM Redis cache
├── models/profile.py                # SQLModel `profiles` table
├── repositories/                    # Reserved
├── schemas/                         # Pydantic request/response models
├── utils/
│   ├── auth.py                      # verify_clerk_token dependency
│   ├── db.py                        # async SQLModel engine + run_migrations()
│   ├── security.py                  # mask_connection_url, sanitizers
│   ├── circuit_breaker.py           # CircuitBreaker, db_circuit_breaker
│   ├── connection_resilience.py     # health_monitor, retry helpers
│   ├── input_validator.py           # SQL/command-injection guards
│   ├── patterns.py                  # Reusable regex / classifiers
│   └── prometheus.py                # Metrics + path templating
├── scripts/                         # Demo + simulation utilities
└── tests/                           # 665 tests across 41 files (see Testing)
```

## Database & Migrations

The backend keeps an **internal Postgres** database for user profiles. User-supplied target databases are connected to per-request and never persisted.

- Engine: created in [utils/db.py](utils/db.py) using `INTERNAL_DATABASE_URL` (`postgresql+psycopg://...`). In development the URL falls back to `postgresql+psycopg://postgres:postgres@db:5432/sequelspeak` (the Docker Compose default).
- Models: [models/profile.py](models/profile.py) (SQLModel `profiles` table — id, user_id, name, host, port, username, database, created_at, last_used).
- Migrations: [alembic/](alembic) with [alembic/env.py](alembic/env.py) configured to import `models.profile` so SQLModel metadata is registered. Initial migration: [alembic/versions/0001_create_profiles_table.py](alembic/versions/0001_create_profiles_table.py).

```bash
# Apply migrations against the configured database
cd backend
alembic upgrade head

# When running migrations from the host (Docker hostname `db` is unreachable),
# point Alembic at a localhost-mapped URL:
ALEMBIC_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/sequelspeak \
  alembic upgrade head
```

In Docker Compose, the dedicated `migrate` service runs `alembic upgrade head` once and the `backend` service waits on it (`service_completed_successfully`). The helper script `python3 start_docker.py` orchestrates this end-to-end.

## Conversation State

[services/conversation_state.py](services/conversation_state.py) provides `ConversationStateManager`:

- Redis-backed when `REDIS_ENABLED=true` and the `redis` package is available; otherwise an in-memory dict (warning logged).
- Each conversation is stored at key `conversation:<uuid>` with `CONVERSATION_STATE_TTL` seconds (default 7 days).
- The manager rebinds its Redis client to the active event loop on each operation, which makes it safe for tests that use multiple event loops.
- Errors fall back to in-memory storage so transient Redis failures degrade gracefully.

The full `ConversationState` schema (SRS v2 §6.1) covers query, clarification, execution plan, generated SQL, results, explanation, persona traces, and errors. Today the Router endpoint populates the initialization fields only.

## Credential Cache

[services/credential_cache.py](services/credential_cache.py) stores per-profile passwords encrypted in Redis:

- AES-256-GCM via `cryptography.hazmat.primitives.ciphers.aead.AESGCM`
- Key derived from `SECRET_KEY` using SHA-256 (rotating `SECRET_KEY` invalidates existing entries; the service auto-evicts undecryptable values)
- Default TTL: 1 hour
- Connection-test endpoint reads/refreshes the cached password when a `profile_id` is supplied

## Observability

- **Structured logging** ([logging_config.py](logging_config.py)) emits JSON in production; correlation IDs are propagated via the `X-Correlation-ID` middleware in [main.py](main.py).
- **Prometheus metrics** at `/metrics` (text exposition format), defined in [utils/prometheus.py](utils/prometheus.py): HTTP totals/latency/in-progress, connection pool gauges, database error counters. The lifespan starts a background task that updates pool metrics every 10s.
- **Path templating** prevents high-cardinality labels (e.g. `/api/v1/profiles/{id}` instead of UUIDs).
- **Health endpoint** reports configured/healthy/unhealthy/not_configured states with measured latency.

## Testing

- **665 test functions** across **41 files** organized by area
- `pytest.ini` sets `asyncio_mode=auto`, includes `--cov=services --cov=api --cov=utils` and HTML/XML reports
- CI ([../.github/workflows/tests.yml](../.github/workflows/tests.yml)) runs the matrix on Python 3.10, 3.11, 3.12 with a Redis 7 service container and gates with `--cov-fail-under=85`

```bash
# From backend/
pytest                                      # full suite
pytest tests/connection/ -v
pytest tests/security/ -v
pytest tests/router/ -v
pytest tests/services/ -v
pytest tests/monitoring/ -v
pytest --cov-report=html                    # open htmlcov/index.html
pytest -m unit                              # marker filter
pytest -m integration                       # requires Redis on localhost:6379
```

### Test Subdirectories

| Subdirectory | Focus |
|--------------|-------|
| `tests/api/` | FastAPI route behaviour (meta, connection) |
| `tests/configuration/` | `Settings` validators, retry config |
| `tests/connection/` | URL parsing, retry, pool stats, resource leaks, resilience, oneshot |
| `tests/conversation/` | `ConversationStateManager` |
| `tests/core/` | App startup, custom exceptions |
| `tests/endpoints/` | Profiles, meta, connection auth |
| `tests/health/` | `/health` endpoint |
| `tests/log_tests/` | Logging config |
| `tests/monitoring/` | Prometheus metrics |
| `tests/query/` | Router schema, validation, conversation integration |
| `tests/router/` | `RouterService` unit + integration |
| `tests/security/` | Auth, input validation, credential safety, no-leak |
| `tests/services/` | `ProfileService`, `CredentialCache` |
| `tests/test_utils/` | Patterns, error classifier, circuit breaker |

## Configuration

Settings are loaded from environment variables via [config.py](config.py). Copy [.env.example](.env.example) to `.env` and customize.

### Application

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | `SequelSpeak Backend` | Display name |
| `APP_VERSION` | `1.0.0` | Reported in `/version` and metrics |
| `BUILD_DATE` | `unknown` | Reported in `/version` |
| `ENVIRONMENT` | `development` | `development` / `staging` / `production` |
| `SECRET_KEY` | – | Required in production; AES key for credential cache derives from it |
| `ALLOWED_ORIGINS` | `http://localhost:3000,http://localhost:5173` | Comma-separated; wildcard rejected in production |
| `INTERNAL_DATABASE_URL` | – | Async URL for the profile/internal DB (`postgresql+psycopg://...`) |

### Connection / Pool

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_CONNECTION_TIMEOUT` | `10` | psycopg connect timeout (seconds) |
| `DB_POOL_MIN_SIZE` | `1` | Pool floor |
| `DB_POOL_MAX_SIZE` | `10` | Pool ceiling (warn >50) |
| `DB_POOL_TIMEOUT` | `30` | Acquisition timeout |
| `DB_POOL_MAX_IDLE` | `None` | Max idle seconds before closing |

### Health / Retry

| Variable | Default | Description |
|----------|---------|-------------|
| `HEALTH_CHECK_DB_URL` | `None` | Optional DB URL for `/health` checks |
| `HEALTH_CHECK_TIMEOUT` | `2` | Capped at 10s |
| `HEALTH_CHECK_RETRY_MAX` | `1` | Keep low for fast responses |
| `CONNECTION_RETRY_MAX` | `2` | Retries for the test-connection endpoint |
| `CONNECTION_RETRY_INITIAL_DELAY` | `1.0` | Base for exponential backoff |

### Rate Limiting & Circuit Breaker

| Variable | Default | Description |
|----------|---------|-------------|
| `RATE_LIMIT_ENABLED` | `true` | Toggle slowapi |
| `RATE_LIMIT_PER_MINUTE` | `10` | Per-IP for `/test-connection` |
| `RATE_LIMIT_BURST` | `3` | Allowed burst |
| `CIRCUIT_BREAKER_ENABLED` | `true` | Toggle the breaker |
| `CIRCUIT_BREAKER_FAILURE_THRESHOLD` | `5` | Consecutive failures before opening |
| `CIRCUIT_BREAKER_TIMEOUT` | `60` | Seconds before half-open |

### Authentication (Clerk)

| Variable | Default | Description |
|----------|---------|-------------|
| `CLERK_SECRET_KEY` | – | Required for protected endpoints |
| `CLERK_PUBLISHABLE_KEY` | – | Optional; for parity with the frontend |

### Redis (conversation state + credential cache)

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_ENABLED` | `true` | When false, conversation state uses in-memory fallback |
| `REDIS_HOST` | `localhost` | Use `redis` inside Docker Compose |
| `REDIS_PORT` | `6379` | |
| `REDIS_DB` | `0` | 0–15 |
| `REDIS_PASSWORD` | – | Optional |
| `REDIS_SSL` | `false` | Use `rediss://` when true |
| `REDIS_TIMEOUT` | `5` | Socket timeout |
| `CONVERSATION_STATE_TTL` | `604800` | 7 days |

### Metrics

| Variable | Default | Description |
|----------|---------|-------------|
| `METRICS_ENABLED` | `true` | Toggle the `/metrics` endpoint and middleware |

## Local Development

```bash
# From the project root
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

cp backend/.env.example backend/.env
# Fill in CLERK_*, SECRET_KEY, ALLOWED_ORIGINS, INTERNAL_DATABASE_URL, REDIS_*

# Run migrations against your dev DB
cd backend
alembic upgrade head

# Start the API with hot-reload
uvicorn main:app --reload --port 8000
```

## Code Quality

- Style: PEP 8 (Black is the project's preferred formatter)
- Coverage gate: 85% (`services/`, `api/`, `utils/`)
- Security: never log connection URLs, passwords, or Clerk tokens — `mask_connection_url()` is required around any error or log line that may include a URL
