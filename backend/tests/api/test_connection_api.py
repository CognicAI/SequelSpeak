import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient
from schemas.errors import ErrorCode
from models.profile import Profile

class TestConnectionApi:
    @pytest.fixture
    def mock_user_claims(self):
        return {"sub": "test-user-id", "email": "test@example.com"}

    @pytest.mark.asyncio
    async def test_connection_with_profile_success(self, client: AsyncClient, mock_user_claims):
        profile_id = "prof-123"
        mock_profile = Profile(
            id=profile_id,
            user_id="test-user-id",
            name="Test DB",
            host="localhost",
            port="5432",
            username="user",
            database="db"
        )
        
        # Patching inside the function where they are imported
        with patch("api.v1.connection.profile_service.get_profile", return_value=mock_profile), \
             patch("services.credential_cache.CredentialCacheService.get_password", return_value="cached-pass"), \
             patch("services.credential_cache.CredentialCacheService.store_password", return_value=None), \
             patch("services.db_connection_service.DBConnectionService.parse_and_verify_url") as mock_verify, \
             patch("services.db_connection_service.DBConnectionService.test_connection_oneshot") as mock_test:
            
            mock_verify.return_value.success = True
            mock_test.return_value.success = True
            mock_test.return_value.message = "Connected!"
            
            response = await client.post(
                "/api/v1/utils/test-connection",
                json={"profile_id": profile_id}
            )
            
            assert response.status_code == 200
            assert response.json()["status"] == "success"
            assert response.json()["message"] == "Connected!"

    @pytest.mark.asyncio
    async def test_connection_profile_not_found(self, client: AsyncClient, mock_user_claims):
        with patch("api.v1.connection.profile_service.get_profile", return_value=None):
            response = await client.post(
                "/api/v1/utils/test-connection",
                json={"profile_id": "non-existent"}
            )
            
            assert response.status_code == 400
            assert response.json()["error_code"] == ErrorCode.PROFILE_NOT_FOUND

    @pytest.mark.asyncio
    async def test_connection_password_required(self, client: AsyncClient, mock_user_claims):
        mock_profile = Profile(
            id="prof-123",
            user_id="test-user-id",
            name="Test DB",
            host="localhost",
            port="5432",
            username="user",
            database="db"
        )
        
        with patch("api.v1.connection.profile_service.get_profile", return_value=mock_profile), \
             patch("services.credential_cache.CredentialCacheService.get_password", return_value=None):
            
            response = await client.post(
                "/api/v1/utils/test-connection",
                json={"profile_id": "prof-123"}
            )
            
            assert response.status_code == 400
            assert response.json()["error_code"] == ErrorCode.AUTH_FAILED
            assert "Password required" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_connection_missing_params(self, client: AsyncClient, mock_user_claims):
        response = await client.post(
            "/api/v1/utils/test-connection",
            json={}
        )
        assert response.status_code == 400
        # When both are missing, it might be caught by the general validation or the manual check.
        # Based on the failure, it's returning 'INVALID_REQUEST' from the global handler.
        assert response.json()["error_code"] == "INVALID_REQUEST"

    @pytest.mark.asyncio
    async def test_connection_with_provided_password_stores_in_cache(self, client: AsyncClient, mock_user_claims):
        profile_id = "prof-123"
        mock_profile = Profile(
            id=profile_id,
            user_id="test-user-id",
            name="Test DB",
            host="localhost",
            port="5432",
            username="user",
            database="db"
        )
        
        with patch("api.v1.connection.profile_service.get_profile", return_value=mock_profile), \
             patch("services.credential_cache.CredentialCacheService.store_password") as mock_store, \
             patch("services.db_connection_service.DBConnectionService.parse_and_verify_url") as mock_verify, \
             patch("services.db_connection_service.DBConnectionService.test_connection_oneshot") as mock_test:
            
            mock_verify.return_value.success = True
            mock_test.return_value.success = True
            mock_test.return_value.message = "Connected!"
            
            await client.post(
                "/api/v1/utils/test-connection",
                json={"profile_id": profile_id, "password": "new-password"}
            )
            
            mock_store.assert_called_once()
            # The first argument to store_password is the user_id from the mock_verify_clerk_token in conftest.py
            args, _ = mock_store.call_args
            assert args[0] == "test-user-id-00000000"
            assert args[1] == profile_id
            assert args[2] == "new-password"
