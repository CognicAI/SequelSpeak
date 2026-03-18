/**
 * ConversationComposer — DB selector + textarea + send button.
 *
 * Disabled when status is 'processing' OR needsReauth is true.
 * Emits onSend(nlQuery, databaseId) when the form is submitted.
 */

import { useState, useCallback, useMemo, type FormEvent, type KeyboardEvent } from 'react';
import { Send, Database, Loader2, ShieldAlert } from 'lucide-react';
import { cn } from '../lib/utils';
import { useProfileSelection } from '../hooks/useProfileSelection';
import { QUERY_MAX_LENGTH } from '../types/query';

interface ConversationComposerProps {
    onSend: (nlQuery: string, databaseId: string) => void;
    onDatabaseChange?: (databaseId: string) => void;
    /** Locks composer while backend is working. */
    isProcessing: boolean;
    /** Locks composer pending credential re-auth. */
    needsReauth: boolean;
    /** Pre-selected DB profile from App state (optional). */
    defaultDatabaseId?: string;
    className?: string;
}

export function ConversationComposer({
    onSend,
    onDatabaseChange,
    isProcessing,
    needsReauth,
    defaultDatabaseId = '',
    className,
}: ConversationComposerProps) {
    const [text, setText] = useState('');
    const [databaseId, setDatabaseId] = useState(defaultDatabaseId);

    const { profiles, isLoading: profilesLoading, error: profilesError } = useProfileSelection();

    const charsLeft = QUERY_MAX_LENGTH - text.length;
    const isOverLimit = charsLeft < 0;
    const isDisabled = isProcessing || needsReauth;
    const canSubmit = text.trim().length > 0 && databaseId.trim().length > 0 && !isOverLimit && !isDisabled;

    const selectedProfile = useMemo(
        () => profiles.find(p => p.id === databaseId) ?? null,
        [profiles, databaseId],
    );

    const handleDatabaseChange = useCallback((id: string) => {
        setDatabaseId(id);
        onDatabaseChange?.(id);
    }, [onDatabaseChange]);

    const handleSubmit = useCallback((e: FormEvent) => {
        e.preventDefault();
        if (!canSubmit) return;
        onSend(text.trim(), databaseId);
        setText('');
    }, [canSubmit, text, databaseId, onSend]);

    // Submit on Enter (not Shift+Enter)
    const handleKeyDown = useCallback((e: KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (canSubmit) {
                onSend(text.trim(), databaseId);
                setText('');
            }
        }
    }, [canSubmit, text, databaseId, onSend]);

    return (
        <div
            className={cn(
                'rounded-2xl border border-white/10 bg-white/5 backdrop-blur-sm p-4 space-y-3',
                needsReauth && 'opacity-60 pointer-events-none',
                className,
            )}
            aria-label="Message composer"
        >
            {/* Credentials warning when locked */}
            {needsReauth && (
                <p className="flex items-center gap-1.5 text-xs text-amber-400" role="alert">
                    <ShieldAlert className="w-3.5 h-3.5 shrink-0" aria-hidden />
                    Re-authenticate above to unlock the composer
                </p>
            )}

            <form onSubmit={handleSubmit} noValidate className="space-y-3">
                {/* Database selector */}
                <div className="flex items-center gap-2">
                    <Database className="w-3.5 h-3.5 text-gray-500 shrink-0" aria-hidden />
                    <label htmlFor="composer-db-select" className="sr-only">Select database</label>

                    {profilesError && (
                        <p className="text-xs text-red-400" role="alert">
                            Could not load profiles: {profilesError}
                        </p>
                    )}

                    <select
                        id="composer-db-select"
                        data-testid="composer-db-select"
                        value={databaseId}
                        onChange={e => handleDatabaseChange(e.target.value)}
                        disabled={isDisabled || profilesLoading}
                        aria-label="Select database profile"
                        className={cn(
                            'flex-1 rounded-lg bg-white/5 border border-white/10 px-2 py-1.5 text-xs text-white',
                            'focus:outline-none focus:ring-2 focus:ring-primary/40',
                            'disabled:opacity-40 disabled:cursor-not-allowed',
                        )}
                    >
                        <option value="" disabled className="bg-gray-900">
                            {profilesLoading ? 'Loading…' : 'Select a database…'}
                        </option>
                        {profiles.map(p => (
                            <option key={p.id} value={p.id} className="bg-gray-900">
                                {p.name} — {p.host}/{p.database}
                            </option>
                        ))}
                    </select>

                    {selectedProfile && (
                        <span className="text-xs text-gray-500 truncate max-w-[120px]">
                            {selectedProfile.host}
                        </span>
                    )}
                </div>

                {/* Textarea + send */}
                <div className="relative">
                    <textarea
                        id="composer-input"
                        data-testid="composer-input"
                        value={text}
                        onChange={e => setText(e.target.value)}
                        onKeyDown={handleKeyDown}
                        disabled={isDisabled}
                        placeholder="Ask a question… (Enter to send, Shift+Enter for new line)"
                        rows={3}
                        aria-label="Message"
                        aria-required="true"
                        className={cn(
                            'w-full resize-none rounded-xl bg-white/5 border px-3 py-2.5 pr-12',
                            'text-sm text-white placeholder:text-gray-600',
                            'focus:outline-none focus:ring-2 focus:ring-primary/40',
                            'disabled:opacity-40 disabled:cursor-not-allowed',
                            isOverLimit ? 'border-red-500/60' : 'border-white/10 hover:border-white/20',
                        )}
                    />

                    {/* Send button inside textarea */}
                    <button
                        type="submit"
                        data-testid="composer-send"
                        disabled={!canSubmit}
                        aria-label="Send message"
                        className={cn(
                            'absolute right-2 bottom-2 p-2 rounded-lg transition-all',
                            canSubmit
                                ? 'bg-primary text-white hover:bg-primary/80 shadow-md shadow-primary/30'
                                : 'bg-white/5 text-gray-600 cursor-not-allowed',
                        )}
                    >
                        {isProcessing
                            ? <Loader2 className="w-4 h-4 animate-spin" aria-hidden />
                            : <Send className="w-4 h-4" aria-hidden />
                        }
                    </button>
                </div>

                {/* Character counter */}
                <p
                    aria-live="polite"
                    className={cn('text-right text-[10px]', isOverLimit ? 'text-red-400' : 'text-gray-600')}
                >
                    {text.length.toLocaleString()} / {QUERY_MAX_LENGTH.toLocaleString()}
                </p>
            </form>
        </div>
    );
}
