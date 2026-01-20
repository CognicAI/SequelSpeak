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
 * Maps backend error codes to user-friendly messages
 */
export const ERROR_CODE_MESSAGES: Record<ConnectionErrorCode, string> = {
    AUTH_FAILED: 'Authentication failed. Please check your username and password.',
    DATABASE_NOT_FOUND: 'Database not found. Please verify the database name exists.',
    HOST_UNREACHABLE: 'Cannot reach the database server. Check the host address and network connectivity.',
    TIMEOUT: 'Connection timed out. The server may be slow or unreachable.',
    SSL_ERROR: 'SSL/TLS connection error. Check your SSL certificate configuration.',
    INVALID_URL: 'Invalid connection URL format. Please check the URL structure.',
    CONNECTION_ERROR: 'Connection failed. Please verify your connection details.',
};

/**
 * Gets a user-friendly error message for a given error code
 */
export function getErrorMessage(errorCode?: ConnectionErrorCode, fallbackMessage?: string): string {
    if (errorCode && ERROR_CODE_MESSAGES[errorCode]) {
        return ERROR_CODE_MESSAGES[errorCode];
    }
    return fallbackMessage || 'An unexpected error occurred. Please try again.';
}
