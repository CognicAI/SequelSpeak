/**
 * QueryForm — natural language query entry point.
 *
 * Features
 * --------
 * - Textarea for NL query (with character counter)
 * - Database selector dropdown bound to saved connection profiles
 * - Client-side validation before submission
 * - Immediate loading indicator before network submit (NFR-2: ≤100 ms)
 * - Enforces active DB credentials before query start
 * - Re-prompts password when selected profile changes or auth expires
 * - Stores returned conversation_id in session state (FR-90)
 */

import { useState, useCallback, useMemo, type FormEvent } from 'react';
import { Send, Database, Loader2, CheckCircle2, AlertCircle, ShieldAlert } from 'lucide-react';
import { useAuth } from '@clerk/clerk-react';
import { cn } from '../lib/utils';
import { useQuerySubmit } from '../hooks/useQuerySubmit';
import { useProfileSelection } from '../hooks/useProfileSelection';
import { QUERY_MAX_LENGTH } from '../types/query';
import { apiClient } from '../services/api/client';
import { ApiError } from '../services/api/errors';
import { PasswordPromptModal } from './PasswordPromptModal';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface QueryFormProps {
    /** Called with the conversation_id after a successful submission. */
    onConversationStarted?: (conversationId: string) => void;
    /** Currently active authenticated connection profile. */
    activeConnectionProfileId?: string | null;
    /** Epoch ms when the current credential cache expires. */
    activeConnectionExpiresAtMs?: number | null;
    /** Notifies parent when a profile is re-authenticated and becomes active. */
    onConnectionActivated?: (profileId: string, expiresAtMs: number) => void;
    /** Additional CSS classes for the root element. */
    className?: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function QueryForm({
    onConversationStarted,
    activeConnectionProfileId = null,
    activeConnectionExpiresAtMs = null,
    onConnectionActivated,
    className,
}: QueryFormProps) {
    const { getToken } = useAuth();
    const [nlQuery, setNlQuery] = useState('');
    const [selectedDatabaseId, setSelectedDatabaseId] = useState('');
    const [credentialMessage, setCredentialMessage] = useState<string | null>(null);

    const [isPromptOpen, setIsPromptOpen] = useState(false);
    const [promptError, setPromptError] = useState<string | null>(null);
    const [promptLoading, setPromptLoading] = useState(false);
    const [pendingSubmission, setPendingSubmission] = useState<{ nlQuery: string; databaseId: string } | null>(null);

    const {
        isSubmitting,
        status,
        errorMessage,
        fieldErrors,
        response,
        submit,
        reset,
    } = useQuerySubmit();

    const {
        profiles,
        isLoading: profilesLoading,
        error: profilesError,
    } = useProfileSelection();

    const selectedProfile = useMemo(
        () => profiles.find((p) => p.id === selectedDatabaseId) ?? null,
        [profiles, selectedDatabaseId],
    );

    const isCredentialExpired =
        activeConnectionExpiresAtMs !== null && Date.now() >= activeConnectionExpiresAtMs;

    const requiresReauth =
        !activeConnectionProfileId ||
        activeConnectionProfileId !== selectedDatabaseId ||
        isCredentialExpired;

    const runQuerySubmit = useCallback(async (values: { nlQuery: string; databaseId: string }) => {
        await submit(values);
    }, [submit]);

    const authenticateSelectedProfile = useCallback(async (password: string): Promise<boolean> => {
        if (!selectedDatabaseId) return false;

        setPromptLoading(true);
        setPromptError(null);

        try {
            const token = await getToken();
            if (!token) {
                throw new Error('Authentication token unavailable.');
            }

            await apiClient.testConnection(undefined, token, undefined, selectedDatabaseId, password);

            const expiresAtMs = Date.now() + (60 * 60 * 1000);
            onConnectionActivated?.(selectedDatabaseId, expiresAtMs);
            setCredentialMessage('Connection authenticated. Query execution resumed.');
            setIsPromptOpen(false);
            return true;
        } catch (err) {
            const message = err instanceof ApiError ? err.message : 'Failed to authenticate. Please try again.';
            setPromptError(message);
            return false;
        } finally {
            setPromptLoading(false);
        }
    }, [getToken, onConnectionActivated, selectedDatabaseId]);

    // -----------------------------------------------------------------------
    // Form submission
    // -----------------------------------------------------------------------

    const handleSubmit = useCallback(
        async (e: FormEvent<HTMLFormElement>) => {
            e.preventDefault();
            setCredentialMessage(null);

            const trimmedQuery = nlQuery.trim();
            const hasLocalValidationError =
                trimmedQuery.length === 0 ||
                trimmedQuery.length > QUERY_MAX_LENGTH ||
                !selectedDatabaseId.trim();

            if (hasLocalValidationError) {
                await runQuerySubmit({ nlQuery, databaseId: selectedDatabaseId });
                return;
            }

            // Gate query creation behind an active authenticated connection.
            if (requiresReauth) {
                setPendingSubmission({ nlQuery, databaseId: selectedDatabaseId });
                setIsPromptOpen(true);
                return;
            }

            // Loading flag is set synchronously inside submit() before await,
            // so the processing indicator renders within the same event loop tick.
            await runQuerySubmit({ nlQuery, databaseId: selectedDatabaseId });
        },
        [nlQuery, selectedDatabaseId, requiresReauth, runQuerySubmit],
    );

    const handlePromptSubmit = useCallback(async (password: string) => {
        const authenticated = await authenticateSelectedProfile(password);
        if (!authenticated || !pendingSubmission) {
            return;
        }

        await runQuerySubmit(pendingSubmission);
        setPendingSubmission(null);
    }, [authenticateSelectedProfile, pendingSubmission, runQuerySubmit]);

    // Notify parent once we have a conversation_id
    if (status === 'success' && response && onConversationStarted) {
        onConversationStarted(response.conversation_id);
    }

    // -----------------------------------------------------------------------
    // Derived state
    // -----------------------------------------------------------------------

    const charsRemaining = QUERY_MAX_LENGTH - nlQuery.length;
    const isOverLimit = charsRemaining < 0;
    const isDisabled = isSubmitting;

    // -----------------------------------------------------------------------
    // Render
    // -----------------------------------------------------------------------

    return (
        <div
            className={cn(
                'w-full rounded-2xl border border-white/10 bg-white/5 backdrop-blur-sm p-6 space-y-5',
                className,
            )}
            data-testid="query-form-container"
        >
            {/* Heading */}
            <div className="space-y-1">
                <h2 className="text-lg font-semibold text-white">Ask your database</h2>
                <p className="text-sm text-gray-400">
                    Type a question in plain English and SequelSpeak will convert it to SQL.
                </p>
            </div>

            <form onSubmit={handleSubmit} noValidate aria-label="Query form" className="space-y-4">

                {/* Database selector */}
                <div className="space-y-1.5">
                    <label
                        htmlFor="query-database-select"
                        className="flex items-center gap-1.5 text-sm font-medium text-gray-300"
                    >
                        <Database className="w-3.5 h-3.5" aria-hidden="true" />
                        Database
                    </label>

                    {profilesError && (
                        <p className="text-xs text-red-400" role="alert">
                            Could not load profiles: {profilesError}
                        </p>
                    )}

                    <select
                        id="query-database-select"
                        data-testid="database-select"
                        value={selectedDatabaseId}
                        onChange={(e) => {
                            setSelectedDatabaseId(e.target.value);
                            setCredentialMessage(null);
                            if (fieldErrors.databaseId) reset();
                        }}
                        disabled={isDisabled || profilesLoading}
                        aria-required="true"
                        aria-describedby={
                            fieldErrors.databaseId ? 'db-error' : undefined
                        }
                        aria-invalid={!!fieldErrors.databaseId}
                        className={cn(
                            'w-full rounded-lg bg-white/5 border px-3 py-2.5 text-sm text-white',
                            'focus:outline-none focus:ring-2 focus:ring-primary/60',
                            'disabled:opacity-50 disabled:cursor-not-allowed',
                            fieldErrors.databaseId
                                ? 'border-red-500/70'
                                : 'border-white/10 hover:border-white/20',
                        )}
                    >
                        <option value="" disabled className="bg-gray-900">
                            {profilesLoading ? 'Loading profiles…' : 'Select a database…'}
                        </option>
                        {profiles.map((p) => (
                            <option key={p.id} value={p.id} className="bg-gray-900">
                                {p.name} — {p.host}/{p.database}
                            </option>
                        ))}
                    </select>

                    {fieldErrors.databaseId && (
                        <p
                            id="db-error"
                            role="alert"
                            className="flex items-center gap-1 text-xs text-red-400"
                        >
                            <AlertCircle className="w-3 h-3 shrink-0" aria-hidden="true" />
                            {fieldErrors.databaseId}
                        </p>
                    )}

                    {selectedDatabaseId && requiresReauth && (
                        <p className="flex items-center gap-1 text-xs text-amber-300" role="status">
                            <ShieldAlert className="w-3 h-3 shrink-0" aria-hidden="true" />
                            Credentials required for {selectedProfile?.name ?? 'selected profile'} before query execution.
                        </p>
                    )}
                </div>

                {/* NL query textarea */}
                <div className="space-y-1.5">
                    <label
                        htmlFor="query-nl-input"
                        className="text-sm font-medium text-gray-300"
                    >
                        Your question
                    </label>

                    <textarea
                        id="query-nl-input"
                        data-testid="nl-query-input"
                        value={nlQuery}
                        onChange={(e) => {
                            setNlQuery(e.target.value);
                            if (fieldErrors.nlQuery) reset();
                        }}
                        placeholder="e.g. Show me total revenue by month for the last quarter"
                        rows={4}
                        disabled={isDisabled}
                        required
                        aria-required="true"
                        aria-describedby={cn(
                            fieldErrors.nlQuery ? 'nl-error' : '',
                            'char-counter',
                        ).trim() || undefined}
                        aria-invalid={!!fieldErrors.nlQuery}
                        className={cn(
                            'w-full resize-none rounded-lg bg-white/5 border px-3 py-2.5',
                            'text-sm text-white placeholder:text-gray-500',
                            'focus:outline-none focus:ring-2 focus:ring-primary/60',
                            'disabled:opacity-50 disabled:cursor-not-allowed',
                            isOverLimit
                                ? 'border-red-500/70'
                                : fieldErrors.nlQuery
                                  ? 'border-red-500/70'
                                  : 'border-white/10 hover:border-white/20',
                        )}
                    />

                    {/* Character counter */}
                    <p
                        id="char-counter"
                        aria-live="polite"
                        className={cn(
                            'text-right text-xs',
                            isOverLimit ? 'text-red-400' : 'text-gray-500',
                        )}
                    >
                        {nlQuery.length.toLocaleString()} / {QUERY_MAX_LENGTH.toLocaleString()}
                    </p>

                    {fieldErrors.nlQuery && (
                        <p
                            id="nl-error"
                            role="alert"
                            className="flex items-center gap-1 text-xs text-red-400"
                        >
                            <AlertCircle className="w-3 h-3 shrink-0" aria-hidden="true" />
                            {fieldErrors.nlQuery}
                        </p>
                    )}
                </div>

                {/* API-level error */}
                {status === 'error' && errorMessage && (
                    <div
                        role="alert"
                        data-testid="submission-error"
                        className="flex items-start gap-2 rounded-lg bg-red-500/10 border border-red-500/20 px-3 py-2.5 text-sm text-red-400"
                    >
                        <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" />
                        <span>{errorMessage}</span>
                    </div>
                )}

                {credentialMessage && (
                    <div
                        role="status"
                        className="flex items-start gap-2 rounded-lg bg-amber-500/10 border border-amber-500/20 px-3 py-2.5 text-sm text-amber-300"
                    >
                        <ShieldAlert className="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" />
                        <span>{credentialMessage}</span>
                    </div>
                )}

                {/* Success banner */}
                {status === 'success' && response && (
                    <div
                        role="status"
                        data-testid="submission-success"
                        className="flex items-start gap-2 rounded-lg bg-green-500/10 border border-green-500/20 px-3 py-2.5 text-sm text-green-400"
                    >
                        <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" />
                        <span>{response.message}</span>
                    </div>
                )}

                {/* Submit button */}
                <button
                    type="submit"
                    data-testid="submit-button"
                    disabled={isDisabled || isOverLimit}
                    aria-busy={isSubmitting}
                    className={cn(
                        'w-full flex items-center justify-center gap-2',
                        'rounded-lg px-4 py-2.5 text-sm font-medium transition-opacity',
                        'bg-gradient-to-r from-primary to-secondary text-white',
                        'hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-primary/60',
                        'disabled:opacity-50 disabled:cursor-not-allowed',
                    )}
                >
                    {isSubmitting ? (
                        <>
                            <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                            Processing…
                        </>
                    ) : (
                        <>
                            <Send className="w-4 h-4" aria-hidden="true" />
                            Run Query
                        </>
                    )}
                </button>
            </form>

            <PasswordPromptModal
                isOpen={isPromptOpen}
                onClose={() => {
                    setIsPromptOpen(false);
                    setPendingSubmission(null);
                }}
                onSubmit={handlePromptSubmit}
                profileName={selectedProfile?.name || 'Database'}
                error={promptError}
                isLoading={promptLoading}
            />
        </div>
    );
}
