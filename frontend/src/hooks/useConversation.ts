/**
 * useConversation — central state machine for the chat UI.
 *
 * Drives a ConversationViewModel via useReducer. Composes:
 *   - useConversationStart  (POST /query/start)
 *   - useConversationStatus (SSE stream GET /query/status/{id}/stream)
 *   - useConversationRespond (POST /query/respond)
 *
 * Credential expiry (FR-130): treated as a system error, not clarification.
 * Timeout (FR-82): detected from streaming, dispatches CONVERSATION_TIMEOUT,
 *   stops streaming, composer is disabled.
 */

import { useReducer, useCallback } from 'react';
import { useConversationStart } from './useConversationStart';
import { useConversationStatus } from './useConversationStatus';
import { useConversationRespond } from './useConversationRespond';
import type {
    ConversationViewModel,
    ConversationMessage,
    ConversationStatus,
    QueryStatusResponse,
    QueryRespondRequest,
} from '../types/conversation';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeMsg(
    role: ConversationMessage['role'],
    kind: ConversationMessage['kind'],
    content: string,
    metadata?: Record<string, unknown>,
): ConversationMessage {
    return { id: crypto.randomUUID(), role, kind, content, createdAt: new Date().toISOString(), metadata };
}

const PROCESSING_PLACEHOLDER_ID = '__processing__';

function processingBubble(): ConversationMessage {
    return {
        id: PROCESSING_PLACEHOLDER_ID,
        role: 'assistant',
        kind: 'text',
        content: '…',
        createdAt: new Date().toISOString(),
    };
}

/** Map backend status string to our ConversationStatus union type. */
function mapBackendStatus(s: string): ConversationStatus {
    const map: Record<string, ConversationStatus> = {
        processing: 'processing',
        clarification_needed: 'clarification_needed',
        complete: 'complete',
        error: 'error',
        timeout: 'error',   // timeout is surfaced as error with system message
        cancelled: 'error',
    };
    return map[s] ?? 'error';
}

// ---------------------------------------------------------------------------
// Reducer
// ---------------------------------------------------------------------------

type Action =
    | { type: 'SEND_MESSAGE'; payload: { content: string; databaseId: string } }
    | { type: 'CONVERSATION_STARTED'; payload: { conversationId: string } }
    | { type: 'START_ERROR'; payload: { message: string } }
    | { type: 'STATUS_UPDATE'; payload: QueryStatusResponse }
    | { type: 'SEND_CLARIFICATION'; payload: { answers: string[] } }
    | { type: 'CLARIFICATION_SENT' }
    | { type: 'RESPOND_ERROR'; payload: { message: string } }
    | { type: 'CREDENTIALS_EXPIRED' }
    | { type: 'REAUTH_SUCCESS'; payload: { profileId: string; expiresAtMs: number } }
    | { type: 'CONVERSATION_TIMEOUT' }
    | { type: 'SET_DATABASE'; payload: { databaseId: string } }
    | { type: 'RESET' };

const initialState: ConversationViewModel = {
    id: null,
    status: 'idle',
    stage: null,
    messages: [],
    pendingClarificationQuestions: [],
    generatedSql: null,
    result: null,
    explanation: null,
    needsReauth: false,
    selectedDatabaseId: '',
};

function reducer(state: ConversationViewModel, action: Action): ConversationViewModel {
    switch (action.type) {
        case 'SEND_MESSAGE': {
            const userMsg = makeMsg('user', 'text', action.payload.content);
            return {
                ...state,
                status: 'processing',
                selectedDatabaseId: action.payload.databaseId,
                messages: [...state.messages, userMsg, processingBubble()],
            };
        }

        case 'CONVERSATION_STARTED':
            return { ...state, id: action.payload.conversationId };

        case 'START_ERROR': {
            // Remove the processing placeholder
            const msgs = state.messages.filter(m => m.id !== PROCESSING_PLACEHOLDER_ID);
            return {
                ...state,
                status: 'error',
                messages: [...msgs, makeMsg('system', 'error', action.payload.message)],
            };
        }

        case 'STATUS_UPDATE': {
            const data = action.payload;
            const newStatus = mapBackendStatus(data.status);
            // Remove processing placeholder
            const msgs = state.messages.filter(m => m.id !== PROCESSING_PLACEHOLDER_ID);

            let additions: ConversationMessage[] = [];

            if (newStatus === 'clarification_needed' && data.pending_clarification_questions.length > 0) {
                // Inject one clarification bubble per question
                additions = data.pending_clarification_questions.map(q =>
                    makeMsg('assistant', 'clarification', q),
                );
            }

            if (newStatus === 'complete') {
                if (data.explanation) {
                    additions.push(makeMsg('assistant', 'text', data.explanation, {
                        generated_sql: data.generated_sql,
                        execution_result: data.execution_result,
                    }));
                }
                if (data.generated_sql) {
                    additions.push(makeMsg('assistant', 'result', data.generated_sql, {
                        execution_result: data.execution_result,
                    }));
                }
            }

            if (newStatus === 'error') {
                additions.push(makeMsg('system', 'error', 'An error occurred during execution.'));
            }

            return {
                ...state,
                status: newStatus,
                stage: data.current_stage,
                pendingClarificationQuestions: data.pending_clarification_questions,
                generatedSql: data.generated_sql,
                result: data.execution_result,
                explanation: data.explanation,
                messages: [...msgs, ...additions],
                // Keep processing placeholder when still processing
                ...(newStatus === 'processing' ? { messages: [...msgs, processingBubble()] } : {}),
            };
        }

        case 'SEND_CLARIFICATION':
            return { ...state, status: 'processing', messages: [...state.messages, processingBubble()] };

        case 'CLARIFICATION_SENT':
            return state; // polling will pick up the new status

        case 'RESPOND_ERROR': {
            const msgs = state.messages.filter(m => m.id !== PROCESSING_PLACEHOLDER_ID);
            return {
                ...state,
                status: 'error',
                messages: [...msgs, makeMsg('system', 'error', action.payload.message)],
            };
        }

        case 'CREDENTIALS_EXPIRED': {
            const msgs = state.messages.filter(m => m.id !== PROCESSING_PLACEHOLDER_ID);
            return {
                ...state,
                status: 'error',
                needsReauth: true,
                messages: [
                    ...msgs,
                    makeMsg('system', 'error', 'Credentials expired. Re-enter your password to continue.'),
                ],
            };
        }

        case 'REAUTH_SUCCESS':
            return { ...state, needsReauth: false, status: 'idle' };

        case 'CONVERSATION_TIMEOUT': {
            const msgs = state.messages.filter(m => m.id !== PROCESSING_PLACEHOLDER_ID);
            return {
                ...state,
                status: 'error',
                messages: [
                    ...msgs,
                    makeMsg('system', 'error', 'Conversation timed out after 30 minutes of inactivity. Start a new query to continue.'),
                ],
            };
        }

        case 'SET_DATABASE':
            return { ...state, selectedDatabaseId: action.payload.databaseId };

        case 'RESET':
            return { ...initialState };

        default:
            return state;
    }
}

