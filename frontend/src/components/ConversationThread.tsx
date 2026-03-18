/**
 * ConversationThread — scrollable list of chat bubbles.
 *
 * Auto-scrolls to the bottom whenever new messages arrive.
 * Renders the transient "processing" bubble for the placeholder message.
 */

import { useEffect, useRef } from 'react';
import { ConversationMessage } from './ConversationMessage';
import type { ConversationMessage as IMessage } from '../types/conversation';
import { cn } from '../lib/utils';
import { MessageSquare } from 'lucide-react';

const PROCESSING_PLACEHOLDER_ID = '__processing__';

interface ConversationThreadProps {
    messages: IMessage[];
    className?: string;
}

export function ConversationThread({ messages, className }: ConversationThreadProps) {
    const bottomRef = useRef<HTMLDivElement>(null);

    // Auto-scroll to bottom on new messages
    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages.length]);

    if (messages.length === 0) {
        return (
            <div className={cn('flex-1 flex flex-col items-center justify-center gap-3 py-16 px-8 text-center', className)}>
                <div className="w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center">
                    <MessageSquare className="w-7 h-7 text-primary/60" aria-hidden />
                </div>
                <p className="text-gray-500 text-sm max-w-xs">
                    Select a database and ask anything — <span className="text-gray-400">e.g. &ldquo;Show me total revenue by month for Q1&rdquo;</span>
                </p>
            </div>
        );
    }

    return (
        <div
            className={cn('flex-1 overflow-y-auto flex flex-col gap-3 py-4 scroll-smooth', className)}
            aria-label="Conversation thread"
            aria-live="polite"
            aria-atomic="false"
            aria-relevant="additions"
        >
            {messages.map((msg) => (
                <ConversationMessage
                    key={msg.id}
                    message={msg}
                    isProcessing={msg.id === PROCESSING_PLACEHOLDER_ID}
                />
            ))}
            <div ref={bottomRef} aria-hidden />
        </div>
    );
}
