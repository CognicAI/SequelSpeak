"""
Centralized logging configuration for SequelSpeak Backend.

Provides environment-specific logging with:
- Structured JSON logging for production
- Human-readable format for development
- Log rotation and file output
- Request correlation ID support
"""
import logging
import logging.handlers
import sys
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from config import settings


class JSONFormatter(logging.Formatter):
    """
    Custom JSON formatter for structured logging in production.
    Outputs logs in JSON format for easy parsing by log aggregation tools.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add correlation ID if present (set by middleware)
        if hasattr(record, 'correlation_id'):
            log_data["correlation_id"] = record.correlation_id
        
        # Add extra fields
        if hasattr(record, 'extra_fields'):
            log_data.update(record.extra_fields)
        
        return json.dumps(log_data)


class CorrelationIdFilter(logging.Filter):
    """
    Filter that adds correlation ID to log records.
    Correlation ID is stored in contextvars and set by middleware.
    """
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Add correlation ID to record if available."""
        # Import here to avoid circular dependency
        try:
            from contextvars import ContextVar
            correlation_id_var: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)
            correlation_id = correlation_id_var.get()
            if correlation_id:
                record.correlation_id = correlation_id
        except Exception:
            pass  # If correlation ID is not available, continue without it
        
        return True


def get_log_level(environment: str) -> int:
    """
    Get appropriate log level based on environment.
    
    Args:
        environment: The application environment (development, staging, production)
        
    Returns:
        Logging level constant
    """
    level_map = {
        'development': logging.DEBUG,
        'staging': logging.INFO,
        'production': logging.WARNING,
    }
    return level_map.get(environment, logging.INFO)


def setup_logging():
    """
    Configure logging for the application with environment-specific settings.
    
    - Development: Human-readable format to console (DEBUG level)
    - Staging: Human-readable format to console + file (INFO level)
    - Production: JSON format to console + rotating file (WARNING level)
    
    File logs are stored in backend/logs/ directory with automatic rotation.
    """
    # Determine log level based on environment
    log_level = get_log_level(settings.environment)
    
    # Create logs directory if it doesn't exist
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()
    
    # Add correlation ID filter to all handlers
    correlation_filter = CorrelationIdFilter()
    
    # === Console Handler ===
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.addFilter(correlation_filter)
    
    if settings.environment == 'production':
        # JSON format for production (easier to parse in log aggregation tools)
        console_formatter = JSONFormatter()
    else:
        # Human-readable format for development/staging
        console_formatter = logging.Formatter(
            fmt='%(asctime)s - %(name)-25s - %(levelname)-8s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # === File Handler with Rotation ===
    # Only add file handler in staging and production
    if settings.environment in ['staging', 'production']:
        log_file = log_dir / f"sequelspeak_{settings.environment}.log"
        
        # Rotating file handler: max 10MB per file, keep 5 backup files
        file_handler = logging.handlers.RotatingFileHandler(
            filename=str(log_file),
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(log_level)
        file_handler.addFilter(correlation_filter)
        
        # Always use JSON format for file logs (easier to parse)
        file_formatter = JSONFormatter()
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
    
    # === Configure third-party loggers ===
    # Reduce noise from verbose libraries
    logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
    logging.getLogger('uvicorn.error').setLevel(logging.INFO)
    
    # Keep our application logs at configured level
    logging.getLogger('backend').setLevel(log_level)
    
    # Log startup message
    logger = logging.getLogger(__name__)
    logger.info(
        f"Logging initialized for {settings.environment} environment at {logging.getLevelName(log_level)} level"
    )
    
    return root_logger
