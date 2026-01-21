/**
 * API Response Types for Test Connection
 */

/** Error codes returned by the backend for connection failures */
export type ConnectionErrorCode =
    | 'AUTH_FAILED'
    | 'DATABASE_NOT_FOUND'
    | 'HOST_UNREACHABLE'
    | 'TIMEOUT'
    | 'SSL_ERROR'
    | 'INVALID_URL'
    | 'CONNECTION_ERROR';

/** Successful test connection response */
export interface TestConnectionSuccessResponse {
    status: 'success';
    message: string;
}

/** Error response from test connection endpoint */
export interface TestConnectionErrorResponse {
    detail: string;
    error_code?: ConnectionErrorCode;
}

/** Union type for all possible test connection responses */
export type TestConnectionResponse = TestConnectionSuccessResponse | TestConnectionErrorResponse;

/** Request body for test connection */
export interface TestConnectionRequest {
    connection_url: string;
}

/**
 * Gets the error message from the backend response.
 * The backend already provides sanitized, user-friendly error messages,
 * so we simply return the detail message from the response.
 * 
 * @param detailMessage - Detailed error message from the backend
 * @returns The error message to display to the user
 */
export function getErrorMessage(detailMessage?: string): string {
    return detailMessage || 'An unexpected error occurred. Please try again.';
}
