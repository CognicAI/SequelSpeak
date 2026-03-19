"""
OrchestratorService — Persona Pipeline Execution

Drives the full conversation execution pipeline as a background task:
  Router → SchemaExpert → SQLWriter → SQLGuardian → Executor → Explainer

Design:
- Each "persona" is a phase function that updates ConversationState and can:
    a) Advance to the next stage (CONTINUE)
    b) Request clarification (PAUSE → status = CLARIFICATION_NEEDED)
    c) Return a terminal result (COMPLETE / ERROR)
- The orchestrator loops through the plan, saves state after each phase,
  and stops when it hits a terminal or pause condition.
- Stage delays are included so the polling frontend perceives real progress.
- SQLWriter → SQLGuardian → SQLWriter retry loop (max 2 retries) for validation
  failures, matching SRS Section 5 requirements.

SRS References:
  - Section 4: Router persona
  - Section 5: Execution pipeline (incl. SQLWriter retry on validation failure)
  - Section 6.1: ConversationState
  - FR-82: 30-minute idle timeout
  - FR-130: Credential loss during execution
"""

import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from typing import Optional, Any
from schemas.conversation import ExecutionStage, ConversationStatus  # type: ignore
from services.conversation_state import ConversationStateManager, ConversationState  # type: ignore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tuning constants
# ---------------------------------------------------------------------------

# Simulated persona processing delays (seconds). These give the frontend time
# to poll and display stage transitions. Replace with actual LLM/DB latency
# once real implementations are wired in.
STAGE_DELAY: dict[ExecutionStage, float] = {
    ExecutionStage.PLANNING:         1.0,
    ExecutionStage.SCHEMA_RETRIEVAL: 1.5,
    ExecutionStage.CONTEXT_RETRIEVAL: 1.0,
    ExecutionStage.SQL_GENERATION:   2.0,
    ExecutionStage.VALIDATION:       1.0,
    ExecutionStage.EXECUTION:        1.5,
    ExecutionStage.EXPLANATION:      2.0,
    ExecutionStage.ANALYTICS:        1.0,
}

# Max times SQLWriter → SQLGuardian cycle is retried on validation failure
SQL_VALIDATION_MAX_RETRIES = 2

