/**
 * useQuerySubmit — orchestrates POST /api/v1/query/start.
 *
 * Responsibilities:
 * - Client-side validation (mirrors server-side rules – fail fast, <100 ms)
 * - Immediate loading flag on submit (satisfies NFR-2 ≤100 ms indicator)
 * - AbortController so in-flight requests are cancelled on unmount
 * - Stores returned conversation_id in session state (FR-90)
 * - Typed error messages surfaced to the caller
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import { useAuth } from '@clerk/clerk-react';
import { apiClient } from '../services/api/client';
import { ApiError } from '../services/api/errors';
import type { QueryStartRequest, QueryStartResponse } from '../types/query';
import { QUERY_MAX_LENGTH, QUERY_MIN_LENGTH } from '../types/query';

// ---------------------------------------------------------------------------
// Session storage key for conversation_id (FR-90)
// ---------------------------------------------------------------------------
const CONVERSATION_ID_KEY = 'sequelspeak_conversation_id';

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export interface QueryFormValues {
    /** Natural-language question entered by the user. */
    nlQuery: string;
    /** UUID of the selected connection profile. */
    databaseId: string;
}

export type QuerySubmitStatus =
    | 'idle'
    | 'submitting'
    | 'success'
    | 'error';

export interface UseQuerySubmitReturn {
    /** Current submission lifecycle status. */
    status: QuerySubmitStatus;
    /** True while the request is in flight — set synchronously on submit. */
    isSubmitting: boolean;
    /** Last successful response, or null if not yet submitted. */
    response: QueryStartResponse | null;
    /** User-facing error message, or null. */
    errorMessage: string | null;
    /** Field-level validation errors keyed by field name. */
    fieldErrors: Partial<Record<keyof QueryFormValues, string>>;
    /** Conversation ID stored from the most recent successful request. */
    conversationId: string | null;
    /** Submit the form — validates client-side first, then calls the API. */
    submit: (values: QueryFormValues) => Promise<void>;
    /** Reset state back to idle. */
    reset: () => void;
}

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

function validateFields(
    values: QueryFormValues,
): Partial<Record<keyof QueryFormValues, string>> {
    const errors: Partial<Record<keyof QueryFormValues, string>> = {};

    const trimmedQuery = values.nlQuery.trim();
    if (trimmedQuery.length < QUERY_MIN_LENGTH) {
        errors.nlQuery = 'Please enter a query.';
    } else if (trimmedQuery.length > QUERY_MAX_LENGTH) {
        errors.nlQuery = `Query must be at most ${QUERY_MAX_LENGTH.toLocaleString()} characters.`;
    }

    if (!values.databaseId.trim()) {
        errors.databaseId = 'Please select a database.';
    }

    return errors;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useQuerySubmit(): UseQuerySubmitReturn {
    const { getToken } = useAuth();

    const [status, setStatus] = useState<QuerySubmitStatus>('idle');
    const [response, setResponse] = useState<QueryStartResponse | null>(null);
    const [errorMessage, setErrorMessage] = useState<string | null>(null);
    const [fieldErrors, setFieldErrors] = useState<
        Partial<Record<keyof QueryFormValues, string>>
    >({});
    const [conversationId, setConversationId] = useState<string | null>(() =>
        sessionStorage.getItem(CONVERSATION_ID_KEY),
    );

    // AbortController to cancel requests on unmount
    const abortRef = useRef<AbortController | null>(null);

    // Cancel in-flight request on unmount
    useEffect(() => {
        return () => {
            abortRef.current?.abort();
        };
    }, []);

    const reset = useCallback(() => {
        abortRef.current?.abort();
        setStatus('idle');
        setResponse(null);
        setErrorMessage(null);
        setFieldErrors({});
    }, []);

    const submit = useCallback(
        async (values: QueryFormValues): Promise<void> => {
            // --- 1. Client-side validation (synchronous, <1 ms) ---
            const errors = validateFields(values);
            if (Object.keys(errors).length > 0) {
                setFieldErrors(errors);
                return;
            }
            setFieldErrors({});

            // --- 2. Set loading flag IMMEDIATELY (NFR-2: ≤100 ms indicator) ---
            setStatus('submitting');
            setErrorMessage(null);
            setResponse(null);

            // --- 3. Build request payload ---
            const payload: QueryStartRequest = {
                query: values.nlQuery.trim(),
                database_id: values.databaseId,
            };

            // Abort any previous in-flight request before creating a new one
            abortRef.current?.abort();
            abortRef.current = new AbortController();

            try {
                const token = await getToken();
                if (!token) throw new Error('Authentication token unavailable.');

                const result = await apiClient.startQuery(
                    payload,
                    token,
                    abortRef.current.signal,
                );

                // --- 4. Store conversation_id in session state (FR-90) ---
                sessionStorage.setItem(CONVERSATION_ID_KEY, result.conversation_id);
                setConversationId(result.conversation_id);
                setResponse(result);
                setStatus('success');
            } catch (err) {
                if (err instanceof ApiError && err.code === 'REQUEST_CANCELLED') {
                    // Ignore deliberate cancellations
                    setStatus('idle');
                    return;
                }
                const message =
                    err instanceof ApiError
                        ? err.message
                        : 'An unexpected error occurred. Please try again.';
                setErrorMessage(message);
                setStatus('error');
            }
        },
        [getToken],
    );

    return {
        status,
        isSubmitting: status === 'submitting',
        response,
        errorMessage,
        fieldErrors,
        conversationId,
        submit,
        reset,
    };
}
