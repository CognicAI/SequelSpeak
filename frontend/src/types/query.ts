/**
 * Query API Types — Section 7.6.3
 *
 * TypeScript interfaces matching the backend RouterRequest / RouterInitResponse
 * schemas defined in backend/schemas/router.py.
 */

// ---------------------------------------------------------------------------
// Request
// ---------------------------------------------------------------------------

/** Optional user/session metadata sent alongside a query. */
export interface QueryUserContext {
    user_id?: string | null;
    session_id?: string | null;
    /** Client IP — populated server-side from the request; callers may omit. */
    ip_address?: string | null;
}

/**
 * Request body for POST /api/v1/query/start (Section 7.8.1).
 *
 * Rules enforced server-side (and mirrored client-side in useQuerySubmit):
 * - `nl_query` 1–10 000 characters, no leading/trailing whitespace
 * - `database_id` must be a non-empty string (profile UUID)
 * - `conversation_id` optional UUID v4
 */
export interface QueryStartRequest {
    /** Natural-language question from the user. */
    query: string;
    /** UUID of the saved connection profile to query against. */
    database_id: string;
    /** Optional UUID v4 to continue an existing conversation. */
    conversation_id?: string;
    /** Optional user/session metadata. */
    user_context?: QueryUserContext;
    /** Reserved for future per-request options (e.g. row limit override). */
    options?: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Response
// ---------------------------------------------------------------------------

/**
 * Body returned by a 200 OK response from POST /api/v1/query/start.
 * Mirrors RouterInitResponse in backend/schemas/router.py.
 */
export interface QueryStartResponse {
    status: 'success';
    /** UUID v4 — store this to poll or resume the conversation. */
    conversation_id: string;
    /** Normalised, whitespace-stripped version of the submitted query. */
    query: string;
    /** ISO 8601 timestamp of request initialisation. */
    timestamp: string;
    /** Request correlation ID for distributed tracing. */
    correlation_id?: string | null;
    /** Human-readable confirmation message. */
    message: string;
}

// ---------------------------------------------------------------------------
// Error
// ---------------------------------------------------------------------------

export type QueryErrorCode =
    | 'INVALID_QUERY'
    | 'QUERY_TOO_LONG'
    | 'QUERY_EMPTY'
    | 'INVALID_CONVERSATION_ID'
    | 'INVALID_REQUEST'
    | 'NETWORK_ERROR'
    | 'REQUEST_CANCELLED';

/** Error body returned on 400 / 422 from the query endpoint. */
export interface QueryErrorResponse {
    detail: string;
    error_code?: QueryErrorCode;
}

// ---------------------------------------------------------------------------
// Validation constants (mirror backend/schemas/router.py)
// ---------------------------------------------------------------------------

export const QUERY_MAX_LENGTH = 10000;
export const QUERY_MIN_LENGTH = 1;
