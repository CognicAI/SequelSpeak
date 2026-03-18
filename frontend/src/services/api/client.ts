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
import type { ConnectionProfile, ProfileCreateRequest, ProfileUpdateRequest } from '../../types/profile';
import type { QueryStartRequest, QueryStartResponse } from '../../types/query';
import type { QueryStatusResponse, QueryRespondRequest, QueryRespondResponse } from '../../types/conversation';
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
        connectionUrl: string | undefined,
        token: string,
        signal?: AbortSignal,
        profileId?: string,
        password?: string,
    ): Promise<TestConnectionSuccessResponse> {
        return this.request<TestConnectionSuccessResponse>(
            '/api/v1/utils/test-connection',
            {
                method: 'POST',
                headers: {
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify({ 
                    connection_url: connectionUrl, 
                    profile_id: profileId,
                    password: password 
                }),
                signal,
            },
        );
    }

    async getProfiles(token: string): Promise<ConnectionProfile[]> {
        return this.request<ConnectionProfile[]>('/api/v1/profiles', {
            method: 'GET',
            headers: { Authorization: `Bearer ${token}` },
        });
    }

    async createProfile(profileData: ProfileCreateRequest, token: string): Promise<ConnectionProfile> {
        return this.request<ConnectionProfile>('/api/v1/profiles', {
            method: 'POST',
            headers: { Authorization: `Bearer ${token}` },
            body: JSON.stringify(profileData),
        });
    }

    async updateProfile(profileId: string, profileData: ProfileUpdateRequest, token: string): Promise<ConnectionProfile> {
        return this.request<ConnectionProfile>(`/api/v1/profiles/${profileId}`, {
            method: 'PUT',
            headers: { Authorization: `Bearer ${token}` },
            body: JSON.stringify(profileData),
        });
    }

    async deleteProfile(profileId: string, token: string): Promise<void> {
        return this.request<void>(`/api/v1/profiles/${profileId}`, {
            method: 'DELETE',
            headers: { Authorization: `Bearer ${token}` },
        });
    }

    /**
     * Initialises a natural-language query (POST /api/v1/query/start).
     *
     * Returns 200 OK with a conversation_id the caller must persist so it
     * can poll for results or continue a multi-turn conversation.
     *
     * @param payload - QueryStartRequest body
     * @param token   - Clerk JWT for authenticated requests
     * @param signal  - Optional AbortSignal for cancellation
     */
    async startQuery(
        payload: QueryStartRequest,
        token: string,
        signal?: AbortSignal,
    ): Promise<QueryStartResponse> {
        return this.request<QueryStartResponse>('/api/v1/query/start', {
            method: 'POST',
            headers: { Authorization: `Bearer ${token}` },
            body: JSON.stringify(payload),
            signal,
        });
    }

    /**
     * Polls the current state of a conversation.
     * GET /api/v1/query/status/{conversationId}
     */
    async getConversationStatus(
        conversationId: string,
        token: string,
        signal?: AbortSignal,
    ): Promise<QueryStatusResponse> {
        return this.request<QueryStatusResponse>(
            `/api/v1/query/status/${encodeURIComponent(conversationId)}`,
            {
                method: 'GET',
                headers: { Authorization: `Bearer ${token}` },
                signal,
            },
        );
    }

    /**
     * Submits answers to pending clarification questions and resumes execution.
     * POST /api/v1/query/respond
     */
    async respondToConversation(
        payload: QueryRespondRequest,
        token: string,
        signal?: AbortSignal,
    ): Promise<QueryRespondResponse> {
        return this.request<QueryRespondResponse>('/api/v1/query/respond', {
            method: 'POST',
            headers: { Authorization: `Bearer ${token}` },
            body: JSON.stringify(payload),
            signal,
        });
    }
}

/** Singleton API client — import this in components */
export const apiClient = new ApiClient();
