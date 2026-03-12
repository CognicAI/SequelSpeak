import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlmodel.ext.asyncio.session import AsyncSession
from datetime import datetime, timezone
import uuid

from services.profile_service import ProfileService
from models.profile import Profile
from schemas.profile import ProfileCreate, ProfileUpdate

class TestProfileServiceUnit:
    @pytest.fixture
    def mock_engine(self):
        with patch("services.profile_service.async_engine") as mock_eng:
            yield mock_eng

    @pytest.fixture
    def profile_service(self, mock_engine: MagicMock) -> ProfileService:
        return ProfileService()

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        session = AsyncMock(spec=AsyncSession)
        session.__aenter__.return_value = session
        session.__aexit__.return_value = False
        return session

    @pytest.mark.asyncio
    async def test_initialize(self, profile_service: ProfileService, mock_engine: MagicMock) -> None:
        # initialize() is a no-op since Alembic handles schema management
        await profile_service.initialize()  # should complete without error

    @pytest.mark.asyncio
    async def test_get_profiles(self, profile_service: ProfileService, mock_session: AsyncMock) -> None:
        user_id = "test-user"
        profile_id = str(uuid.uuid4())
        mock_profile = Profile(
            id=profile_id,
            user_id=user_id,
            name="Test DB",
            host="localhost",
            port="5432",
            username="user",
            database="db",
            created_at=datetime.now(timezone.utc)
        )

        mock_exec_result = MagicMock()
        mock_exec_result.all.return_value = [mock_profile]
        mock_session.exec.return_value = mock_exec_result

        with patch("services.profile_service.AsyncSession", return_value=mock_session):
            profiles = await profile_service.get_profiles(user_id)

            assert len(profiles) == 1
            assert profiles[0].name == "Test DB"
            assert profiles[0].host == "localhost"

    @pytest.mark.asyncio
    async def test_get_profile(self, profile_service: ProfileService, mock_session: AsyncMock) -> None:
        user_id = "test-user"
        profile_id = str(uuid.uuid4())
        mock_profile = Profile(
            id=profile_id,
            user_id=user_id,
            name="Test DB",
            host="localhost",
            port="5432",
            username="user",
            database="db"
        )

        mock_exec_result = MagicMock()
        mock_exec_result.first.return_value = mock_profile
        mock_session.exec.return_value = mock_exec_result

        with patch("services.profile_service.AsyncSession", return_value=mock_session):
            profile = await profile_service.get_profile(user_id, profile_id)
            assert profile == mock_profile

    @pytest.mark.asyncio
    async def test_create_profile(self, profile_service: ProfileService, mock_session: AsyncMock) -> None:
        user_id = "test-user"
        profile_in = ProfileCreate(
            name="New DB",
            host="remote-host",
            port="5432",
            username="admin",
            database="prod",
            password="password123"
        )

        with patch("services.profile_service.AsyncSession", return_value=mock_session), \
             patch("services.profile_service.credential_cache") as mock_cache:
            mock_cache.store_password = AsyncMock()
            response = await profile_service.create_profile(user_id, profile_in)

            assert response.name == "New DB"
            assert response.host == "remote-host"
            mock_session.add.assert_called_once()
            mock_session.commit.assert_called_once()
            mock_session.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_profile_success(self, profile_service: ProfileService, mock_session: AsyncMock) -> None:
        user_id = "test-user"
        profile_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        mock_profile = Profile(
            id=profile_id,
            user_id=user_id,
            name="Old Name",
            host="localhost",
            port="5432",
            username="user",
            database="db",
            created_at=now
        )

        profile_in = ProfileUpdate(name="New Name", lastUsed=now.isoformat())

        mock_exec_result = MagicMock()
        mock_exec_result.first.return_value = mock_profile
        mock_session.exec.return_value = mock_exec_result

        with patch("services.profile_service.AsyncSession", return_value=mock_session), \
             patch("services.profile_service.credential_cache") as mock_cache:
            mock_cache.store_password = AsyncMock()
            response = await profile_service.update_profile(user_id, profile_id, profile_in)

            assert response is not None
            assert response.name == "New Name"
            assert mock_profile.name == "New Name"
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_profile_not_found(self, profile_service: ProfileService, mock_session: AsyncMock) -> None:
        mock_exec_result = MagicMock()
        mock_exec_result.first.return_value = None
        mock_session.exec.return_value = mock_exec_result

        with patch("services.profile_service.AsyncSession", return_value=mock_session):
            response = await profile_service.update_profile("user", "id", ProfileUpdate(name="New"))
            assert response is None

    @pytest.mark.asyncio
    async def test_create_profile_caches_password(self, profile_service: ProfileService, mock_session: AsyncMock) -> None:
        user_id = "test-user"
        profile_in = ProfileCreate(
            name="New DB",
            host="remote-host",
            port="5432",
            username="admin",
            database="prod",
            password="secret123"
        )

        with patch("services.profile_service.AsyncSession", return_value=mock_session), \
             patch("services.profile_service.credential_cache") as mock_cache:
            mock_cache.store_password = AsyncMock()
            response = await profile_service.create_profile(user_id, profile_in)

            mock_cache.store_password.assert_awaited_once_with(user_id, response.id, "secret123")

    @pytest.mark.asyncio
    async def test_update_profile_caches_password(self, profile_service: ProfileService, mock_session: AsyncMock) -> None:
        user_id = "test-user"
        profile_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        mock_profile = Profile(
            id=profile_id,
            user_id=user_id,
            name="DB",
            host="localhost",
            port="5432",
            username="user",
            database="db",
            created_at=now
        )

        mock_exec_result = MagicMock()
        mock_exec_result.first.return_value = mock_profile
        mock_session.exec.return_value = mock_exec_result

        with patch("services.profile_service.AsyncSession", return_value=mock_session), \
             patch("services.profile_service.credential_cache") as mock_cache:
            mock_cache.store_password = AsyncMock()
            await profile_service.update_profile(user_id, profile_id, ProfileUpdate(password="new-secret"))

            mock_cache.store_password.assert_awaited_once_with(user_id, profile_id, "new-secret")

    @pytest.mark.asyncio
    async def test_update_profile_skips_cache_when_no_password(self, profile_service: ProfileService, mock_session: AsyncMock) -> None:
        user_id = "test-user"
        profile_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        mock_profile = Profile(
            id=profile_id,
            user_id=user_id,
            name="DB",
            host="localhost",
            port="5432",
            username="user",
            database="db",
            created_at=now
        )

        mock_exec_result = MagicMock()
        mock_exec_result.first.return_value = mock_profile
        mock_session.exec.return_value = mock_exec_result

        with patch("services.profile_service.AsyncSession", return_value=mock_session), \
             patch("services.profile_service.credential_cache") as mock_cache:
            mock_cache.store_password = AsyncMock()
            await profile_service.update_profile(user_id, profile_id, ProfileUpdate(name="Renamed"))

            mock_cache.store_password.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_profile_success(self, profile_service: ProfileService, mock_session: AsyncMock) -> None:
        user_id = "test-user"
        profile_id = str(uuid.uuid4())
        mock_profile = Profile(id=profile_id, user_id=user_id, name="X", host="H", port="P", username="U", database="D")

        mock_exec_result = MagicMock()
        mock_exec_result.first.return_value = mock_profile
        mock_session.exec.return_value = mock_exec_result

        with patch("services.profile_service.AsyncSession", return_value=mock_session):
            result = await profile_service.delete_profile(user_id, profile_id)
            assert result is True
            mock_session.delete.assert_called_once_with(mock_profile)
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_profile_not_found(self, profile_service: ProfileService, mock_session: AsyncMock) -> None:
        mock_exec_result = MagicMock()
        mock_exec_result.first.return_value = None
        mock_session.exec.return_value = mock_exec_result

        with patch("services.profile_service.AsyncSession", return_value=mock_session):
            result = await profile_service.delete_profile("user", "id")
            assert result is False

    @pytest.mark.asyncio
    async def test_get_decrypted_password_deprecated(self, profile_service: ProfileService) -> None:
        result = await profile_service.get_decrypted_password("user", "id")
        assert result is None
