import pytest
from httpx import AsyncClient
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from schemas.profile import ProfileCreate, ProfileUpdate
from main import app

# We will need to mock the backend ProfileService because it uses Redis internally
@pytest.fixture
def mock_profile_service():
    with patch("api.v1.profiles.profile_service") as mock_service:
        yield mock_service

@pytest.fixture
def mock_auth():
    with patch("api.v1.profiles.verify_clerk_token") as mock_verify:
        mock_verify.return_value = {"sub": "test_user_123"}
        yield mock_verify

@pytest.mark.asyncio
async def test_get_profiles(client: AsyncClient, mock_profile_service, mock_auth):
    mock_profile_service.get_profiles = AsyncMock(return_value=[
        {"id": "c1", "name": "Test DB", "host": "localhost", "port": "5432", "username": "pg", "database": "test", "createdAt": "2025-01-01T00:00:00Z"}
    ])
    
    app_dependency_overrides = app.dependency_overrides
    from utils.auth import verify_clerk_token
    app.dependency_overrides[verify_clerk_token] = lambda: {"sub": "test_user_123"}
    
    response = await client.get("/api/v1/profiles")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["id"] == "c1"
    
    # Restore
    app.dependency_overrides = app_dependency_overrides

@pytest.mark.asyncio
async def test_create_profile(client: AsyncClient, mock_profile_service, mock_auth):
    mock_profile_service.create_profile = AsyncMock(return_value={
        "id": "c2", "name": "New DB", "host": "local", "port": "5432", "username": "user", "database": "db", "createdAt": "2025-01-01T00:00:00Z"
    })
    
    app_dependency_overrides = app.dependency_overrides
    from utils.auth import verify_clerk_token
    app.dependency_overrides[verify_clerk_token] = lambda: {"sub": "user1"}
    
    profile_data = {
        "name": "New DB",
        "host": "local",
        "port": "5432",
        "username": "user",
        "database": "db",
        "password": "secret_password"
    }
    
    response = await client.post("/api/v1/profiles", json=profile_data)
    assert response.status_code == 200
    assert response.json()["id"] == "c2"
    assert "password" not in response.json()
    
    app.dependency_overrides = app_dependency_overrides

@pytest.mark.asyncio
async def test_update_profile(client: AsyncClient, mock_profile_service, mock_auth):
    mock_profile_service.update_profile = AsyncMock(return_value={
        "id": "c1", "name": "Updated", "host": "local", "port": "5432", "username": "user", "database": "db", "createdAt": "2025-01-01T00:00:00Z"
    })
    
    app_dependency_overrides = app.dependency_overrides
    from utils.auth import verify_clerk_token
    app.dependency_overrides[verify_clerk_token] = lambda: {"sub": "test_user"}
    
    response = await client.put("/api/v1/profiles/c1", json={"name": "Updated"})
    assert response.status_code == 200
    assert response.json()["name"] == "Updated"
    
    app.dependency_overrides = app_dependency_overrides

@pytest.mark.asyncio
async def test_delete_profile(client: AsyncClient, mock_profile_service, mock_auth):
    mock_profile_service.delete_profile = AsyncMock(return_value=True)
    
    app_dependency_overrides = app.dependency_overrides
    from utils.auth import verify_clerk_token
    app.dependency_overrides[verify_clerk_token] = lambda: {"sub": "test_user"}
    
    response = await client.delete("/api/v1/profiles/c1")
    assert response.status_code == 204
    
    mock_profile_service.delete_profile = AsyncMock(return_value=False)
    response = await client.delete("/api/v1/profiles/c2")
    assert response.status_code == 404
    
    app.dependency_overrides = app_dependency_overrides
