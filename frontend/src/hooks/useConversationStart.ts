/**
 * useConversationStart — wraps POST /api/v1/query/start.
 *
 * Thin layer over apiClient.startQuery. Returns a stable `start` callback,
 * loading flag, and error string so the chat page can kick off a conversation
 * without coupling itself to fetch logic.
 *
 * User context: always attaches the verified Clerk userId and sessionId so the
 * backend can enforce multi-tenant isolation and SRS tracking requirements.
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import { useAuth, useSession } from '@clerk/clerk-react';
import { apiClient } from '../services/api/client';
import { ApiError } from '../services/api/errors';
import type { QueryStartResponse } from '../types/query';

export interface UseConversationStartReturn {
    /** Call to start a new conversation. Returns the response or null on error. */
    start: (nlQuery: string, databaseId: string) => Promise<QueryStartResponse | null>;
    isStarting: boolean;
    error: string | null;
    /** Reset error state back to null. */
    reset: () => void;
}

export function useConversationStart(): UseConversationStartReturn {
    const { getToken, userId } = useAuth();
    const { session } = useSession();
    const [isStarting, setIsStarting] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const abortRef = useRef<AbortController | null>(null);

    useEffect(() => {
        return () => { abortRef.current?.abort(); };
    }, []);

    const reset = useCallback(() => {
        setError(null);
    }, []);

    const start = useCallback(
        async (nlQuery: string, databaseId: string): Promise<QueryStartResponse | null> => {
            abortRef.current?.abort();
            abortRef.current = new AbortController();

            setIsStarting(true);
            setError(null);

            try {
                const token = await getToken();
                if (!token) throw new Error('Authentication token unavailable.');

                const result = await apiClient.startQuery(
                    {
                        query: nlQuery.trim(),
                        database_id: databaseId,
                        user_context: {
                            // Clerk userId is the canonical user identifier (maps to JWT "sub").
                            // The backend also asserts this from the JWT, providing a double check.
                            user_id: userId ?? undefined,
                            // Session ID scopes the conversation to the current browser session.
                            session_id: session?.id ?? undefined,
                        },
                    },
                    token,
                    abortRef.current.signal,
                );
                return result;
            } catch (err) {
                if (err instanceof ApiError && err.code === 'REQUEST_CANCELLED') {
                    return null;
                }
                const msg = err instanceof ApiError
                    ? err.message
                    : 'An unexpected error occurred. Please try again.';
                setError(msg);
                return null;
            } finally {
                setIsStarting(false);
            }
        },
        [getToken, userId, session],
    );

    return { start, isStarting, error, reset };
}
