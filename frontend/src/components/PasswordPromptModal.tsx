import React, { useState, useEffect, useRef } from 'react';
import { Key, X, AlertCircle, Loader2, ArrowRight } from 'lucide-react';
import { cn } from '../lib/utils';

interface PasswordPromptModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSubmit: (password: string) => Promise<void>;
    profileName: string;
    error?: string | null;
    isLoading?: boolean;
}

export function PasswordPromptModal({
    isOpen,
    onClose,
    onSubmit,
    profileName,
    error = null,
    isLoading = false
}: PasswordPromptModalProps) {
    const [password, setPassword] = useState('');
    const inputRef = useRef<HTMLInputElement>(null);
    const modalRef = useRef<HTMLDivElement>(null);
    const [prevIsOpen, setPrevIsOpen] = useState(isOpen);

    if (isOpen !== prevIsOpen) {
        setPrevIsOpen(isOpen);
        if (isOpen) {
            setPassword('');
        }
    }

    useEffect(() => {
        if (!isOpen) return;

        // Focus after animation
        const timer = setTimeout(() => {
            inputRef.current?.focus();
        }, 100);
        return () => clearTimeout(timer);
    }, [isOpen]);

    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape') {
                onClose();
            }

            if (e.key === 'Tab') {
                const modalElement = modalRef.current;
                if (!modalElement) return;

                const focusableElements = modalElement.querySelectorAll(
                    'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
                );
                
                if (focusableElements.length === 0) return;

                const firstElement = focusableElements[0] as HTMLElement;
                const lastElement = focusableElements[focusableElements.length - 1] as HTMLElement;

                if (e.shiftKey) {
                    if (document.activeElement === firstElement) {
                        lastElement.focus();
                        e.preventDefault();
                    }
                } else {
                    if (document.activeElement === lastElement) {
                        firstElement.focus();
                        e.preventDefault();
                    }
                }
            }
        };

        if (isOpen) {
            window.addEventListener('keydown', handleKeyDown);
        }

        return () => {
            window.removeEventListener('keydown', handleKeyDown);
        };
    }, [isOpen, onClose]);

    if (!isOpen) return null;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (password.trim()) {
            await onSubmit(password);
        }
    };

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
            {/* Backdrop */}
            <div 
                className="absolute inset-0 bg-black/60 backdrop-blur-md animate-in fade-in duration-300"
                onClick={onClose}
            />
            
            {/* Modal */}
            <div 
                ref={modalRef}
                role="dialog"
                aria-modal="true"
                aria-labelledby="modal-title"
                className="relative w-full max-w-md bg-[#0a0a0a] border border-white/10 rounded-2xl shadow-2xl overflow-hidden animate-in zoom-in-95 fade-in duration-300"
            >
                <div className="p-6">
                    {/* Header */}
                    <div className="flex items-center justify-between mb-6">
                        <div className="flex items-center gap-3">
                            <div className="p-2 rounded-lg bg-primary/10 text-primary">
                                <Key className="w-5 h-5" />
                            </div>
                            <div>
                                <h3 id="modal-title" className="text-lg font-bold text-white">Credentials Required</h3>
                                <p className="text-xs text-gray-500">Session expired or not yet authenticated</p>
                            </div>
                        </div>
                        <button 
                            onClick={onClose}
                            className="p-1 rounded-full hover:bg-white/5 text-gray-400 hover:text-white transition-colors"
                            aria-label="Close modal"
                        >
                            <X className="w-5 h-5" />
                        </button>
                    </div>

                    <div className="mb-6">
                        <p className="text-sm text-gray-400 mb-2">
                            Please enter the database password for profile:
                        </p>
                        <div className="px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm font-medium text-white truncate">
                            {profileName}
                        </div>
                    </div>

                    <form onSubmit={handleSubmit} className="space-y-4">
                        <div className="space-y-2">
                            <label htmlFor="db-password" className="text-xs font-medium text-gray-400 ml-1">
                                Database Password
                            </label>
                            <div className="relative">
                                <Key className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-600" />
                                <input
                                    id="db-password"
                                    ref={inputRef}
                                    type="password"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    placeholder="••••••••"
                                    disabled={isLoading}
                                    className={cn(
                                        "w-full pl-11 pr-4 py-3 rounded-xl bg-white/5 border border-white/10 outline-none transition-all duration-300",
                                        "text-sm text-white placeholder:text-gray-700",
                                        "focus:border-primary/50 focus:ring-1 focus:ring-primary/50",
                                        error && "border-red-500/50 focus:border-red-500 focus:ring-red-500/50",
                                        isLoading && "opacity-50 cursor-not-allowed"
                                    )}
                                />
                            </div>
                        </div>

                        {error && (
                            <div className="flex items-center gap-2 p-3 rounded-lg bg-red-500/10 text-red-400 border border-red-500/20 animate-in fade-in slide-in-from-top-1">
                                <AlertCircle className="w-4 h-4 shrink-0" />
                                <span className="text-xs">{error}</span>
                            </div>
                        )}

                        <div className="flex gap-3 pt-2">
                            <button
                                type="button"
                                onClick={onClose}
                                disabled={isLoading}
                                className="flex-1 px-4 py-2.5 rounded-xl border border-white/10 text-gray-400 hover:text-white hover:bg-white/5 transition-all text-sm font-medium"
                            >
                                Cancel
                            </button>
                            <button
                                type="submit"
                                disabled={isLoading || !password.trim()}
                                className={cn(
                                    "flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl font-medium transition-all duration-300",
                                    !password.trim() || isLoading
                                        ? "bg-white/5 text-gray-500 cursor-not-allowed"
                                        : "bg-gradient-to-r from-primary to-secondary text-white hover:opacity-90 shadow-lg shadow-primary/20"
                                )}
                            >
                                {isLoading ? (
                                    <>
                                        <Loader2 className="w-4 h-4 animate-spin" />
                                        <span>Authenticating...</span>
                                    </>
                                ) : (
                                    <>
                                        <span>Connect</span>
                                        <ArrowRight className="w-4 h-4" />
                                    </>
                                )}
                            </button>
                        </div>
                    </form>

                    <div className="mt-6 pt-6 border-t border-white/5">
                        <div className="flex items-start gap-2">
                            <div className="p-1 rounded bg-green-500/10 text-green-400 mt-0.5" aria-hidden="true">
                                <X className="w-3 h-3 rotate-45" /> {/* Small shield replacement */}
                            </div>
                            <p className="text-[10px] text-gray-500 leading-relaxed">
                                <span className="text-green-400 font-medium">Zero-Persistence:</span> This password is only cached in memory for your current session and will never be stored on disk.
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
