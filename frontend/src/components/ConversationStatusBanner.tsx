/**
 * ConversationStatusBanner — thin strip at the top of the chat showing
 * the current conversation status with an icon and brief label.
 */

import { Loader2, CheckCircle2, AlertCircle, MessageSquare, ShieldAlert } from 'lucide-react';
import { cn } from '../lib/utils';
import type { ConversationStatus } from '../types/conversation';

interface ConversationStatusBannerProps {
    status: ConversationStatus;
    stage?: string | null;
    needsReauth?: boolean;
    className?: string;
}

const STATUS_CONFIG: Record<ConversationStatus, {
    icon: React.ReactNode;
    label: string;
    classes: string;
}> = {
    idle: {
        icon: <MessageSquare className="w-3.5 h-3.5" aria-hidden />,
        label: 'Ask your database anything in plain English',
        classes: 'text-gray-500 bg-transparent border-transparent',
    },
    processing: {
        icon: <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden />,
        label: 'Processing…',
        classes: 'text-primary bg-primary/5 border-primary/20',
    },
    clarification_needed: {
        icon: <MessageSquare className="w-3.5 h-3.5" aria-hidden />,
        label: 'Clarification needed — please answer below',
        classes: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
    },
    complete: {
        icon: <CheckCircle2 className="w-3.5 h-3.5" aria-hidden />,
        label: 'Query complete',
        classes: 'text-green-400 bg-green-500/10 border-green-500/20',
    },
    error: {
        icon: <AlertCircle className="w-3.5 h-3.5" aria-hidden />,
        label: 'An error occurred',
        classes: 'text-red-400 bg-red-500/10 border-red-500/20',
    },
};

export function ConversationStatusBanner({
    status,
    stage,
    needsReauth = false,
    className,
}: ConversationStatusBannerProps) {
    // Credential re-auth overrides the status display
    if (needsReauth) {
        return (
            <div
                className={cn(
                    'flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-medium border',
                    'text-amber-400 bg-amber-500/10 border-amber-500/20',
                    className,
                )}
                role="status"
                aria-live="polite"
            >
                <ShieldAlert className="w-3.5 h-3.5 shrink-0" aria-hidden />
                <span>Credentials expired — re-authenticate to resume</span>
            </div>
        );
    }

    const config = STATUS_CONFIG[status];
    const stageLabel = status === 'processing' && stage ? ` — ${stage.replace(/_/g, ' ')}` : '';

    return (
        <div
            className={cn(
                'flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-medium border transition-all duration-300',
                config.classes,
                className,
            )}
            role="status"
            aria-live="polite"
        >
            {config.icon}
            <span>{config.label}{stageLabel}</span>
        </div>
    );
}