# Dangerous SQL keywords that the stub SQLGuardian rejects
DANGEROUS_KEYWORDS = re.compile(
    r'\b(DROP|DELETE|TRUNCATE|ALTER|UPDATE|INSERT|CREATE|GRANT|REVOKE|EXEC|EXECUTE)\b',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Stage result sentinel
# ---------------------------------------------------------------------------

class StageResult:
    """Returned by each persona phase function."""

    CONTINUE = "continue"       # Move to next stage
    PAUSE    = "pause"          # Clarification needed — stop, wait for user
    COMPLETE = "complete"       # Terminal: success
    ERROR    = "error"          # Terminal: failure
    RETRY    = "retry"          # Validation failed — retry SQL generation

    def __init__(
        self,
        outcome: str,
        *,
        message: str = "",
        generated_sql: Optional[str] = None,
        execution_result: Optional[dict[str, Any]] = None,
        explanation: Optional[str] = None,
        visualization_config: Optional[dict[str, Any]] = None,
        duration_ms: Optional[int] = None,
        clarification_questions: Optional[list[str]] = None,
        validation_errors: Optional[list[str]] = None,
    ):
        self.outcome = outcome
        self.message = message
        self.generated_sql = generated_sql
        self.execution_result = execution_result
        self.explanation = explanation
        self.visualization_config = visualization_config
        self.duration_ms = duration_ms
        self.clarification_questions = clarification_questions or []
        self.validation_errors = validation_errors or []


# ---------------------------------------------------------------------------
# OrchestratorService
# ---------------------------------------------------------------------------

class OrchestratorService:
    """
    Executes the persona pipeline for a conversation as a FastAPI background task.

    Usage:
        background_tasks.add_task(orchestrator_service.execute_conversation, conversation_id)
    """

    def __init__(self, state_manager: ConversationStateManager) -> None:
        self.state_manager = state_manager

    # ------------------------------------------------------------------
    # Entry point (called by background tasks)
    # ------------------------------------------------------------------

    async def execute_conversation(self, conversation_id: str) -> None:
        """
        Run the full persona pipeline for the given conversation.

        Designed to be called as a FastAPI BackgroundTask — all exceptions
        are caught internally so the background task never crashes the server.
        """
        logger.info(f"Orchestrator starting: conversation_id={conversation_id}")
        try:
            await self._run_pipeline(conversation_id)
        except Exception as exc:
            logger.exception(
                f"Unhandled error in orchestrator: conversation_id={conversation_id}, error={exc}"
            )
            await self._mark_error(conversation_id, f"Orchestration failed: {exc}")

    # ------------------------------------------------------------------
    # Pipeline loop
    # ------------------------------------------------------------------

    async def _require_state(self, conversation_id: str) -> ConversationState:
        state = await self.state_manager.get_state(conversation_id)
        if state is None:
            raise RuntimeError(f"State inexplicably lost for conversation {conversation_id}")
        return state

    async def _run_pipeline(self, conversation_id: str) -> None:
        raw_state = await self.state_manager.get_state(conversation_id)
        if raw_state is None:
            logger.warning(f"Orchestrator: conversation {conversation_id} not found at pipeline start")
            return
        
        state: ConversationState = raw_state
        assert state is not None

        user_id = state.metadata.get("user_context", {}).get("user_id", "unknown")
        current_query = state.current_nl_query or "unknown"
        logger.info(
            f"Orchestrator pipeline: conversation_id={conversation_id}, user_id={user_id}, "
            f"query='{current_query[:80]}'"
        )

        # --- Phase 1: Planning ---
        if await self._is_terminal_or_paused(conversation_id):
            return
        state = await self._require_state(conversation_id)
        await self._set_stage(state, ExecutionStage.PLANNING)
        result = await self.phase_planning(state)
        await self._record_persona_result(state, "Router", ExecutionStage.PLANNING, result)
        if result.outcome == StageResult.PAUSE:
            await self._set_clarification(state, result.clarification_questions)
            return
        if result.outcome in (StageResult.ERROR, StageResult.COMPLETE):
            await self._handle_terminal(state, result)
            return

        # --- Phase 2: Schema Retrieval ---
        if await self._is_terminal_or_paused(conversation_id):
            return
        state = await self._require_state(conversation_id)
        await self._set_stage(state, ExecutionStage.SCHEMA_RETRIEVAL)
        result = await self.phase_schema_retrieval(state)
        await self._record_persona_result(state, "SchemaExpert", ExecutionStage.SCHEMA_RETRIEVAL, result)
        if result.outcome in (StageResult.ERROR, StageResult.COMPLETE):
            await self._handle_terminal(state, result)
            return

        # --- Phase 3: Context Retrieval ---
        if await self._is_terminal_or_paused(conversation_id):
            return
        state = await self._require_state(conversation_id)
        await self._set_stage(state, ExecutionStage.CONTEXT_RETRIEVAL)
        result = await self.phase_context_retrieval(state)
        await self._record_persona_result(state, "ContextRetriever", ExecutionStage.CONTEXT_RETRIEVAL, result)
        if result.outcome in (StageResult.ERROR, StageResult.COMPLETE):
            await self._handle_terminal(state, result)
            return

        # --- Phase 4+5: SQLWriter → SQLGuardian with retry loop ---
        sql_attempt = 0
        current_sql: Optional[str] = None
        while sql_attempt <= SQL_VALIDATION_MAX_RETRIES:
            if await self._is_terminal_or_paused(conversation_id):
                return

            state = await self._require_state(conversation_id)
            await self._set_stage(state, ExecutionStage.SQL_GENERATION)

            gen_result = await self.phase_sql_generation(state, attempt=sql_attempt)
            await self._record_persona_result(state, "SQLWriter", ExecutionStage.SQL_GENERATION, gen_result)
            if gen_result.outcome == StageResult.ERROR:
                await self._mark_error(conversation_id, gen_result.message)
                return
            current_sql = gen_result.generated_sql

            # Persist generated SQL immediately so polling can show it
            state = await self._require_state(conversation_id)
            if state and current_sql:
                state.generated_sql = current_sql
                state.updated_at = self._now()
                await self.state_manager.save_state(state)

            # Validation
            if await self._is_terminal_or_paused(conversation_id):
                return
            state = await self._require_state(conversation_id)
            await self._set_stage(state, ExecutionStage.VALIDATION)

            val_result = await self.phase_validation(state, sql=current_sql)
            await self._record_persona_result(state, "SQLGuardian", ExecutionStage.VALIDATION, val_result)
            if val_result.outcome == StageResult.CONTINUE:
                break  # Validation passed — exit retry loop
            if val_result.outcome == StageResult.ERROR:
                await self._mark_error(conversation_id, val_result.message)
                return
            if val_result.outcome == StageResult.RETRY:
                sql_attempt += 1
                if sql_attempt > SQL_VALIDATION_MAX_RETRIES:
                    logger.error(
                        f"[SQLGuardian] Max validation retries exceeded "
                        f"(conversation_id={conversation_id})"
                    )
                    await self._mark_error(
                        conversation_id,
                        f"SQL validation failed after {SQL_VALIDATION_MAX_RETRIES + 1} attempts: "
                        f"{', '.join(val_result.validation_errors)}",
                    )
                    return
                logger.warning(
                    f"[SQLGuardian] Validation failed (attempt {sql_attempt}/"
                    f"{SQL_VALIDATION_MAX_RETRIES + 1}) — retrying SQLWriter: "
                    f"errors={val_result.validation_errors} "
                    f"(conversation_id={conversation_id})"
                )
                continue

        # --- Phase 6: Execution ---
        if await self._is_terminal_or_paused(conversation_id):
            return
        state = await self._require_state(conversation_id)
        await self._set_stage(state, ExecutionStage.EXECUTION)
        result = await self.phase_execution(state, sql=current_sql)
        await self._record_persona_result(state, "Executor", ExecutionStage.EXECUTION, result)
        if result.outcome in (StageResult.ERROR, StageResult.COMPLETE):
            await self._handle_terminal(state, result)
            return

        # Persist execution result
        state = await self._require_state(conversation_id)
        if state and result.execution_result is not None:
            state.execution_result = result.execution_result
            state.updated_at = self._now()
            await self.state_manager.save_state(state)

        # --- Phase 7: Explanation ---
        if await self._is_terminal_or_paused(conversation_id):
            return
        state = await self._require_state(conversation_id)
        await self._set_stage(state, ExecutionStage.EXPLANATION)
        result = await self.phase_explanation(state, execution_result=result.execution_result)
        await self._record_persona_result(state, "Explainer", ExecutionStage.EXPLANATION, result)

        if result.outcome in (StageResult.ERROR, StageResult.COMPLETE):
            await self._handle_terminal(state, result)
            return

        # --- Phase 8: Analytics ---
        if await self._is_terminal_or_paused(conversation_id):
            return
        state = await self._require_state(conversation_id)
        await self._set_stage(state, ExecutionStage.ANALYTICS)
        analytics_result = await self.phase_analytics(state, execution_result=result.execution_result)
        await self._record_persona_result(state, "Analytics", ExecutionStage.ANALYTICS, analytics_result)
        if analytics_result.outcome in (StageResult.ERROR, StageResult.COMPLETE):
            await self._handle_terminal(state, analytics_result)
            return

        if analytics_result.visualization_config is not None:
            state = await self._require_state(conversation_id)
            state.visualization_config = analytics_result.visualization_config
            state.updated_at = self._now()
            await self.state_manager.save_state(state)

        # Always terminal from here
        state = await self._require_state(conversation_id)
        await self._mark_complete(state, result)

    # ------------------------------------------------------------------
    # Guard helper
    # ------------------------------------------------------------------

    async def _is_terminal_or_paused(self, conversation_id: str) -> bool:
        """Return True if the pipeline should stop (externally set status)."""
        state = await self.state_manager.get_state(conversation_id)
        if state is None:
            logger.warning(f"Orchestrator: conversation {conversation_id} vanished — stopping")
            return True
        
        assert state is not None
        if state.status in (
            ConversationStatus.COMPLETE,
            ConversationStatus.ERROR,
            ConversationStatus.CANCELLED,
            ConversationStatus.TIMEOUT,
            ConversationStatus.CLARIFICATION_NEEDED,
        ):
            logger.info(
                f"Orchestrator stopping early: id={conversation_id}, "
                f"status={state.status.value}"
            )
            return True
        return False

    # ------------------------------------------------------------------
    # Persona phases
    # ------------------------------------------------------------------

    async def phase_planning(self, state: ConversationState) -> StageResult:
        """
        Router persona: validate query, determine execution plan.

        Real implementation: call LLM with Router system prompt, decide
        whether clarification is needed before proceeding.
        """
        t0 = time.perf_counter()
        await asyncio.sleep(STAGE_DELAY[ExecutionStage.PLANNING])
        elapsed = time.perf_counter() - t0

        query = state.current_nl_query or ""
        user_id = state.metadata.get("user_context", {}).get("user_id", "unknown")

        logger.info(
            f"[Router] Planning: query='{query[:120]}', user_id={user_id}, "
            f"elapsed={elapsed:.2f}s (conversation_id={state.conversation_id})"
        )
        return StageResult(StageResult.CONTINUE, duration_ms=round(elapsed * 1000))

    async def phase_schema_retrieval(self, state: ConversationState) -> StageResult:
        """
        SchemaExpert persona: retrieve relevant schema from the database.

        Real implementation: connect using state.metadata['database_id'],
        run information_schema queries, store schema summary in metadata.
        """
        t0 = time.perf_counter()
        await asyncio.sleep(STAGE_DELAY[ExecutionStage.SCHEMA_RETRIEVAL])
        elapsed = time.perf_counter() - t0

        database_id = state.metadata.get("database_id", "not_set")
        logger.info(
            f"[SchemaExpert] Schema retrieved: database_id={database_id}, "
            f"elapsed={elapsed:.2f}s (conversation_id={state.conversation_id})"
        )
        # Stub: real impl stores schema context in metadata["schema_context"]
        return StageResult(StageResult.CONTINUE, duration_ms=round(elapsed * 1000))

    async def phase_context_retrieval(self, state: ConversationState) -> StageResult:
        """
        ContextRetriever persona: fetch similar historical queries/examples.

        Real implementation: semantic retrieval from pgvector/query history.
        """
        t0 = time.perf_counter()
        await asyncio.sleep(STAGE_DELAY[ExecutionStage.CONTEXT_RETRIEVAL])
        elapsed = time.perf_counter() - t0

        logger.info(
            f"[ContextRetriever] Context gathered: elapsed={elapsed:.2f}s "
            f"(conversation_id={state.conversation_id})"
        )
        return StageResult(StageResult.CONTINUE, duration_ms=round(elapsed * 1000))

    async def phase_sql_generation(
        self,
        state: ConversationState,
        attempt: int = 0,
    ) -> StageResult:
        """
        SQLWriter persona: generate SQL from NL query + schema context.

        Real implementation: call LLM with NL query and schema context.
        On retry (attempt > 0) the previous validation errors are passed
        in clarification_history so the LLM can self-correct.
        """
        t0 = time.perf_counter()
        await asyncio.sleep(STAGE_DELAY[ExecutionStage.SQL_GENERATION])
        elapsed = time.perf_counter() - t0

        query = state.current_nl_query
        # Stub SQL — the comment includes the attempt number so retries are visible
        stub_sql = (
            f"SELECT *\nFROM stub_table\nWHERE -- stub: {query}"
            + (f"\n-- retry attempt {attempt}" if attempt > 0 else "")
        )

        logger.info(
            "[SQLWriter] Generated SQL (attempt %d): sql='%s...', elapsed=%.2fs (conversation_id=%s)",
            attempt + 1,
            stub_sql[:120],  # type: ignore[no-matching-overload]
            elapsed,
            state.conversation_id
        )
        return StageResult(
            StageResult.CONTINUE,
            generated_sql=stub_sql,
            duration_ms=round(elapsed * 1000),
        )

    async def phase_validation(
        self,
        state: ConversationState,
        sql: Optional[str] = None,
    ) -> StageResult:
        """
        SQLGuardian persona: validate generated SQL for safety and syntax.

        Real implementation: parse SQL AST, run allow-list checks.
        Stub: rejects any SQL containing dangerous DDL/DML keywords.
        Returns RETRY when validation fails (triggers SQLWriter retry loop).
        """
        t0 = time.perf_counter()
        await asyncio.sleep(STAGE_DELAY[ExecutionStage.VALIDATION])
        elapsed = time.perf_counter() - t0

        target_sql = sql or state.generated_sql or ""
        errors: list[str] = []

        # Safety check: reject dangerous mutations
        if DANGEROUS_KEYWORDS.search(target_sql):
            found = DANGEROUS_KEYWORDS.findall(target_sql)
            errors.append(f"Dangerous SQL keywords detected: {', '.join(set(found))}")

        is_valid = len(errors) == 0
        logger.info(
            f"[SQLGuardian] Validation: valid={is_valid}, errors={errors}, "
            f"elapsed={elapsed:.2f}s (conversation_id={state.conversation_id})"
        )

        if not is_valid:
            return StageResult(
                StageResult.RETRY,
                validation_errors=errors,
                duration_ms=round(elapsed * 1000),
            )
        return StageResult(StageResult.CONTINUE, duration_ms=round(elapsed * 1000))

    async def phase_execution(
        self,
        state: ConversationState,
        sql: Optional[str] = None,
    ) -> StageResult:
        """
        Executor persona: run the validated SQL against the target database.

        Real implementation: retrieve connection URL from credential cache
        using state.metadata['database_id'], execute via psycopg, return rows.
        """
        t0 = time.perf_counter()
        await asyncio.sleep(STAGE_DELAY[ExecutionStage.EXECUTION])
        elapsed = time.perf_counter() - t0

        target_sql = sql or state.generated_sql or "(no SQL)"
        stub_result: dict[str, Any] = {"rows": [], "row_count": 0, "columns": [], "execution_time_ms": round(elapsed * 1000)}

        logger.info(
            "[Executor] Executed: sql='%s...', rows=%d, time=%.2fs (conversation_id=%s)",
            target_sql[:80],  # type: ignore[no-matching-overload]
            stub_result['row_count'],
            elapsed,
            state.conversation_id
        )
        return StageResult(
            StageResult.CONTINUE,
            execution_result=stub_result,
            duration_ms=round(elapsed * 1000),
        )

    async def phase_explanation(
        self,
        state: ConversationState,
        execution_result: Optional[dict[str, Any]] = None,
    ) -> StageResult:
        """
        Explainer persona: generate plain-English explanation of the results.

        Real implementation: call LLM with SQL + rows to produce concise narrative.
        """
        t0 = time.perf_counter()
        await asyncio.sleep(STAGE_DELAY[ExecutionStage.EXPLANATION])
        elapsed = time.perf_counter() - t0

        row_count = (execution_result or {}).get("row_count", 0)
        stub_explanation = (
            f"Your query returned {row_count} rows. "
            "Results are shown above — replace this stub with a real LLM explanation."
        )

        logger.info(
            f"[Explainer] Explanation: rows={row_count}, elapsed={elapsed:.2f}s "
            f"(conversation_id={state.conversation_id})"
        )
        return StageResult(
            StageResult.CONTINUE,
            explanation=stub_explanation,
            execution_result=execution_result,
            duration_ms=round(elapsed * 1000),
        )

    async def phase_analytics(
        self,
        state: ConversationState,
        execution_result: Optional[dict[str, Any]] = None,
    ) -> StageResult:
        """
        Analytics persona: decide whether and how to visualize results.
        """
        t0 = time.perf_counter()
        await asyncio.sleep(STAGE_DELAY[ExecutionStage.ANALYTICS])
        elapsed = time.perf_counter() - t0

        row_count = int((execution_result or {}).get("row_count", 0))
        visualization_required = row_count > 0
        viz_config: dict[str, Any] = {
            "visualization_required": visualization_required,
            "chart_type": "table" if visualization_required else None,
            "time_bucket": None,
        }

        logger.info(
            f"[Analytics] Visualization decision: required={visualization_required}, "
            f"elapsed={elapsed:.2f}s (conversation_id={state.conversation_id})"
        )
        return StageResult(
            StageResult.CONTINUE,
            execution_result=execution_result,
            visualization_config=viz_config,
            duration_ms=round(elapsed * 1000),
        )

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    async def _set_stage(self, state: ConversationState, stage: ExecutionStage) -> None:
        """Persist stage transition to state store and emit a log line."""
        state.current_stage = stage
        state.status = ConversationStatus.PROCESSING
        state.updated_at = self._now()
        await self.state_manager.save_state(state)
        logger.info(
            f"Stage → {stage.value} (conversation_id={state.conversation_id})"
        )

    async def _record_persona_result(
        self,
        state: ConversationState,
        persona_name: str,
        stage: ExecutionStage,
        result: StageResult,
    ) -> None:
        """Append persona trace entry and maintain completed persona list."""
        trace_entry: dict[str, Any] = {
            "persona_name": persona_name,
            "stage": stage.value,
            "input_data": {},
            "output_data": {
                "outcome": result.outcome,
                "message": result.message,
            },
            "timestamp": self._now(),
            "duration_ms": result.duration_ms,
        }
        state.persona_trace.append(trace_entry)

        if result.outcome in (StageResult.CONTINUE, StageResult.COMPLETE):
            if persona_name not in state.completed_stages:
                state.completed_stages.append(persona_name)

        state.updated_at = self._now()
        await self.state_manager.save_state(state)

    async def _set_clarification(
        self,
        state: ConversationState,
        questions: list[str],
    ) -> None:
        """Pause execution and request clarification from the user."""
        state.status = ConversationStatus.CLARIFICATION_NEEDED
        state.awaiting_user_response = True
        state.pending_clarification_questions = questions
        # Record which stage we paused at for potential resume
        state.metadata['_paused_at_stage'] = state.current_stage.value
        state.updated_at = self._now()
        await self.state_manager.save_state(state)
        logger.info(
            f"[Orchestrator] Paused for clarification: "
            f"questions={questions}, paused_at={state.current_stage.value} "
            f"(conversation_id={state.conversation_id})"
        )

    async def _handle_terminal(
        self,
        state: ConversationState,
        result: StageResult,
    ) -> None:
        if result.outcome == StageResult.COMPLETE:
            await self._mark_complete(state, result)
        elif result.outcome == StageResult.ERROR:
            await self._mark_error(state.conversation_id, result.message)

    async def _mark_complete(
        self,
        state: ConversationState,
        result: StageResult,
    ) -> None:
        """Transition conversation to complete with final results."""
        state.status = ConversationStatus.COMPLETE
        state.current_stage = ExecutionStage.COMPLETE
        state.awaiting_user_response = False
        if result.generated_sql:
            state.generated_sql = result.generated_sql
        if result.execution_result is not None:
            state.execution_result = result.execution_result
        if result.explanation:
            state.explanation = result.explanation
        if result.visualization_config is not None:
            state.visualization_config = result.visualization_config
        # Mark current turn as complete
        now = self._now()
        state.metadata['_turn_completed_at'] = now
        state.updated_at = now
        await self.state_manager.save_state(state)
        user_id = state.metadata.get("user_context", {}).get("user_id", "unknown")
        logger.info(
            f"Orchestrator: COMPLETE — conversation_id={state.conversation_id}, "
            f"user_id={user_id}, turn={state.turn_number}, "
            f"sql='{(state.generated_sql or '')[:80]}', "
            f"explanation='{(state.explanation or '')[:80]}'"
        )

    async def _mark_error(self, conversation_id: str, message: str) -> None:
        """Transition conversation to error state."""
        state = await self._require_state(conversation_id)
        if not state:
            return
        state.status = ConversationStatus.ERROR
        state.current_stage = ExecutionStage.ERROR
        now = self._now()
        state.updated_at = now
        state.errors.append({"message": message, "timestamp": now})
        # Mark current turn as error
        state.metadata['_turn_error'] = True
        await self.state_manager.save_state(state)
        logger.error(
            f"Orchestrator: ERROR — conversation_id={conversation_id}, "
            f"turn={state.turn_number}: {message}"
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Singleton helpers (matches the pattern used by router_service.py)
# ---------------------------------------------------------------------------

_orchestrator_service: Optional[OrchestratorService] = None


def get_orchestrator_service() -> OrchestratorService:
    """
    Return the singleton OrchestratorService instance.

    Raises:
        RuntimeError: If not yet initialized via initialize_orchestrator_service()
    """
    if _orchestrator_service is None:
        raise RuntimeError(
            "OrchestratorService not initialized. "
            "Call initialize_orchestrator_service() during application startup."
        )
    return _orchestrator_service


def initialize_orchestrator_service(state_manager: ConversationStateManager) -> None:
    """
    Create and register the singleton OrchestratorService.

    Call this inside the FastAPI lifespan context after the state manager
    has been initialized.
    """
    global _orchestrator_service
    _orchestrator_service = OrchestratorService(state_manager)
    logger.info("OrchestratorService initialized")
