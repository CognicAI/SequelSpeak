/**
 * QueryChatPage — top-level chat page container.
 *
 * Responsibilities:
 * - Receives active connection props from App.tsx
 * - Detects credential expiry or profile switch before send
 * - Orchestrates useConversation state machine
 * - Renders ConversationThread + ConversationStatusBanner + ConversationComposer
 * - Shows ClarificationPromptCard when status === 'clarification_needed'
 * - Opens PasswordPromptModal on needsReauth, resumes after success
 */

import { useState, useCallback, useMemo } from 'react';
import { useAuth } from '@clerk/clerk-react';
import { ArrowLeft } from 'lucide-react';
import { cn } from '../lib/utils';
import { useConversation } from '../hooks/useConversation';
import { useProfileSelection } from '../hooks/useProfileSelection';
import { ConversationThread } from './ConversationThread';
import { ConversationComposer } from './ConversationComposer';
import { ConversationStatusBanner } from './ConversationStatusBanner';
import { ClarificationPromptCard } from './ClarificationPromptCard';
import { PasswordPromptModal } from './PasswordPromptModal';
import { apiClient } from '../services/api/client';
import { ApiError } from '../services/api/errors';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface QueryChatPageProps {
    /** UUID of the authenticated connection profile. */
    activeConnectionProfileId: string;
    /** Epoch ms when the active credentials expire. */
    activeConnectionExpiresAtMs: number | null;
    /** Called after successful re-auth so App.tsx can update its own state. */
    onConnectionActivated: (profileId: string, expiresAtMs: number) => void;
    /** Navigate back to the connection page. */
    onGoToConnect: () => void;
    className?: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function QueryChatPage({
    activeConnectionProfileId,
    activeConnectionExpiresAtMs,
    onConnectionActivated,
    onGoToConnect,
    className,
}: QueryChatPageProps) {
    const { getToken } = useAuth();
    const { profiles } = useProfileSelection();

    const {
        conversation,
        isBusy,
        sendMessage,
        sendClarification,
        handleCredentialsExpired,
        handleReauthSuccess,
        setDatabase,
        reset,
    } = useConversation();

    // ── Password modal state
    const [isPromptOpen, setIsPromptOpen] = useState(false);
    const [promptError, setPromptError] = useState<string | null>(null);
    const [promptLoading, setPromptLoading] = useState(false);
    const [pendingProfileId, setPendingProfileId] = useState<string | null>(null);

    // ── The profile whose credentials the modal is asking for
    const promptProfile = useMemo(
        () => profiles.find(p => p.id === (pendingProfileId ?? conversation.selectedDatabaseId)) ?? null,
        [profiles, pendingProfileId, conversation.selectedDatabaseId],
    );

    // ── Credential guard — called just before sending a message
    const isCredentialExpired =
        activeConnectionExpiresAtMs !== null && Date.now() >= activeConnectionExpiresAtMs;

    const credentialsAreValid = (selectedDbId: string) =>
        selectedDbId === activeConnectionProfileId && !isCredentialExpired;

    // ── Handle send from composer
    const handleSend = useCallback(
        async (nlQuery: string, databaseId: string) => {
            if (!credentialsAreValid(databaseId)) {
                // Block before sending — show modal then retry
                setPendingProfileId(databaseId);
                setIsPromptOpen(true);
                handleCredentialsExpired();
                return;
            }
            await sendMessage(nlQuery, databaseId);
        },
        // eslint-disable-next-line react-hooks/exhaustive-deps
        [activeConnectionProfileId, activeConnectionExpiresAtMs, sendMessage, handleCredentialsExpired],
    );

    // ── Handle database change in composer — if switching to a different profile
    const handleDatabaseChange = useCallback(
        (databaseId: string) => {
            setDatabase(databaseId);
            if (!credentialsAreValid(databaseId)) {
                setPendingProfileId(databaseId);
                setIsPromptOpen(true);
                handleCredentialsExpired();
            }
        },
        // eslint-disable-next-line react-hooks/exhaustive-deps
        [activeConnectionProfileId, activeConnectionExpiresAtMs, setDatabase, handleCredentialsExpired],
    );

    // ── Password modal submit
    const handlePasswordSubmit = useCallback(
        async (password: string) => {
            const profileId = pendingProfileId ?? conversation.selectedDatabaseId;
            if (!profileId) return;

            setPromptLoading(true);
            setPromptError(null);

            try {
                const token = await getToken();
                if (!token) throw new Error('Authentication token unavailable.');

                await apiClient.testConnection(undefined, token, undefined, profileId, password);

                const expiresAtMs = Date.now() + 60 * 60 * 1000; // 1 h
                onConnectionActivated(profileId, expiresAtMs);
                handleReauthSuccess(profileId, expiresAtMs);
                setIsPromptOpen(false);
                setPendingProfileId(null);
            } catch (err) {
                const message =
                    err instanceof ApiError ? err.message : 'Failed to authenticate. Please try again.';
                setPromptError(message);
            } finally {
                setPromptLoading(false);
            }
        },
        [
            getToken,
            pendingProfileId,
            conversation.selectedDatabaseId,
            onConnectionActivated,
            handleReauthSuccess,
        ],
    );

    const handleModalClose = useCallback(() => {
        setIsPromptOpen(false);
        setPromptError(null);
    }, []);

    // ── Clarification handler
    const handleClarification = useCallback(
        async (answers: string[]) => {
            await sendClarification(answers);
        },
        [sendClarification],
    );

    return (
        <div
            className={cn('flex flex-col h-full w-full', className)}
            data-testid="query-chat-page"
        >
            {/* Top bar */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-white/10 shrink-0">
                <ConversationStatusBanner
                    status={conversation.status}
                    stage={conversation.stage}
                    needsReauth={conversation.needsReauth}
                    className="flex-1 mr-4"
                />

                <div className="flex items-center gap-2">
                    {conversation.messages.length > 0 && (
                        <button
                            type="button"
                            onClick={reset}
                            className="px-3 py-1.5 rounded-lg text-xs font-medium border border-white/10 text-gray-400 hover:text-white hover:bg-white/10 transition-colors"
                            aria-label="Start a new conversation"
                        >
                            New chat
                        </button>
                    )}
                    <button
                        type="button"
                        onClick={onGoToConnect}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border border-white/10 text-gray-400 hover:text-white hover:bg-white/10 transition-colors"
                        aria-label="Change database connection"
                    >
                        <ArrowLeft className="w-3.5 h-3.5" aria-hidden />
                        Change connection
                    </button>
                </div>
            </div>

            {/* Thread */}
            <ConversationThread
                messages={conversation.messages}
                className="flex-1 min-h-0"
            />

            {/* Clarification card — shown when backend needs user input */}
            {conversation.status === 'clarification_needed' &&
                conversation.pendingClarificationQuestions.length > 0 && (
                    <div className="px-4 pb-2 shrink-0">
                        <ClarificationPromptCard
                            questions={conversation.pendingClarificationQuestions}
                            isSubmitting={isBusy}
                            onSubmit={handleClarification}
                        />
                    </div>
                )}

            {/* Conversation ID debug trace (only shown if present) */}
            {conversation.id && (
                <p className="text-center text-[10px] text-gray-700 pb-1 select-none shrink-0">
                    conversation{' '}
                    <span className="font-mono">{conversation.id.slice(0, 8)}…</span>
                </p>
            )}

            {/* Composer */}
            <div className="px-4 pb-4 shrink-0">
                <ConversationComposer
                    onSend={handleSend}
                    onDatabaseChange={handleDatabaseChange}
                    isProcessing={conversation.status === 'processing' || isBusy}
                    needsReauth={conversation.needsReauth}
                    defaultDatabaseId={activeConnectionProfileId}
                />
            </div>

            {/* Password modal */}
            <PasswordPromptModal
                isOpen={isPromptOpen}
                onClose={handleModalClose}
                onSubmit={handlePasswordSubmit}
                profileName={promptProfile?.name ?? 'Database'}
                error={promptError}
                isLoading={promptLoading}
            />
        </div>
    );
}
