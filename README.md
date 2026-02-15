# SequelSpeak

<!-- Replace YOUR_USERNAME with your GitHub username in the badge URLs below -->
[![Backend Tests](https://github.com/YOUR_USERNAME/SequelSpeak/actions/workflows/tests.yml/badge.svg)](https://github.com/YOUR_USERNAME/SequelSpeak/actions/workflows/tests.yml)
[![codecov](https://codecov.io/gh/YOUR_USERNAME/SequelSpeak/branch/main/graph/badge.svg)](https://codecov.io/gh/YOUR_USERNAME/SequelSpeak)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104%2B-009688.svg)](https://fastapi.tiangolo.com)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

An agentic, schema-aware Text-to-SQL system that converts natural language to safe, validated SQL for PostgreSQL.

## Architecture

Built using a **PersonaPlex-inspired architecture** with a Router + isolated Personas approach:

- **Router**: Intent classification and persona orchestration
- **Personas**: Single-responsibility agents (SchemaExpert, SQLWriter, SQLGuardian, etc.)
- **Philosophy**: *"Don't make the LLM think harder — force correct behavior through architecture"*

## Tech Stack

- **Backend**: FastAPI (Python) with async/await
- **Database**: PostgreSQL + pgvector
- **Frontend**: React/TypeScript with Vite
- **State**: Redis for conversation management
- **Observability**: OpenTelemetry

## Quick Start

### Prerequisites

- Python 3.10+ (tested on 3.10, 3.11, 3.12)
- Node.js 18+
- PostgreSQL (for testing database connections)

### Setup

```bash
# Clone the repository
git clone <repository-url>
cd SequelSpeak

# Backend Setup - Create virtual environment at project root
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install backend dependencies
pip install -r backend/requirements.txt

# Configure backend
cp backend/.env.example backend/.env
# Edit backend/.env with your settings

# Frontend Setup
cd frontend
npm install

# Configure frontend
cp .env.example .env
# Edit frontend/.env if needed
cd ..

# Start both servers (from project root with venv activated)
./start.sh
```

The application will be available at:
- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

### Running Tests

```bash
# Activate virtual environment (if not already active)
source .venv/bin/activate

# Run backend tests
pytest backend/tests/ -v

# Run with coverage
pytest backend/tests/ -v --cov=backend/services --cov=backend/api --cov-report=term-missing

# Generate HTML coverage report
pytest backend/tests/ --cov=backend/services --cov=backend/api --cov-report=html
# Open htmlcov/index.html in browser to view detailed coverage

# Run only integration tests (requires Redis)
pytest backend/tests/ -v -m integration

# Run excluding slow tests
pytest backend/tests/ -v -m "not slow"
```

## Project Structure

```
SequelSpeak/
├── .venv/                      # Virtual environment (created during setup)
├── start.sh                    # Quick start script for both servers
├── backend/                    # FastAPI backend
│   ├── main.py                # FastAPI application
│   ├── config.py              # Pydantic settings
│   ├── requirements.txt       # Python dependencies
│   ├── .env                   # Environment configuration (not in git)
│   ├── api/v1/                # API endpoints
│   ├── services/              # Business logic
│   ├── schemas/               # Pydantic models
│   ├── utils/                 # Helper utilities
│   └── tests/                 # Pytest test suite
└── frontend/                  # React + TypeScript frontend
    ├── src/
    │   ├── components/       # React components
    │   ├── hooks/            # Custom React hooks
    │   ├── services/         # API clients
    │   └── types/            # TypeScript types
    ├── package.json
    └── .env                  # Frontend config (not in git)
```

## Development

### Backend Development

```bash
# Activate virtual environment
source .venv/bin/activate

# Start backend only (from project root)
cd backend
uvicorn main:app --reload --port 8000

# Run tests (basic)
cd ..
pytest backend/tests/ -v

# Run tests with coverage report
pytest backend/tests/ --cov=backend/services --cov=backend/api --cov=backend/utils --cov-report=html
# View coverage report: open backend/htmlcov/index.html

# Run integration tests (requires Redis running)
docker run -d -p 6379:6379 redis:7-alpine
pytest backend/tests/ -v -m integration
```

### Frontend Development

```bash
# Start frontend only
cd frontend
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

## Key Features

### Connection Management
- ✅ Async connection pooling with psycopg
- ✅ Secure credential handling (never logged)
- ✅ Automatic retry with exponential backoff
- ✅ Circuit breaker for database protection
- ✅ Health monitoring with timestamp tracking

### Security
- ✅ Input validation (SQL/command injection prevention)
- ✅ Credential masking in logs
- ✅ Rate limiting on connection endpoints
- ✅ CORS configuration per environment
- ✅ No password storage (profiles store metadata only)

### Observability
- ✅ Structured JSON logging in production
- ✅ Correlation IDs for request tracing
- ✅ Connection pool statistics
- ✅ Health check endpoint with latency metrics

## Configuration

### Backend Configuration

Key environment variables in `backend/.env`:

```env
# Required
ENVIRONMENT=development          # development | staging | production
ALLOWED_ORIGINS=*               # CORS origins (use * only in dev)

# Optional
DB_CONNECTION_TIMEOUT=10        # Connection timeout in seconds
DB_POOL_MIN_SIZE=1             # Min connections in pool
DB_POOL_MAX_SIZE=5             # Max connections in pool
HEALTH_CHECK_DB_URL=postgres://user:pass@host:5432/db
```

See `backend/.env.example` for full configuration options.

### Frontend Configuration

Key environment variables in `frontend/.env`:

```env
VITE_API_URL=http://localhost:8000
```

## Testing

### Backend Test Coverage

- **38 total tests** with 100% pass rate
- **91% code coverage** for connection services
- Tests cover: URL parsing, connection logic, security, error handling

```bash
# Run specific test categories
pytest backend/tests/test_connection.py -v              # URL parsing
pytest backend/tests/test_connection_service.py -v      # Connection logic
pytest backend/tests/test_no_credential_leak.py -v      # Security
```

## Documentation

- **Backend API**: http://localhost:8000/docs (Swagger UI)
- **Backend README**: [backend/README.md](backend/README.md)
- **Frontend README**: [frontend/README.md](frontend/README.md)

## License

[Add your license here]

## Contributing

[Add contributing guidelines here]
