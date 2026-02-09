"""
Integration tests for conversation ID propagation.
"""

import asyncio
from typing import Awaitable, TypeVar

from fastapi.testclient import TestClient

from main import app
from services.conversation_state import conversation_state_manager

client = TestClient(app)


T = TypeVar("T")


def run_async(coro: Awaitable[T]) -> T:
    return asyncio.run(coro)


def test_conversation_id_persisted_and_reused():
    run_async(conversation_state_manager.clear())

    first_response = client.post(
        "/api/v1/query",
        json={"query": "test query"}
    )

    assert first_response.status_code == 200
    first_data = first_response.json()
    first_id = first_data["conversation_id"]

    state = run_async(conversation_state_manager.get_state(first_id))
    assert state is not None
    assert state.conversation_id == first_id

    second_response = client.post(
        "/api/v1/query",
        json={"query": "follow-up", "conversation_id": first_id}
    )

    assert second_response.status_code == 200
    second_data = second_response.json()
    assert second_data["conversation_id"] == first_id
