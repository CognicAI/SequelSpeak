/**
 * useConversationStatus — streams GET /api/v1/query/status/{id}/stream via SSE.
 *
 * Behaviour:
 * - Opens EventSource when conversationId is non-null and status is active.
 * - Emits onUpdate on `progress` and terminal events.
 * - Closes stream on terminal events.
 * - Dispatches onTimeout when stream emits `timeout`.
 * - Cleans up stream connection on unmount.
 */

import { useEffect, useRef } from 'react';
import { useAuth } from '@clerk/clerk-react';
import type { QueryStatusResponse } from '../types/conversation';
import type { ConversationStatus } from '../types/conversation';

/** Statuses that should keep the stream open. */
const ACTIVE_STATUSES = new Set<string>(['processing', 'clarification_needed']);

/** Statuses that close the stream. */
const TERMINAL_STATUSES = new Set<string>(['complete', 'error', 'timeout', 'cancelled']);

interface UseConversationStatusOptions {
    conversationId: string | null;
    /** Current conversation status — controls whether polling runs. */
    status: ConversationStatus;
    onUpdate: (data: QueryStatusResponse) => void;
    onCredentialsExpired: () => void;
    onTimeout: () => void;
    onError: (message: string) => void;
}

export function useConversationStatus({
    conversationId,
    status,
    onUpdate,
    onCredentialsExpired,
    onTimeout,
    onError,
}: UseConversationStatusOptions): void {
    const { getToken } = useAuth();
    const eventSourceRef = useRef<EventSource | null>(null);

    // Keep latest callbacks in refs so event listeners always use current handlers
    const onUpdateRef = useRef(onUpdate);
    const onCredentialsExpiredRef = useRef(onCredentialsExpired);
    const onTimeoutRef = useRef(onTimeout);
    const onErrorRef = useRef(onError);
    useEffect(() => { onUpdateRef.current = onUpdate; }, [onUpdate]);
    useEffect(() => { onCredentialsExpiredRef.current = onCredentialsExpired; }, [onCredentialsExpired]);
    useEffect(() => { onTimeoutRef.current = onTimeout; }, [onTimeout]);
    useEffect(() => { onErrorRef.current = onError; }, [onError]);

    useEffect(() => {
        const shouldStream = conversationId && ACTIVE_STATUSES.has(status);

        if (!shouldStream) {
            eventSourceRef.current?.close();
            eventSourceRef.current = null;
            return;
        }

        if (TERMINAL_STATUSES.has(status)) {
            return;
        }

        let cancelled = false;

        const connect = async (): Promise<void> => {
            try {
                const token = await getToken();
                if (!token) {
                    onCredentialsExpiredRef.current();
                    return;
                }

                if (cancelled) {
                    return;
                }

                eventSourceRef.current?.close();
                const streamUrl = `/api/v1/query/status/${encodeURIComponent(conversationId)}/stream?access_token=${encodeURIComponent(token)}`;
                const source = new EventSource(streamUrl);
                eventSourceRef.current = source;

                source.addEventListener('progress', (event: MessageEvent) => {
                    try {
                        const data = JSON.parse(event.data) as QueryStatusResponse;
                        onUpdateRef.current(data);
                    } catch {
                        onErrorRef.current('Received malformed progress update from stream.');
                    }
                });

                source.addEventListener('complete', (event: MessageEvent) => {
                    try {
                        const data = JSON.parse(event.data) as QueryStatusResponse;
                        onUpdateRef.current(data);
                    } finally {
                        source.close();
                    }
                });

                source.addEventListener('clarification_needed', (event: MessageEvent) => {
                    try {
                        const data = JSON.parse(event.data) as QueryStatusResponse;
                        onUpdateRef.current(data);
                    } finally {
                        source.close();
                    }
                });

                source.addEventListener('cancelled', (event: MessageEvent) => {
                    try {
                        const data = JSON.parse(event.data) as QueryStatusResponse;
                        onUpdateRef.current(data);
                    } finally {
                        source.close();
                    }
                });

                source.addEventListener('error', (event: Event) => {
                    const maybeMessageEvent = event as MessageEvent;

                    // Server-originated SSE error payload
                    if (typeof maybeMessageEvent.data === 'string' && maybeMessageEvent.data.length > 0) {
                        try {
                            const payload = JSON.parse(maybeMessageEvent.data) as { error?: string };
                            onErrorRef.current(payload.error ?? 'Streaming status failed.');
                        } catch {
                            onErrorRef.current('Streaming status failed.');
                        }
                        source.close();
                    }
                    // Network-level disconnects trigger EventSource auto-retry.
                });

                source.addEventListener('timeout', () => {
                    onTimeoutRef.current();
                    source.close();
                });
            } catch {
                onErrorRef.current('Failed to establish status stream.');
            }
        };

        void connect();

        return () => {
            cancelled = true;
            eventSourceRef.current?.close();
            eventSourceRef.current = null;
        };
    }, [conversationId, status, getToken]);
}
