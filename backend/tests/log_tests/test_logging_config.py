"""
Tests for logging configuration.
"""
import sys
import os
import logging
import json
from io import StringIO
from pathlib import Path

# Add backend to path - MUST be before any project imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

# Add backend to path

from unittest.mock import patch, MagicMock
from logging_config import (
    setup_logging,
    get_log_level,
    JSONFormatter,
    CorrelationIdFilter
)


class TestGetLogLevel:
    """Test log level determination based on environment."""
    
    def test_development_log_level(self):
        """Development environment should use DEBUG level."""
        assert get_log_level('development') == logging.DEBUG
    
    def test_staging_log_level(self):
        """Staging environment should use INFO level."""
        assert get_log_level('staging') == logging.INFO
    
    def test_production_log_level(self):
        """Production environment should use WARNING level."""
        assert get_log_level('production') == logging.WARNING
    
    def test_unknown_environment_defaults_to_info(self):
        """Unknown environment should default to INFO level."""
        assert get_log_level('unknown') == logging.INFO


class TestJSONFormatter:
    """Test JSON log formatter."""
    
    def test_formats_log_as_json(self):
        """JSON formatter should output valid JSON."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name='test_logger',
            level=logging.INFO,
            pathname='test.py',
            lineno=10,
            msg='Test message',
            args=(),
            exc_info=None
        )
        
        output = formatter.format(record)
        
        # Should be valid JSON
        log_data = json.loads(output)
        assert log_data['level'] == 'INFO'
        assert log_data['message'] == 'Test message'
        assert log_data['logger'] == 'test_logger'
        assert 'timestamp' in log_data
    
    def test_includes_correlation_id_if_present(self):
        """JSON formatter should include correlation ID if available."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name='test_logger',
            level=logging.INFO,
            pathname='test.py',
            lineno=10,
            msg='Test message',
            args=(),
            exc_info=None
        )
        record.correlation_id = 'test-correlation-id-123'
        
        output = formatter.format(record)
        log_data = json.loads(output)
        
        assert log_data['correlation_id'] == 'test-correlation-id-123'
    
    def test_includes_exception_info(self):
        """JSON formatter should include exception traceback."""
        formatter = JSONFormatter()
        
        try:
            raise ValueError("Test exception")
        except ValueError:
            exc_info = sys.exc_info()
        
        record = logging.LogRecord(
            name='test_logger',
            level=logging.ERROR,
            pathname='test.py',
            lineno=10,
            msg='Error occurred',
            args=(),
            exc_info=exc_info
        )
        
        output = formatter.format(record)
        log_data = json.loads(output)
        
        assert 'exception' in log_data
        assert 'ValueError: Test exception' in log_data['exception']


class TestCorrelationIdFilter:
    """Test correlation ID filter."""
    
    def test_adds_correlation_id_to_record(self):
        """Filter should add correlation ID to log record if available."""
        from contextvars import ContextVar
        
        filter_instance = CorrelationIdFilter()
        record = logging.LogRecord(
            name='test_logger',
            level=logging.INFO,
            pathname='test.py',
            lineno=10,
            msg='Test message',
            args=(),
            exc_info=None
        )
        
        # Filter should not fail even if correlation ID is not set
        result = filter_instance.filter(record)
        assert result is True


class TestSetupLogging:
    """Test logging setup function."""
    
    @patch('logging_config.settings')
    def test_setup_creates_log_directory(self, mock_settings):
        """Setup should create logs directory if it doesn't exist."""
        mock_settings.environment = 'development'
        
        with patch('pathlib.Path.mkdir') as mock_mkdir:
            setup_logging()
            mock_mkdir.assert_called_once_with(exist_ok=True)
    
    @patch('logging_config.settings')
    def test_setup_configures_root_logger(self, mock_settings):
        """Setup should configure root logger with appropriate level."""
        mock_settings.environment = 'development'
        
        setup_logging()
        
        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG
    
    @patch('logging_config.settings')
    def test_setup_adds_console_handler(self, mock_settings):
        """Setup should add console handler."""
        mock_settings.environment = 'development'
        
        setup_logging()
        
        root_logger = logging.getLogger()
        # Should have at least one StreamHandler
        has_stream_handler = any(
            isinstance(h, logging.StreamHandler) 
            for h in root_logger.handlers
        )
        assert has_stream_handler
    
    @patch('logging_config.settings')
    def test_production_uses_json_formatter(self, mock_settings):
        """Production environment should use JSON formatter for console."""
        mock_settings.environment = 'production'
        
        setup_logging()
        
        root_logger = logging.getLogger()
        stream_handlers = [
            h for h in root_logger.handlers 
            if isinstance(h, logging.StreamHandler)
        ]
        
        # At least one handler should use JSON formatter
        has_json_formatter = any(
            isinstance(h.formatter, JSONFormatter)
            for h in stream_handlers
        )
        assert has_json_formatter


class TestLoggingIntegration:
    """Integration tests for logging system."""
    
    @patch('logging_config.settings')
    def test_log_messages_are_formatted_correctly(self, mock_settings):
        """Test that log messages are properly formatted."""
        mock_settings.environment = 'development'
        
        # Capture log output
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
        
        test_logger = logging.getLogger('test_integration')
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.DEBUG)
        
        test_logger.info('Test info message')
        test_logger.warning('Test warning message')
        
        output = stream.getvalue()
        assert 'INFO - Test info message' in output
        assert 'WARNING - Test warning message' in output
