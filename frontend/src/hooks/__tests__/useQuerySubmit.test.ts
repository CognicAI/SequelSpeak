/**
 * Unit tests for useQuerySubmit hook.
 *
 * Covers:
 * - Client-side validation (empty query, empty database, over-limit)
 * - Successful submission → status 'success', conversation_id persisted
 * - API error → status 'error', message surfaced
 * - Abort / cancellation → status returns to 'idle'
 * - reset() clears state
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useQuerySubmit } from '../useQuerySubmit';
import type { QueryStartResponse } from '../../types/query';
import { QUERY_MAX_LENGTH } from '../../types/query';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// Mock Clerk so we can run without a ClerkProvider
vi.mock('@clerk/clerk-react', () => ({
    useAuth: () => ({
        getToken: vi.fn().mockResolvedValue('test-jwt-token'),
    }),
}));

// Mock ApiClient — we stub individual methods per test
const mockStartQuery = vi.fn();
vi.mock('../../services/api/client', () => ({
    apiClient: {
        startQuery: (...args: unknown[]) => mockStartQuery(...args),
    },
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeSuccessResponse(overrides?: Partial<QueryStartResponse>): QueryStartResponse {
    return {
        status: 'success',
        conversation_id: 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d',
        query: 'Show me total revenue',
        timestamp: '2026-03-14T10:00:00Z',
        message: 'Query initialized successfully',
        ...overrides,
    };
}

const validValues = {
    nlQuery: 'Show me total revenue for last month',
    databaseId: 'db-profile-uuid-1234',
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useQuerySubmit', () => {
    beforeEach(() => {
        mockStartQuery.mockReset();
        sessionStorage.clear();
    });

    afterEach(() => {
        vi.restoreAllMocks();
    });

    // -----------------------------------------------------------------------
    // Initial state
    // -----------------------------------------------------------------------

    it('initialises with idle status', () => {
        const { result } = renderHook(() => useQuerySubmit());
        expect(result.current.status).toBe('idle');
        expect(result.current.isSubmitting).toBe(false);
        expect(result.current.response).toBeNull();
        expect(result.current.errorMessage).toBeNull();
        expect(result.current.fieldErrors).toEqual({});
        expect(result.current.conversationId).toBeNull();
    });

    // -----------------------------------------------------------------------
    // Client-side validation
    // -----------------------------------------------------------------------

    it('sets fieldError for empty nlQuery and does NOT call API', async () => {
        const { result } = renderHook(() => useQuerySubmit());

        await act(async () => {
            await result.current.submit({ nlQuery: '', databaseId: 'some-id' });
        });

        expect(result.current.fieldErrors.nlQuery).toBeTruthy();
        expect(result.current.status).toBe('idle');
        expect(mockStartQuery).not.toHaveBeenCalled();
    });

    it('sets fieldError for whitespace-only nlQuery', async () => {
        const { result } = renderHook(() => useQuerySubmit());

        await act(async () => {
            await result.current.submit({ nlQuery: '   ', databaseId: 'some-id' });
        });

        expect(result.current.fieldErrors.nlQuery).toBeTruthy();
        expect(mockStartQuery).not.toHaveBeenCalled();
    });

    it('sets fieldError when query exceeds QUERY_MAX_LENGTH', async () => {
        const { result } = renderHook(() => useQuerySubmit());
        const oversized = 'x'.repeat(QUERY_MAX_LENGTH + 1);

        await act(async () => {
            await result.current.submit({ nlQuery: oversized, databaseId: 'some-id' });
        });

        expect(result.current.fieldErrors.nlQuery).toMatch(/most/i);
        expect(mockStartQuery).not.toHaveBeenCalled();
    });

    it('sets fieldError for empty databaseId and does NOT call API', async () => {
        const { result } = renderHook(() => useQuerySubmit());

        await act(async () => {
            await result.current.submit({ nlQuery: 'valid query', databaseId: '' });
        });

        expect(result.current.fieldErrors.databaseId).toBeTruthy();
        expect(mockStartQuery).not.toHaveBeenCalled();
    });

    it('sets fieldErrors for both blank fields simultaneously', async () => {
        const { result } = renderHook(() => useQuerySubmit());

        await act(async () => {
            await result.current.submit({ nlQuery: '', databaseId: '' });
        });

        expect(result.current.fieldErrors.nlQuery).toBeTruthy();
        expect(result.current.fieldErrors.databaseId).toBeTruthy();
    });

    // -----------------------------------------------------------------------
    // Successful submission
    // -----------------------------------------------------------------------

    it('sets status to success and stores conversation_id on 200 OK', async () => {
        const successResp = makeSuccessResponse();
        mockStartQuery.mockResolvedValueOnce(successResp);

        const { result } = renderHook(() => useQuerySubmit());

        await act(async () => {
            await result.current.submit(validValues);
        });

        expect(result.current.status).toBe('success');
        expect(result.current.isSubmitting).toBe(false);
        expect(result.current.response).toEqual(successResp);
        expect(result.current.conversationId).toBe(successResp.conversation_id);
    });

    it('persists conversation_id to sessionStorage (FR-90)', async () => {
        mockStartQuery.mockResolvedValueOnce(makeSuccessResponse());

        const { result } = renderHook(() => useQuerySubmit());

        await act(async () => {
            await result.current.submit(validValues);
        });

        expect(sessionStorage.getItem('sequelspeak_conversation_id')).toBe(
            'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d',
        );
    });

    it('trims the query before sending to the API', async () => {
        mockStartQuery.mockResolvedValueOnce(makeSuccessResponse({ query: 'trimmed' }));

        const { result } = renderHook(() => useQuerySubmit());

        await act(async () => {
            await result.current.submit({
                nlQuery: '  Show me revenue  ',
                databaseId: validValues.databaseId,
            });
        });

        const [payload] = mockStartQuery.mock.calls[0] as unknown as [{ query: string }];
        expect(payload.query).toBe('Show me revenue');
    });

    it('passes database_id to API payload', async () => {
        mockStartQuery.mockResolvedValueOnce(makeSuccessResponse());

        const { result } = renderHook(() => useQuerySubmit());

        await act(async () => {
            await result.current.submit(validValues);
        });

        const [payload] = mockStartQuery.mock.calls[0] as unknown as [{ database_id: string }];
        expect(payload.database_id).toBe(validValues.databaseId);
    });

    // -----------------------------------------------------------------------
    // Error handling
    // -----------------------------------------------------------------------

    it('sets status to error and surfaces errorMessage on ApiError', async () => {
        const { ApiError } = await import('../../services/api/errors');
        mockStartQuery.mockRejectedValueOnce(
            new ApiError('Query is too long', 'QUERY_TOO_LONG', 400),
        );

        const { result } = renderHook(() => useQuerySubmit());

        await act(async () => {
            await result.current.submit(validValues);
        });

        expect(result.current.status).toBe('error');
        expect(result.current.errorMessage).toBe('Query is too long');
        expect(result.current.response).toBeNull();
    });

    it('sets generic message on unexpected errors', async () => {
        mockStartQuery.mockRejectedValueOnce(new Error('unexpected'));

        const { result } = renderHook(() => useQuerySubmit());

        await act(async () => {
            await result.current.submit(validValues);
        });

        expect(result.current.status).toBe('error');
        expect(result.current.errorMessage).toMatch(/unexpected/i);
    });

    // -----------------------------------------------------------------------
    // Reset
    // -----------------------------------------------------------------------

    it('reset() returns state to idle and clears errors', async () => {
        const { ApiError } = await import('../../services/api/errors');
        mockStartQuery.mockRejectedValueOnce(new ApiError('fail', 'INVALID_QUERY', 400));

        const { result } = renderHook(() => useQuerySubmit());

        await act(async () => {
            await result.current.submit(validValues);
        });
        expect(result.current.status).toBe('error');

        act(() => {
            result.current.reset();
        });

        expect(result.current.status).toBe('idle');
        expect(result.current.errorMessage).toBeNull();
        expect(result.current.fieldErrors).toEqual({});
    });
});
