"""
Router Service

Handles Router persona initialization and conversation state creation.
This service contains the business logic for setting up new conversations
at the Router entry point.

Key Responsibilities:
- Create and persist initial ConversationState
- Initialize conversation with proper stage and status
- Handle persistence failures gracefully
- Provide error recovery and logging

SRS Reference: Section 4.1-4.6 (Router persona)
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from schemas.conversation import ExecutionStage, ConversationStatus
from services.conversation_state import (
    ConversationState,
    ConversationStateManager,
)


logger = logging.getLogger(__name__)


class RouterService:
    """
    Router service for conversation initialization.
    
    Provides business logic for creating and persisting initial conversation state
    at the Router entry point. Ensures state is properly initialized before any
    routing decisions are made.
    """
    
    def __init__(self, state_manager: ConversationStateManager):
        """
        Initialize Router service.
        
        Args:
            state_manager: ConversationStateManager instance for persistence
        """
        self.state_manager = state_manager
    
    async def initialize_conversation(
        self,
        query: str,
        conversation_id: Optional[str] = None,
        user_context: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> ConversationState:
        """
        Initialize a new conversation with Router entry state.
        
        This method creates the initial ConversationState with:
        - Proper conversation ID (generated or provided)
        - Initial execution stage (PLANNING)
        - Initial status (PROCESSING)
        - Original query text
        - User context and correlation ID in metadata
        
        The state is persisted BEFORE any routing decisions are made.
        This ensures we have a complete audit trail from the very start.
        
        Args:
            query: Natural language query from user
            conversation_id: Optional conversation ID (generated if None)
            user_context: Optional user context metadata
            correlation_id: Optional correlation ID for tracing
        
        Returns:
            ConversationState: Initialized and persisted conversation state
        
        Raises:
            Exception: If state persistence fails after retries
        """
        # Generate or validate conversation ID
        conv_id = conversation_id or self.state_manager.generate_conversation_id()
        
        # Create initial state with Router entry values
        state = ConversationState(
            conversation_id=conv_id,
            original_nl_query=query,
            current_stage=ExecutionStage.PLANNING,
            status=ConversationStatus.PROCESSING,
            awaiting_user_response=False,
            metadata={
                'user_context': user_context or {},
                'correlation_id': correlation_id,
            }
        )
        
        # Persist state with error handling
        try:
            await self._persist_state_with_retry(state)
            logger.info(
                f"Initialized conversation state: id={conv_id}, "
                f"stage={state.current_stage.value}, status={state.status.value}",
                extra={'extra_fields': {'correlation_id': correlation_id}}
            )
            return state
        
        except Exception as e:
            logger.error(
                f"Failed to persist initial conversation state: {e}",
                extra={'extra_fields': {'correlation_id': correlation_id}}
            )
            raise
    
    async def update_conversation_stage(
        self,
        conversation_id: str,
        stage: ExecutionStage,
        status: Optional[ConversationStatus] = None,
        **additional_fields: Any
    ) -> None:
        """
        Update conversation stage and optionally other fields.
        
        Used when Router makes routing decisions and needs to update
        the execution stage or status.
        
        Args:
            conversation_id: Conversation ID to update
            stage: New execution stage
            status: Optional new status
            **additional_fields: Additional fields to update (e.g., execution_plan)
        """
        # Get existing state
        state = await self.state_manager.get_state(conversation_id)
        
        if not state:
            logger.warning(f"Cannot update stage: conversation {conversation_id} not found")
            return
        
        # Update fields
        state.current_stage = stage
        if status:
            state.status = status
        
        # Update additional fields
        for key, value in additional_fields.items():
            if hasattr(state, key):
                setattr(state, key, value)
        
        # Update timestamp
        state.updated_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        
        # Persist
        await self.state_manager.save_state(state)
        
        logger.info(
            f"Updated conversation stage: id={conversation_id}, "
            f"stage={stage.value}, status={status.value if status else 'unchanged'}"
        )
    
    async def _persist_state_with_retry(
        self,
        state: ConversationState,
        max_retries: int = 2
    ) -> None:
        """
        Persist state with retry logic.
        
        Attempts to persist the state multiple times if persistence fails.
        This handles transient Redis connection issues gracefully.
        
        Args:
            state: ConversationState to persist
            max_retries: Maximum number of retry attempts
        
        Raises:
            Exception: If all retry attempts fail
        """
        last_exception = None
        
        for attempt in range(max_retries + 1):
            try:
                await self.state_manager.save_state(state)
                
                if attempt > 0:
                    logger.info(
                        f"State persistence succeeded on retry {attempt} "
                        f"for conversation {state.conversation_id}"
                    )
                
                return  # Success
            
            except Exception as e:
                last_exception = e
                logger.warning(
                    f"State persistence attempt {attempt + 1}/{max_retries + 1} failed "
                    f"for conversation {state.conversation_id}: {e}"
                )
                
                if attempt < max_retries:
                    # Brief delay before retry
                    import asyncio
                    await asyncio.sleep(0.1 * (attempt + 1))
        
        # All retries failed
        raise Exception(
            f"Failed to persist conversation state after {max_retries + 1} attempts: "
            f"{last_exception}"
        )


# Singleton instance - will be initialized with conversation_state_manager in main.py
router_service: Optional[RouterService] = None


def get_router_service() -> RouterService:
    """
    Get the singleton RouterService instance.
    
    Returns:
        RouterService: The initialized router service
    
    Raises:
        RuntimeError: If router service not initialized
    """
    if router_service is None:
        raise RuntimeError(
            "RouterService not initialized. "
            "Call initialize_router_service() during application startup."
        )
    return router_service


def initialize_router_service(state_manager: ConversationStateManager) -> None:
    """
    Initialize the singleton RouterService instance.
    
    Call this during application startup (in lifespan context).
    
    Args:
        state_manager: ConversationStateManager instance
    """
    global router_service
    router_service = RouterService(state_manager)
    logger.info("RouterService initialized")
