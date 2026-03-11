"""
Local conftest for endpoint auth tests.

These tests specifically verify authentication behaviour (missing token,
expired token, invalid signature, etc.) so they MUST use a real-auth client
that does NOT override verify_clerk_token.

The global conftest.py client fixture mocks verify_clerk_token so that all
other tests can pass without a live Clerk service. That mock cannot be used
here — it would make every request appear authenticated, defeating the purpose
of these tests.
"""

import pytest
from typing import AsyncGenerator
from httpx import ASGITransport, AsyncClient
from main import app


@pytest.fixture
async def client(reset_conversation_state: None) -> AsyncGenerator[AsyncClient, None]:
    """
    Unauthenticated test client — NO verify_clerk_token override.

    Used exclusively by tests that need real auth enforcement (401 checks).
    Any dependency_overrides set by other fixtures are cleared before each
    test and restored afterwards to avoid cross-test contamination.
    """
    # Snapshot and clear any overrides so real auth runs
    saved_overrides = dict(app.dependency_overrides)
    app.dependency_overrides.clear()

    try:
        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app, raise_app_exceptions=False)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                yield ac
    finally:
        # Restore previous overrides (safe for test isolation)
        app.dependency_overrides.clear()
        app.dependency_overrides.update(saved_overrides)
