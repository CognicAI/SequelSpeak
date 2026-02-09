"""
Unit tests for conversation state management.
"""

import asyncio
import uuid
from typing import TypeVar, Coroutine, Any

from schemas.router import UUID_V4_PATTERN
from services.conversation_state import conversation_state_manager

T = TypeVar('T')


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def test_generates_conversation_id_when_missing():
    run_async(conversation_state_manager.clear())

    conversation_id = run_async(conversation_state_manager.get_or_create(None))

    assert UUID_V4_PATTERN.match(conversation_id)
    state = run_async(conversation_state_manager.get_state(conversation_id))
    assert state is not None
    assert state.conversation_id == conversation_id


def test_reuses_existing_conversation_id():
    run_async(conversation_state_manager.clear())

    existing_id = str(uuid.uuid4())
    first = run_async(conversation_state_manager.get_or_create(existing_id))
    second = run_async(conversation_state_manager.get_or_create(existing_id))

    assert first == existing_id
    assert second == existing_id
    state = run_async(conversation_state_manager.get_state(existing_id))
    assert state is not None
    assert state.conversation_id == existing_id


def test_creates_state_for_provided_id():
    run_async(conversation_state_manager.clear())

    provided_id = str(uuid.uuid4())
    conversation_id = run_async(conversation_state_manager.get_or_create(provided_id))

    assert conversation_id == provided_id
    state = run_async(conversation_state_manager.get_state(provided_id))
    assert state is not None
    assert state.conversation_id == provided_id
