import { Component, type ReactNode, type ErrorInfo } from 'react';

interface ErrorBoundaryProps {
    /** Content to render when no error has occurred */
    children: ReactNode;
    /** Optional custom fallback UI to show on error */
    fallback?: ReactNode;
}

interface ErrorBoundaryState {
    hasError: boolean;
    error: Error | null;
}

/**
 * Top-level error boundary to prevent uncaught render errors from crashing the app.
 * Displays a user-friendly fallback UI instead of a white screen of death.
 *
 * @example
 * <ErrorBoundary>
 *   <App />
 * </ErrorBoundary>
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
    constructor(props: ErrorBoundaryProps) {
        super(props);
        this.state = { hasError: false, error: null };
    }

    static getDerivedStateFromError(error: Error): ErrorBoundaryState {
        return { hasError: true, error };
    }

    componentDidCatch(error: Error, errorInfo: ErrorInfo) {
        // Log for debugging; in production, wire this to an error tracking service
        console.error('[ErrorBoundary] Uncaught render error:', error, errorInfo);
    }

    render() {
        if (this.state.hasError) {
            if (this.props.fallback) {
                return this.props.fallback;
            }

            return (
                <div className="min-h-screen flex items-center justify-center bg-background">
                    <div className="text-center space-y-4 p-8 max-w-md">
                        <div className="flex justify-center">
                            <div className="p-4 rounded-full bg-red-500/10 text-red-400">
                                <svg
                                    className="w-10 h-10"
                                    fill="none"
                                    viewBox="0 0 24 24"
                                    stroke="currentColor"
                                    aria-hidden="true"
                                >
                                    <path
                                        strokeLinecap="round"
                                        strokeLinejoin="round"
                                        strokeWidth={1.5}
                                        d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"
                                    />
                                </svg>
                            </div>
                        </div>
                        <h1 className="text-2xl font-bold text-white">Something went wrong</h1>
                        <p className="text-gray-400 text-sm">
                            An unexpected error occurred. Please refresh the page to try again.
                        </p>
                        {this.state.error && (
                            <p className="text-xs text-red-400/70 font-mono bg-red-500/5 rounded-lg px-3 py-2 border border-red-500/10 text-left break-all">
                                {this.state.error.message}
                            </p>
                        )}
                        <button
                            type="button"
                            onClick={() => window.location.reload()}
                            className="px-6 py-2.5 bg-primary/20 hover:bg-primary/30 text-primary border border-primary/30 rounded-xl text-sm font-medium transition-all duration-200 hover:scale-[1.02] cursor-pointer"
                        >
                            Reload Page
                        </button>
                    </div>
                </div>
            );
        }

        return this.props.children;
    }
}
