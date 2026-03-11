import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException, Request, status
from utils.auth import verify_clerk_token
from config import settings

class TestAuthUnit:
    @pytest.fixture
    def mock_request(self):
        return MagicMock(spec=Request)

    @pytest.mark.asyncio
    async def test_verify_clerk_token_no_secret_key(self, mock_request):
        with patch("utils.auth.settings") as mock_settings:
            mock_settings.clerk_secret_key = None
            with pytest.raises(HTTPException) as excinfo:
                await verify_clerk_token(mock_request, None)
            assert excinfo.value.status_code == 500
            assert "Authentication is not configured" in excinfo.value.detail

    @pytest.mark.asyncio
    async def test_verify_clerk_token_no_credentials(self, mock_request):
        with patch("utils.auth.settings") as mock_settings:
            mock_settings.clerk_secret_key = "test-secret"
            with pytest.raises(HTTPException) as excinfo:
                await verify_clerk_token(mock_request, None)
            assert excinfo.value.status_code == 401
            assert "Authentication required" in excinfo.value.detail

    @pytest.mark.asyncio
    async def test_verify_clerk_token_invalid_scheme(self, mock_request):
        from fastapi.security import HTTPAuthorizationCredentials
        credentials = HTTPAuthorizationCredentials(scheme="Basic", credentials="token")
        with patch("utils.auth.settings") as mock_settings:
            mock_settings.clerk_secret_key = "test-secret"
            with pytest.raises(HTTPException) as excinfo:
                await verify_clerk_token(mock_request, credentials)
            assert excinfo.value.status_code == 401
            assert "Authentication required" in excinfo.value.detail

    @pytest.mark.asyncio
    async def test_verify_clerk_token_signed_out(self, mock_request):
        from fastapi.security import HTTPAuthorizationCredentials
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid-token")
        
        mock_state = MagicMock()
        mock_state.is_signed_in = False
        mock_state.reason = "expired"
        mock_state.message = "Token expired"
        
        with patch("utils.auth.settings") as mock_settings, \
             patch("utils.auth.authenticate_request", return_value=mock_state):
            mock_settings.clerk_secret_key = "test-secret"
            with pytest.raises(HTTPException) as excinfo:
                await verify_clerk_token(mock_request, credentials)
            assert excinfo.value.status_code == 401
            assert "expired" in excinfo.value.detail.lower()

    @pytest.mark.asyncio
    async def test_verify_clerk_token_invalid_signature(self, mock_request):
        from fastapi.security import HTTPAuthorizationCredentials
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid-token")
        
        mock_state = MagicMock()
        mock_state.is_signed_in = False
        mock_state.reason = "invalid signature"
        
        with patch("utils.auth.settings") as mock_settings, \
             patch("utils.auth.authenticate_request", return_value=mock_state):
            mock_settings.clerk_secret_key = "test-secret"
            with pytest.raises(HTTPException) as excinfo:
                await verify_clerk_token(mock_request, credentials)
            assert excinfo.value.status_code == 401
            assert "invalid" in excinfo.value.detail.lower()

    @pytest.mark.asyncio
    async def test_verify_clerk_token_success(self, mock_request):
        from fastapi.security import HTTPAuthorizationCredentials
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid-token")
        
        mock_state = MagicMock()
        mock_state.is_signed_in = True
        mock_state.payload = {"sub": "user-123", "email": "user@example.com"}
        
        with patch("utils.auth.settings") as mock_settings, \
             patch("utils.auth.authenticate_request", return_value=mock_state):
            mock_settings.clerk_secret_key = "test-secret"
            result = await verify_clerk_token(mock_request, credentials)
            assert result["sub"] == "user-123"

    @pytest.mark.asyncio
    async def test_verify_clerk_token_unexpected_error(self, mock_request):
        from fastapi.security import HTTPAuthorizationCredentials
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
        
        with patch("utils.auth.settings") as mock_settings, \
             patch("utils.auth.authenticate_request", side_effect=ValueError("Unexpected")):
            mock_settings.clerk_secret_key = "test-secret"
            with pytest.raises(HTTPException) as excinfo:
                await verify_clerk_token(mock_request, credentials)
            assert excinfo.value.status_code == 401
            assert "Authentication failed" in excinfo.value.detail

    @pytest.mark.asyncio
    async def test_verify_clerk_token_empty_token(self, mock_request):
        from fastapi.security import HTTPAuthorizationCredentials
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="")
        with patch("utils.auth.settings") as mock_settings:
            mock_settings.clerk_secret_key = "test-secret"
            with pytest.raises(HTTPException) as excinfo:
                await verify_clerk_token(mock_request, credentials)
            assert excinfo.value.status_code == 401
            assert "Authentication required" in excinfo.value.detail

    @pytest.mark.asyncio
    async def test_verify_clerk_token_unknown_reason(self, mock_request):
        from fastapi.security import HTTPAuthorizationCredentials
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
        
        mock_state = MagicMock()
        mock_state.is_signed_in = False
        mock_state.reason = "some-unknown-reason"
        
        with patch("utils.auth.settings") as mock_settings, \
             patch("utils.auth.authenticate_request", return_value=mock_state):
            mock_settings.clerk_secret_key = "test-secret"
            with pytest.raises(HTTPException) as excinfo:
                await verify_clerk_token(mock_request, credentials)
            assert excinfo.value.status_code == 401
            assert "authentication failed" in excinfo.value.detail.lower()

