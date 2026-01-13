import psycopg
from urllib.parse import urlparse, quote_plus, urlunparse

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
            return {"valid": False, "message": f"URL Parsing Error: {str(e)}"}

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
             # This catches mostly authentication or host unreachable errors
             error_msg = str(e).strip()
             return {"success": False, "message": f"Connection Failed: {error_msg}"}
        except Exception as e:
            return {"success": False, "message": f"An unexpected error occurred: {str(e)}"}
