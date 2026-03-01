import { useEffect, useState, useRef } from 'react';
import { Wifi, WifiOff, X } from 'lucide-react';
import { cn } from '../lib/utils';
import { CONNECTION_STATUS_MESSAGES } from '../types/api';
import { UI } from '../constants/ui';

export type ConnectionStatus = 'connected' | 'disconnected' | 'unknown';

interface ConnectionStatusBannerProps {
    /** Current connection status */
    status: ConnectionStatus;
    /** Callback when the banner is dismissed */
    onDismiss?: () => void;
    /** Auto-dismiss delay in ms after recovery (default: 3000) */
    autoDismissDelay?: number;
}

/**
 * A notification banner that displays connection status changes.
 * Shows user-friendly messages without technical jargon.
 * Auto-dismisses after connection recovery.
 */
export function ConnectionStatusBanner({
    status,
    onDismiss,
    autoDismissDelay = UI.AUTO_DISMISS_DELAY,
}: ConnectionStatusBannerProps) {
    const [isVisible, setIsVisible] = useState(false);
    const [displayStatus, setDisplayStatus] = useState<ConnectionStatus>(status);

    // Store callback in ref to avoid timer resets on parent re-renders
    const onDismissRef = useRef(onDismiss);
    useEffect(() => {
        onDismissRef.current = onDismiss;
    }, [onDismiss]);

    useEffect(() => {
        if (status === 'disconnected') {
            setDisplayStatus('disconnected');
            setIsVisible(true);
        } else if (status === 'connected') {
            setDisplayStatus('connected');
            setIsVisible(true);
            // Auto-dismiss after delay
            const timer = setTimeout(() => {
                setIsVisible(false);
                onDismissRef.current?.();
            }, autoDismissDelay);
            return () => clearTimeout(timer);
        } else {
            // 'unknown' - hide the banner
            setIsVisible(false);
        }
        return undefined;
    }, [status, autoDismissDelay]);

    if (!isVisible) {
        return null;
    }

    const isDisconnected = displayStatus === 'disconnected';
    const message = isDisconnected
        ? CONNECTION_STATUS_MESSAGES.lost
        : CONNECTION_STATUS_MESSAGES.restored;

    return (
        <div
            role="alert"
            aria-live="polite"
            className={cn(
                "flex items-center gap-3 px-4 py-3 rounded-xl mb-4",
                "animate-in slide-in-from-top-2 fade-in duration-300",
                isDisconnected
                    ? "bg-amber-500/10 border border-amber-500/20 text-amber-400"
                    : "bg-green-500/10 border border-green-500/20 text-green-400"
            )}
        >
            {/* Status Icon */}
            <div className={cn(
                "p-1.5 rounded-full shrink-0",
                isDisconnected ? "bg-amber-500/20" : "bg-green-500/20"
            )}>
                {isDisconnected ? (
                    <WifiOff className="w-4 h-4" />
                ) : (
                    <Wifi className="w-4 h-4" />
                )}
            </div>

            {/* Message */}
            <span className="text-sm flex-1">{message}</span>

            {/* Dismiss Button (only for disconnected state) */}
            {isDisconnected && onDismiss && (
                <button
                    type="button"
                    onClick={() => {
                        setIsVisible(false);
                        onDismiss();
                    }}
                    className="p-1 rounded-full hover:bg-white/10 transition-colors shrink-0"
                    aria-label="Dismiss notification"
                >
                    <X className="w-4 h-4" />
                </button>
            )}
        </div>
    );
}
