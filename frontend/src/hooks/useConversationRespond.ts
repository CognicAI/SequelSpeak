/**
 * useConversationRespond — wraps POST /api/v1/query/respond.
 *
 * Used when the user answers pending clarification questions.
 * Carries the same conversation_id so the backend can resume execution.
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import { useAuth } from '@clerk/clerk-react';
import { apiClient } from '../services/api/client';
import { ApiError } from '../services/api/errors';
import type { QueryRespondRequest, QueryRespondResponse } from '../types/conversation';

export interface UseConversationRespondReturn {
    /** Submit clarification answers. Returns response or null on error. */
    respond: (payload: QueryRespondRequest) => Promise<QueryRespondResponse | null>;
    isResponding: boolean;
    error: string | null;
    reset: () => void;
}

export function useConversationRespond(): UseConversationRespondReturn {
    const { getToken } = useAuth();
    const [isResponding, setIsResponding] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const abortRef = useRef<AbortController | null>(null);

    useEffect(() => {
        return () => { abortRef.current?.abort(); };
    }, []);

    const reset = useCallback(() => { setError(null); }, []);

    const respond = useCallback(
        async (payload: QueryRespondRequest): Promise<QueryRespondResponse | null> => {
            abortRef.current?.abort();
            abortRef.current = new AbortController();

            setIsResponding(true);
            setError(null);

            try {
                const token = await getToken();
                if (!token) throw new Error('Authentication token unavailable.');

                const result = await apiClient.respondToConversation(
                    payload,
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
                    : 'Failed to send clarification answer.';
                setError(msg);
                return null;
            } finally {
                setIsResponding(false);
            }
        },
        [getToken],
    );

    return { respond, isResponding, error, reset };
}
