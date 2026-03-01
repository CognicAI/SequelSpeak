/**
 * ApiClient — centralised HTTP client for all backend API calls.
 *
 * Features:
 * - Reads base URL from `VITE_API_URL` env var (defaults to localhost:8000)
 * - Attaches `Content-Type: application/json` to every request
 * - Maps server errors and network failures to typed `ApiError` instances
 * - Exposes named methods per endpoint to keep components free of fetch logic
 */

import type { TestConnectionSuccessResponse } from '../../types/api';
import { ApiError } from './errors';

class ApiClient {
    private readonly baseURL: string;
    private readonly defaultHeaders: HeadersInit;

    constructor() {
        this.baseURL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
        this.defaultHeaders = {
            'Content-Type': 'application/json',
        };
    }

    /**
     * Generic request helper — wraps `fetch` and converts errors to `ApiError`.
     */
    private async request<T>(
        endpoint: string,
        options: RequestInit = {},
    ): Promise<T> {
        const url = `${this.baseURL}${endpoint}`;
        const config: RequestInit = {
            ...options,
            headers: {
                ...this.defaultHeaders,
                ...options.headers,
            },
        };

        try {
            const response = await fetch(url, config);

            if (!response.ok) {
                // Attempt to parse a structured error body; fall back gracefully
                // if the body is non-JSON (e.g. HTML from a proxy, empty 5xx).
                let detail: string | undefined;
                let errorCode: string | undefined;
                try {
                    const errorData = await response.json() as { detail?: string; error_code?: string };
                    detail = errorData.detail;
                    errorCode = errorData.error_code;
                } catch {
                    // Non-JSON body — use the HTTP status text as the message
                }
                throw new ApiError(
                    detail ?? response.statusText ?? 'Request failed',
                    errorCode,
                    response.status,
                );
            }

            // 204 No Content (and similar) have no body to parse
            const data: T = response.status === 204
                ? (undefined as T)
                : (await response.json() as T);

            return data;
        } catch (error) {
            if (error instanceof ApiError) throw error;
            if (error instanceof DOMException && error.name === 'AbortError') {
                throw new ApiError('Request cancelled', 'REQUEST_CANCELLED');
            }
            throw new ApiError(
                'Failed to connect to backend server. Please check your network connection.',
                'NETWORK_ERROR',
            );
        }
    }

    /**
     * Tests a PostgreSQL connection URL against the backend.
     *
     * @param connectionUrl - Full postgres:// connection string (including password)
     * @param token         - Clerk JWT for authenticated requests
     * @param signal        - Optional AbortSignal for cancellation
     */
    async testConnection(
        connectionUrl: string,
        token: string,
        signal?: AbortSignal,
    ): Promise<TestConnectionSuccessResponse> {
        return this.request<TestConnectionSuccessResponse>(
            '/api/v1/utils/test-connection',
            {
                method: 'POST',
                headers: {
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify({ connection_url: connectionUrl }),
                signal,
            },
        );
    }
}

/** Singleton API client — import this in components */
export const apiClient = new ApiClient();
