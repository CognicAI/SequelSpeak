# Backend Service

FastAPI backend for SequelSpeak with PostgreSQL connection management.

## Configuration

The backend can be configured using environment variables. Create a `.env` file in the backend directory with the following variables:

### Environment Variables

| Variable | Description | Default | Type |
|----------|-------------|---------|------|
| `DB_CONNECTION_TIMEOUT` | PostgreSQL connection timeout in seconds | `10` | integer |
| `APP_NAME` | Application name | `"FastAPI Backend"` | string |
| `ENVIRONMENT` | Environment (development/production) | `"development"` | string |

### Example `.env` file

```env
DB_CONNECTION_TIMEOUT=15
APP_NAME=SequelSpeak Backend
ENVIRONMENT=production
```

## PostgreSQL Connection

The backend establishes PostgreSQL connections using `psycopg` with the following features:

- ✅ **Configurable timeout**: Set via `DB_CONNECTION_TIMEOUT` environment variable
- ✅ **Secure credential handling**: No plain-text credentials in logs
- ✅ **Graceful error handling**: User-friendly error messages with detailed server-side logging
- ✅ **Connection validation**: Automatic connection testing with `SELECT 1` query

## Testing

### Test Coverage

- **38 total tests** with 100% pass rate
- **91% code coverage** for `services/db_connection_service.py`
- **21 URL parsing tests** covering valid/invalid URLs and special characters
- **16 connection logic tests** covering all error scenarios
- **1 credential leak test** ensuring security

### Running Tests

```bash
# Setup (first time only)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Run all tests
pytest tests/ -v

# Run with coverage report
pytest tests/ -v --cov=services --cov=api --cov-report=term-missing

# Run specific test files
pytest tests/test_connection.py -v                    # URL parsing tests
pytest tests/test_connection_service.py -v            # Connection logic tests

# Generate HTML coverage report
pytest tests/ --cov=services --cov=api --cov-report=html
# Open htmlcov/index.html in your browser

# Run tests with markers
pytest tests/ -v -m unit                              # Only unit tests
```

### Test Organization

```
tests/
├── test_connection.py              # URL parsing tests (21 tests)
├── test_connection_service.py      # Connection logic tests (16 tests)
├── test_no_credential_leak.py      # Security tests (1 test)
└── IMPLEMENTATION_WALKTHROUGH.md   # Implementation documentation
```

### Continuous Integration

Tests automatically run on GitHub Actions for:
- Python versions: 3.10, 3.11, 3.12
- Triggers: Push to main/develop, Pull requests
- Coverage reports uploaded to Codecov

## Development

### Setup Development Environment

```bash
# Clone repository
git clone <repository-url>
cd SequelSpeak/backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env

# Run tests to verify setup
pytest tests/ -v
```

### Code Quality

- **Linting**: Follow PEP 8 style guidelines
- **Testing**: Maintain >80% code coverage
- **Security**: No credentials in logs or error messages
- **Documentation**: Update tests when adding features


