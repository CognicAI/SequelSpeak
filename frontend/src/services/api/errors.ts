/**
 * ApiError — typed error thrown by ApiClient for all API failures.
 * Distinguishes API errors from generic JS errors via `instanceof`.
 */
export class ApiError extends Error {
    /** Application-level error code (e.g. 'AUTH_FAILED', 'NETWORK_ERROR') */
    readonly code: string | undefined;
    /** HTTP status code, if the error came from a server response */
    readonly status: number | undefined;

    constructor(message: string, code?: string, status?: number) {
        super(message);
        this.name = 'ApiError';
        this.code = code;
        this.status = status;
    }
}
