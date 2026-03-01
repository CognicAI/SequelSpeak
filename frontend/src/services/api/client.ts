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
            const data: unknown = await response.json();

            if (!response.ok) {
                // Server returned an error payload
                const errorData = data as { detail?: string; error_code?: string };
                throw new ApiError(
                    errorData.detail ?? 'Request failed',
                    errorData.error_code,
                    response.status,
                );
            }

            return data as T;
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
