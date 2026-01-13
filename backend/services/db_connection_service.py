import logging
import psycopg
from urllib.parse import urlparse, quote_plus, urlunparse

# Configure logger
logger = logging.getLogger(__name__)

class DBConnectionService:
    @staticmethod
    def parse_and_verify_url(url: str) -> dict:
        """
        Parses the connection URL and validates its structure.
        Returns a result dictionary with status and message.
        """
        try:
            parsed = urlparse(url)
            if not parsed.scheme or 'postgres' not in parsed.scheme:
                 return {"valid": False, "message": "Invalid URL scheme. Must be postgres:// or postgresql://"}
            
            # Basic structural check
            if not parsed.netloc: # Includes host:port or just host
                return {"valid": False, "message": "Invalid URL structure: Host is missing."}

            return {"valid": True, "message": "Valid structure"}
        except Exception as e:
            logger.error(f"URL Parsing Error: {str(e)}")
            return {"valid": False, "message": "Invalid URL format."}

    @staticmethod
    def test_connection(url: str) -> dict:
        """
        Attempts to connect to the PostgreSQL database using the provided URL.
        Handles password encoding if necessary.
        """
        try:
            # We trust psycopg to handle the connection string format mostly,
            # but we can do a quick check or encoding if we were constructing it manually.
            # Here since we get a full string, we pass it directly to psycopg.
            # Psycopg 3 validates well.
            
            with psycopg.connect(url, connect_timeout=5) as conn:
                # Just opening the connection is enough to verify credentials and reachability
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    result = cur.fetchone()
                    if result == (1,):
                        return {"success": True, "message": "Connection successful!"}
                    else:
                        return {"success": False, "message": "Connection verification query failed."}
                        
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
                user_message = (
                    "Connection failed: Authentication error. "
                    "Please verify your username, password, and access permissions."
                )

            # Database name / database not found issues
            elif "does not exist" in details_lower and "database" in details_lower:
                user_message = (
                    "Connection failed: The specified database could not be found. "
                    "Please verify the database name and that it exists on the server."
                )

            # Network / connectivity / host/port issues
            elif (
                "could not connect to server" in details_lower
                or "connection refused" in details_lower
                or "could not translate host name" in details_lower
                or "network is unreachable" in details_lower
                or "timeout expired" in details_lower
                or "timed out" in details_lower
            ):
                user_message = (
                    "Connection failed: Unable to reach the database server. "
                    "Please verify the host, port, and network connectivity."
                )

            # Fallback generic message
            else:
                user_message = (
                    "Connection failed: Unable to connect to the database. "
                    "Please verify your host, port, database name, and credentials."
                )

            return {
                "success": False,
                "message": user_message,
            }
        except Exception as e:
            logger.error(f"Unexpected error during connection test: {str(e)}", exc_info=True)
            return {"success": False, "message": "An unexpected error occurred while testing the connection."}