// ---------------------------------------------------------------------------
// Public interface
// ---------------------------------------------------------------------------

export interface UseConversationReturn {
    conversation: ConversationViewModel;
    /** isStarting || isResponding */
    isBusy: boolean;
    sendMessage: (nlQuery: string, databaseId: string) => Promise<void>;
    sendClarification: (answers: string[]) => Promise<void>;
    handleCredentialsExpired: () => void;
    handleReauthSuccess: (profileId: string, expiresAtMs: number) => void;
    setDatabase: (databaseId: string) => void;
    reset: () => void;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useConversation(): UseConversationReturn {
    const [conversation, dispatch] = useReducer(reducer, initialState);
    const { start, isStarting } = useConversationStart();
    const { respond, isResponding } = useConversationRespond();

    // ---- Polling ----
    useConversationStatus({
        conversationId: conversation.id,
        status: conversation.status,
        onUpdate: useCallback((data: QueryStatusResponse) => {
            dispatch({ type: 'STATUS_UPDATE', payload: data });
        }, []),
        onCredentialsExpired: useCallback(() => {
            dispatch({ type: 'CREDENTIALS_EXPIRED' });
        }, []),
        onTimeout: useCallback(() => {
            dispatch({ type: 'CONVERSATION_TIMEOUT' });
        }, []),
        onError: useCallback((message: string) => {
            dispatch({ type: 'START_ERROR', payload: { message } });
        }, []),
    });

    // ---- Actions ----

    const sendMessage = useCallback(async (nlQuery: string, databaseId: string) => {
        // Optimistic: immediately show user bubble
        dispatch({ type: 'SEND_MESSAGE', payload: { content: nlQuery, databaseId } });

        const result = await start(nlQuery, databaseId);
        if (!result) {
            // start() already set its own error state; surface it
            dispatch({ type: 'START_ERROR', payload: { message: 'Failed to start conversation.' } });
            return;
        }

        dispatch({ type: 'CONVERSATION_STARTED', payload: { conversationId: result.conversation_id } });
    }, [start]);

    const sendClarification = useCallback(async (answers: string[]) => {
        if (!conversation.id) return;
        dispatch({ type: 'SEND_CLARIFICATION', payload: { answers } });

        const payload: QueryRespondRequest = {
            conversation_id: conversation.id,
            answers,
            database_id: conversation.selectedDatabaseId || undefined,
        };
        const result = await respond(payload);
        if (!result) {
            dispatch({ type: 'RESPOND_ERROR', payload: { message: 'Failed to send answer.' } });
        }
        // Success: polling will pick up new status automatically
    }, [conversation.id, conversation.selectedDatabaseId, respond]);

    const handleCredentialsExpired = useCallback(() => {
        dispatch({ type: 'CREDENTIALS_EXPIRED' });
    }, []);

    const handleReauthSuccess = useCallback((profileId: string, expiresAtMs: number) => {
        dispatch({ type: 'REAUTH_SUCCESS', payload: { profileId, expiresAtMs } });
    }, []);

    const setDatabase = useCallback((databaseId: string) => {
        dispatch({ type: 'SET_DATABASE', payload: { databaseId } });
    }, []);

    const reset = useCallback(() => {
        dispatch({ type: 'RESET' });
    }, []);

    return {
        conversation,
        isBusy: isStarting || isResponding,
        sendMessage,
        sendClarification,
        handleCredentialsExpired,
        handleReauthSuccess,
        setDatabase,
        reset,
    };
}
