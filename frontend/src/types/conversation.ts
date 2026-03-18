/**
 * Conversation Types — Chat UI
 *
 * Defines the client-side data model for the chat interface.
 * Aligns with the backend ConversationState / ConversationStatus schemas
 * (backend/schemas/conversation.py) and the new query API response shapes.
 */

// ---------------------------------------------------------------------------
// Message model
// ---------------------------------------------------------------------------

/** Who sent the message. */
export type MessageRole = 'user' | 'assistant' | 'system';

/**
 * What kind of content the bubble carries.
 * - text        — plain prose (user input, assistant narrative, system notice)
 * - clarification — assistant is asking the user a question, needs a reply
 * - result      — final query result (SQL + rows, serialised as JSON string in content)
 * - error       — something went wrong (credential expiry, timeout, API error)
 */
export type MessageKind = 'text' | 'clarification' | 'result' | 'error';

export interface ConversationMessage {
  /** Locally generated UUID so React has a stable key. */
  id: string;
  role: MessageRole;
  kind: MessageKind;
  /**
   * Always a human-readable string.
   * For `kind === 'result'` the generated SQL and row data are in `metadata`.
   */
  content: string;
  createdAt: string; // ISO 8601
  metadata?: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Conversation view-model
// ---------------------------------------------------------------------------

/** Mirrors backend ConversationStatus enum. */
export type ConversationStatus =
  | 'idle'
  | 'processing'
  | 'clarification_needed'
  | 'complete'
  | 'error';

export interface ConversationViewModel {
  id: string | null;
  status: ConversationStatus;
  /** Current backend execution stage, e.g. "planning", "sql_generation". */
  stage: string | null;
  messages: ConversationMessage[];
  /** Raw question strings awaiting user answers. */
  pendingClarificationQuestions: string[];
  generatedSql: string | null;
  result: unknown;
  explanation: string | null;
  /** Whether the composer is locked pending credential re-auth. */
  needsReauth: boolean;
  /** UUID of the DB profile the user has selected in the composer. */
  selectedDatabaseId: string;
}

// ---------------------------------------------------------------------------
// Backend API shapes
// ---------------------------------------------------------------------------

/**
 * Response from GET /api/v1/query/status/{conversation_id}.
 * Mirrors QueryStatusResponse in backend/schemas/router.py.
 */
export interface QueryStatusResponse {
  conversation_id: string;
  /** Backend ConversationStatus value. */
  status: string;
  current_stage: string;
  awaiting_user_response: boolean;
  pending_clarification_questions: string[];
  generated_sql: string | null;
  execution_result: unknown;
  explanation: string | null;
}

/**
 * Body for POST /api/v1/query/respond.
 */
export interface QueryRespondRequest {
  conversation_id: string;
  /** Free-text answers to pending clarification questions (one per question). */
  answers: string[];
  /** Optional override for multi-turn free-form follow-ups. */
  message?: string;
  /** Optionally pass a different database_id if the user switched profiles. */
  database_id?: string;
}

/** Response from POST /api/v1/query/respond. */
export interface QueryRespondResponse {
  conversation_id: string;
  status: string;
  current_stage: string;
  message: string;
}
