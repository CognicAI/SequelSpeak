import logging
import psycopg
from urllib.parse import urlparse, quote_plus, urlunparse
from config import settings
from schemas.errors import ErrorCode, ConnectionResult

# Configure logger
logger = logging.getLogger(__name__)

class DBConnectionService:
    @staticmethod
    def parse_and_verify_url(url: str) -> ConnectionResult:
        """
        Parses the connection URL and validates its structure.
        Returns a ConnectionResult with success status and message.
        """
        try:
            parsed = urlparse(url)
            if not parsed.scheme or 'postgres' not in parsed.scheme:
                return ConnectionResult(
                    success=False,
                    message="Invalid URL scheme. Must be postgres:// or postgresql://",
                    error_code=ErrorCode.INVALID_URL
                )
            
            # Basic structural check
            if not parsed.netloc:  # Includes host:port or just host
                return ConnectionResult(
                    success=False,
                    message="Invalid URL structure: Host is missing.",
                    error_code=ErrorCode.INVALID_URL
                )

            return ConnectionResult(success=True, message="Valid structure")
        except Exception as e:
            logger.error(f"URL Parsing Error: {str(e)}")
            return ConnectionResult(
                success=False,
                message="Invalid URL format.",
                error_code=ErrorCode.INVALID_URL
            )

    @staticmethod
    def test_connection(url: str) -> ConnectionResult:
        """
        Attempts to connect to the PostgreSQL database using the provided URL.
        Handles password encoding if necessary.
        """
        try:
            # We trust psycopg to handle the connection string format mostly,
            # but we can do a quick check or encoding if we were constructing it manually.
            # Here since we get a full string, we pass it directly to psycopg.
            # Psycopg 3 validates well.
            
            with psycopg.connect(url, connect_timeout=settings.db_connection_timeout) as conn:
                # Just opening the connection is enough to verify credentials and reachability
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    result = cur.fetchone()
                    if result == (1,):
                        return ConnectionResult(success=True, message="Connection successful!")
                    else:
                        return ConnectionResult(
                            success=False,
                            message="Connection verification query failed.",
                            error_code=ErrorCode.CONNECTION_ERROR
                        )
                        
        except psycopg.OperationalError as e:
            # Log the full error for debugging but return a sanitized message to user
            error_details = str(e).strip()
            logger.error(f"Database Connection Failed: {error_details}")

            # Provide slightly more specific (but still safe) messages for common failure modes.
            details_lower = error_details.lower()

            # Authentication / authorization issues
            if (
                "password authentication failed" in details_lower
                or "authentication failed" in details_lower
                or "no pg_hba.conf entry" in details_lower
                or "permission denied" in details_lower
            ):
                return ConnectionResult(
                    success=False,
                    message=(
                        "Connection failed: Authentication error. "
                        "Please verify your username, password, and access permissions."
                    ),
                    error_code=ErrorCode.AUTH_FAILED
                )

            # Database name / database not found issues
            elif "does not exist" in details_lower and "database" in details_lower:
                return ConnectionResult(
                    success=False,
                    message=(
                        "Connection failed: The specified database could not be found. "
                        "Please verify the database name and that it exists on the server."
                    ),
                    error_code=ErrorCode.DATABASE_NOT_FOUND
                )

            # SSL/TLS certificate issues
            elif (
                "ssl error" in details_lower
                or "ssl connection" in details_lower
                or "ssl handshake" in details_lower
                or "certificate verify" in details_lower
                or "certificate validation" in details_lower
                or "certificate_verify_failed" in details_lower
                or "tlsv1" in details_lower
                or "ssl_error" in details_lower
                or "certificate expired" in details_lower
                or "certificate invalid" in details_lower
                or "self-signed certificate" in details_lower
            ):
                return ConnectionResult(
                    success=False,
                    message=(
                        "Connection failed: SSL/TLS certificate error. "
                        "Please verify your SSL configuration and certificate validity."
                    ),
                    error_code=ErrorCode.SSL_ERROR
                )

            # Timeout issues (check before general network errors)
            elif (
                "timeout expired" in details_lower
                or "timed out" in details_lower
                or "connection timeout" in details_lower
            ):
                return ConnectionResult(
                    success=False,
                    message=(
                        f"Connection failed: Connection attempt timed out after {settings.db_connection_timeout} seconds. "
                        "Please verify the host, port, and network connectivity, or try increasing the timeout."
                    ),
                    error_code=ErrorCode.TIMEOUT
                )

            # Network / connectivity / host/port issues
            elif (
                "could not connect to server" in details_lower
                or "connection refused" in details_lower
                or "connection reset" in details_lower
                or "could not translate host name" in details_lower
                or "network is unreachable" in details_lower
            ):
                return ConnectionResult(
                    success=False,
                    message=(
                        "Connection failed: Unable to reach the database server. "
                        "Please verify the host, port, and network connectivity."
                    ),
                    error_code=ErrorCode.HOST_UNREACHABLE
                )

            # Fallback generic message
            else:
                return ConnectionResult(
                    success=False,
                    message=(
                        "Connection failed: Unable to connect to the database. "
                        "Please verify your host, port, database name, and credentials."
                    ),
                    error_code=ErrorCode.CONNECTION_ERROR
                )

        except Exception as e:
            logger.error(f"Unexpected error during connection test: {str(e)}", exc_info=True)
            return ConnectionResult(
                success=False,
                message="An unexpected error occurred while testing the connection.",
                error_code=ErrorCode.CONNECTION_ERROR
            )

