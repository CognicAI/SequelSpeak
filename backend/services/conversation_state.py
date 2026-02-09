"""
Conversation state management for Router requests.

Provides an in-memory conversation state store with async-safe access.
Designed to be replaced with Redis-backed storage in future iterations.
"""

from __future__ import annotations
import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Optional


@dataclass
class ConversationState:
    """Represents persisted state for a conversation."""

    conversation_id: str
    created_at: float
    last_updated_at: float


class ConversationStateManager:
    """
    Async-safe manager for conversation state.

    Stores minimal metadata for each conversation ID to support
    validation, reuse, and downstream propagation.
    """

    _instance: ConversationStateManager | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._states = {}
            cls._instance._lock = None
        return cls._instance

    _states: dict[str, ConversationState]
    _lock: Optional[asyncio.Lock]

    def _ensure_lock(self) -> asyncio.Lock:
        """Lazily initialize the asyncio.Lock when an event loop is available."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def get_or_create(self, conversation_id: Optional[str]) -> str:
        """
        Get an existing conversation ID or create a new one.

        Args:
            conversation_id: Optional existing conversation ID

        Returns:
            Conversation ID (existing or newly generated)
        """
        if conversation_id:
            await self.upsert_state(conversation_id)
            return conversation_id

        new_id = str(uuid.uuid4())
        await self.upsert_state(new_id)
        return new_id

    async def upsert_state(self, conversation_id: str) -> ConversationState:
        """
        Create or update conversation state.

        Args:
            conversation_id: Conversation ID to store

        Returns:
            ConversationState instance
        """
        current_time = time.time()
        async with self._ensure_lock():
            existing = self._states.get(conversation_id)
            if existing:
                existing.last_updated_at = current_time
                return existing

            state = ConversationState(
                conversation_id=conversation_id,
                created_at=current_time,
                last_updated_at=current_time,
            )
            self._states[conversation_id] = state
            return state

    async def get_state(self, conversation_id: str) -> Optional[ConversationState]:
        """
        Retrieve conversation state by ID.

        Args:
            conversation_id: Conversation ID to lookup

        Returns:
            ConversationState if found, else None
        """
        async with self._ensure_lock():
            return self._states.get(conversation_id)

    async def clear(self) -> None:
        """Clear all stored conversation states (for tests)."""
        async with self._ensure_lock():
            self._states.clear()


conversation_state_manager = ConversationStateManager()
