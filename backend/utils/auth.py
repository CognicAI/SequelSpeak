"""
Authentication utilities for Clerk JWT verification.

Provides FastAPI dependency for verifying Clerk JWT tokens and extracting user claims.
"""

import logging
from typing import Dict, Any, Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from clerk_backend_api import authenticate_request
from clerk_backend_api.security.types import AuthenticateRequestOptions
from config import settings

logger = logging.getLogger(__name__)

# HTTP Bearer token security scheme
security = HTTPBearer(auto_error=False)


async def verify_clerk_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Dict[str, Any]:
    """
    Verify Clerk JWT token and extract user claims.
    
    This dependency should be added to any endpoint that requires user authentication.
    It validates the JWT token signature, expiration, and issuer using Clerk's JWKS.
    
    Usage:
        @router.post("/protected-endpoint")
        async def protected_endpoint(
            user_claims: dict = Depends(verify_clerk_token)
        ):
            user_id = user_claims["sub"]
            # ... endpoint logic
    
    Args:
        request: FastAPI Request object
        credentials: HTTP Bearer token from Authorization header
        
    Returns:
        Dictionary of JWT claims including:
        - sub: User ID (Clerk user identifier)
        - email: User email address
        - exp: Token expiration timestamp
        - iat: Token issued at timestamp
        - iss: Token issuer (Clerk instance URL)
        
    Raises:
        HTTPException 401: If token is missing, invalid, expired, or malformed
        HTTPException 500: If authentication service is unavailable
    """
    # Check if authentication is configured
    if not settings.clerk_secret_key:
        logger.error("Authentication attempt but CLERK_SECRET_KEY not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication is not configured on this server"
        )
    
    # Extract token from Bearer scheme, with SSE fallback via query param.
    # EventSource cannot send custom Authorization headers, so we allow
    # ?access_token=<jwt> for endpoints that use streaming.
    auth_request = request
    token: Optional[str] = None
    if credentials is not None and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    else:
        query_token = request.query_params.get("access_token")
        if query_token:
            token = query_token
            # Build a derived Request with Authorization header injected.
            # We avoid mutating the original request because headers may
            # already be cached by earlier dependencies.
            scope_headers = list(request.scope.get("headers", []))
            has_auth_header = any(k.lower() == b"authorization" for k, _ in scope_headers)
            if not has_auth_header:
                scope_headers.append((b"authorization", f"Bearer {token}".encode("utf-8")))
            scope_copy = dict(request.scope)
            scope_copy["headers"] = scope_headers
            auth_request = Request(scope_copy, request.receive)
        else:
            logger.warning("Authentication failed: Missing or invalid authorization scheme")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required. Please provide a valid access token.",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    if not token:
        logger.warning("Authentication failed: No token provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a valid access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        # Configure authentication options
        # Use secret_key to let Clerk SDK fetch JWKS from Clerk's servers
        # This handles RS256 token verification properly
        auth_options = AuthenticateRequestOptions(
            secret_key=settings.clerk_secret_key,
        )
        
        # Authenticate request using Clerk SDK
        # Pass the FastAPI Request object directly - Clerk SDK will extract what it needs
        request_state = authenticate_request(auth_request, auth_options)
        
        # Check authentication result
        if not request_state.is_signed_in:
            # Token is invalid, expired, or malformed
            error_reason = getattr(request_state, 'reason', 'unknown')
            error_message = getattr(request_state, 'message', 'Authentication failed')
            
            logger.warning(f"Authentication failed: {error_reason} - {error_message}")
            
            # Provide user-friendly error messages based on reason
            if 'expired' in str(error_reason).lower():
                detail = "Access token has expired. Please sign in again."
            elif 'invalid' in str(error_reason).lower() or 'signature' in str(error_reason).lower():
                detail = "Invalid access token. Please sign in again."
            else:
                detail = "Authentication failed. Please sign in again."
            
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=detail,
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Extract claims from authenticated session
        # The payload contains the JWT claims directly
        session_claims: Dict[str, Any] = request_state.payload  # type: ignore[assignment]
        
        # Log successful authentication (don't log full claims for privacy)
        user_id = str(session_claims.get("sub", "unknown"))  # type: ignore
        logger.info(f"User authenticated successfully: {user_id[:8] if len(user_id) > 8 else user_id}...")
        
        return session_claims  # type: ignore[return-value]
        
    except HTTPException:
        # Re-raise our own HTTPExceptions
        raise
    except Exception as e:
        # Handle unexpected errors
        logger.error(f"Unexpected authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

