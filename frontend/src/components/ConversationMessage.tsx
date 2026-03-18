/**
 * ConversationMessage — renders a single chat bubble.
 *
 * Role / Kind matrix:
 *   user  / text          → right-aligned primary gradient bubble
 *   assistant / text      → left-aligned glass bubble (also used for "processing…")
 *   assistant / clarification → left-aligned question bubble with subtle highlight
 *   assistant / result    → full-width SQL result card
 *   system / error        → centred amber/red warning strip
 *   system / text         → centred muted info strip
 */

import { AlertTriangle, CheckCircle2, Database, MessageSquare } from 'lucide-react';
import { cn } from '../lib/utils';
import type { ConversationMessage as IConversationMessage } from '../types/conversation';

interface ConversationMessageProps {
    message: IConversationMessage;
    /** True when this is the transient "…" processing placeholder. */
    isProcessing?: boolean;
}

export function ConversationMessage({ message, isProcessing = false }: ConversationMessageProps) {
    const { role, kind, content } = message;

    // ── System messages (error / info notices)
    if (role === 'system') {
        const isError = kind === 'error';
        return (
            <div className="flex justify-center px-4 py-1">
                <div
                    className={cn(
                        'flex items-start gap-2 rounded-xl px-3 py-2 text-xs max-w-[80%]',
                        isError
                            ? 'bg-red-500/10 border border-red-500/20 text-red-400'
                            : 'bg-white/5 border border-white/10 text-gray-400',
                    )}
                    role={isError ? 'alert' : 'status'}
                >
                    {isError
                        ? <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" aria-hidden />
                        : <MessageSquare className="w-3.5 h-3.5 shrink-0 mt-0.5" aria-hidden />
                    }
                    <span>{content}</span>
                </div>
            </div>
        );
    }

    // ── User messages
    if (role === 'user') {
        return (
            <div className="flex justify-end px-4">
                <div className="max-w-[75%] rounded-2xl rounded-tr-sm px-4 py-2.5 bg-gradient-to-br from-primary to-secondary text-white text-sm shadow-lg shadow-primary/20">
                    {content}
                </div>
            </div>
        );
    }

    // ── Assistant: processing placeholder (animated dots)
    if (isProcessing) {
        return (
            <div className="flex justify-start px-4">
                <div className="rounded-2xl rounded-tl-sm px-4 py-3 bg-white/5 border border-white/10 backdrop-blur-sm">
                    <span className="flex items-center gap-1" aria-label="Processing" role="status">
                        {[0, 1, 2].map(i => (
                            <span
                                key={i}
                                className="w-1.5 h-1.5 rounded-full bg-primary/70 animate-bounce"
                                style={{ animationDelay: `${i * 150}ms` }}
                            />
                        ))}
                    </span>
                </div>
            </div>
        );
    }

    // ── Assistant: result card (SQL)
    if (kind === 'result') {
        return (
            <div className="px-4 w-full">
                <div className="rounded-2xl rounded-tl-sm border border-white/10 bg-white/5 backdrop-blur-sm overflow-hidden">
                    <div className="flex items-center gap-2 px-4 py-2.5 border-b border-white/10 bg-white/5">
                        <Database className="w-4 h-4 text-primary" aria-hidden />
                        <span className="text-xs font-medium text-gray-300">Generated SQL</span>
                    </div>
                    <pre className="p-4 text-xs text-green-300 font-mono overflow-x-auto whitespace-pre-wrap">
                        {content}
                    </pre>
                    {message.metadata?.execution_result !== undefined && (
                        <div className="px-4 py-3 border-t border-white/10 text-xs text-gray-400">
                            {(() => {
                                try {
                                    const rows = message.metadata.execution_result as { rows?: unknown[]; row_count?: number };
                                    if (rows?.rows && Array.isArray(rows.rows) && rows.rows.length > 0) {
                                        const data = rows.rows as Record<string, unknown>[];
                                        const cols = Object.keys(data[0]);
                                        return (
                                            <div className="overflow-x-auto">
                                                <table className="w-full text-left text-xs">
                                                    <thead>
                                                        <tr>
                                                            {cols.map(c => (
                                                                <th key={c} className="px-2 py-1 text-gray-400 font-medium border-b border-white/10">{c}</th>
                                                            ))}
                                                        </tr>
                                                    </thead>
                                                    <tbody>
                                                        {data.slice(0, 50).map((row, i) => (
                                                            <tr key={i} className="border-b border-white/5 hover:bg-white/5">
                                                                {cols.map(c => (
                                                                    <td key={c} className="px-2 py-1 text-gray-300">{String(row[c] ?? '')}</td>
                                                                ))}
                                                            </tr>
                                                        ))}
                                                    </tbody>
                                                </table>
                                                {rows.row_count && rows.row_count > 50 && (
                                                    <p className="mt-2 text-gray-500">{rows.row_count} rows total — showing first 50</p>
                                                )}
                                            </div>
                                        );
                                    }
                                } catch {}
                                return <span>No result rows.</span>;
                            })()}
                        </div>
                    )}
                </div>
            </div>
        );
    }

    // ── Assistant: clarification question bubble (styled to stand out slightly)
    if (kind === 'clarification') {
        return (
            <div className="flex justify-start px-4">
                <div className="max-w-[80%] rounded-2xl rounded-tl-sm px-4 py-3 bg-amber-500/10 border border-amber-500/20 text-amber-200 text-sm">
                    <p className="text-xs font-medium text-amber-400 mb-1">Clarification needed</p>
                    <p>{content}</p>
                </div>
            </div>
        );
    }

    // ── Assistant: plain text (narrative + check mark for complete)
    const isComplete = message.metadata?.is_complete;
    return (
        <div className="flex justify-start items-start gap-2 px-4">
            <div className="w-6 h-6 shrink-0 mt-0.5 rounded-full bg-primary/10 flex items-center justify-center">
                {isComplete
                    ? <CheckCircle2 className="w-3.5 h-3.5 text-green-400" aria-hidden />
                    : <MessageSquare className="w-3.5 h-3.5 text-primary" aria-hidden />
                }
            </div>
            <div className="max-w-[80%] rounded-2xl rounded-tl-sm px-4 py-2.5 bg-white/5 border border-white/10 backdrop-blur-sm text-sm text-gray-200 leading-relaxed">
                {content}
            </div>
        </div>
    );
}
