/**
 * ProfileSelector Component
 * 
 * Dropdown UI for selecting saved connection profiles.
 * 
 * Features:
 * - Lists all available profiles
 * - Visual indication of active profile
 * - Graceful handling of edge cases (empty list, loading, errors)
 * - Accessible keyboard navigation
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import { ChevronDown, User2, Check, AlertCircle, FolderOpen, X } from 'lucide-react';
import { cn } from '../lib/utils';
import type { ConnectionProfile } from '../types/profile';

interface ProfileSelectorProps {
    /** List of available profiles */
    profiles: ConnectionProfile[];
    /** Currently active profile ID */
    activeProfileId: string | null;
    /** Whether profiles are loading */
    isLoading?: boolean;
    /** Error message if profile loading failed */
    error?: string | null;
    /** Callback when a profile is selected */
    onProfileSelect: (profileId: string) => void;
    /** Callback when selection is cleared */
    onClearSelection?: () => void;
    /** Whether the selector is disabled */
    disabled?: boolean;
    /** Additional CSS classes */
    className?: string;
}

export function ProfileSelector({
    profiles,
    activeProfileId,
    isLoading = false,
    error = null,
    onProfileSelect,
    onClearSelection,
    disabled = false,
    className,
}: ProfileSelectorProps) {
    const [isOpen, setIsOpen] = useState(false);
    const dropdownRef = useRef<HTMLDivElement>(null);
    const buttonRef = useRef<HTMLButtonElement>(null);

    // Find active profile for display
    const activeProfile = activeProfileId
        ? profiles.find(p => p.id === activeProfileId)
        : null;

    // Handle outside clicks to close dropdown
    useEffect(() => {
        function handleClickOutside(event: MouseEvent) {
            if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
                setIsOpen(false);
            }
        }

        if (isOpen) {
            document.addEventListener('mousedown', handleClickOutside);
            return () => document.removeEventListener('mousedown', handleClickOutside);
        }
    }, [isOpen]);

    // Handle keyboard navigation
    const handleKeyDown = useCallback((event: React.KeyboardEvent) => {
        switch (event.key) {
            case 'Escape':
                setIsOpen(false);
                buttonRef.current?.focus();
                break;
            case 'Enter':
            case ' ':
                if (!isOpen) {
                    event.preventDefault();
                    setIsOpen(true);
                }
                break;
            case 'ArrowDown':
                event.preventDefault();
                if (!isOpen) {
                    setIsOpen(true);
                }
                break;
        }
    }, [isOpen]);

    // Handle profile selection
    const handleSelect = useCallback((profileId: string) => {
        onProfileSelect(profileId);
        setIsOpen(false);
        buttonRef.current?.focus();
    }, [onProfileSelect]);

    // Handle clear selection
    const handleClear = useCallback((event: React.MouseEvent) => {
        event.stopPropagation();
        onClearSelection?.();
    }, [onClearSelection]);

    // Render loading state
    if (isLoading) {
        return (
            <div className={cn("w-full", className)}>
                <div className="flex items-center gap-2 px-3 py-2.5 bg-white/5 rounded-lg border border-white/10 animate-pulse">
                    <div className="w-4 h-4 bg-white/10 rounded" />
                    <div className="flex-1 h-4 bg-white/10 rounded" />
                    <div className="w-4 h-4 bg-white/10 rounded" />
                </div>
            </div>
        );
    }

    // Render error state
    if (error) {
        return (
            <div className={cn("w-full", className)}>
                <div className="flex items-center gap-2 px-3 py-2.5 bg-red-500/10 rounded-lg border border-red-500/20 text-red-400">
                    <AlertCircle className="w-4 h-4 shrink-0" />
                    <span className="text-xs">{error}</span>
                </div>
            </div>
        );
    }

    // Render empty state
    if (profiles.length === 0) {
        return (
            <div className={cn("w-full", className)}>
                <div className="flex items-center gap-2 px-3 py-2.5 bg-white/5 rounded-lg border border-white/10 text-gray-500">
                    <FolderOpen className="w-4 h-4 shrink-0" />
                    <span className="text-xs">No saved profiles</span>
                </div>
            </div>
        );
    }

    return (
        <div
            ref={dropdownRef}
            className={cn("relative w-full", className)}
            onKeyDown={handleKeyDown}
        >
            {/* Trigger Button */}
            <button
                ref={buttonRef}
                type="button"
                onClick={() => !disabled && setIsOpen(!isOpen)}
                disabled={disabled}
                aria-haspopup="listbox"
                aria-expanded={isOpen}
                aria-label={activeProfile ? `Selected profile: ${activeProfile.name}` : 'Select a connection profile'}
                className={cn(
                    "w-full flex items-center gap-2 px-3 py-2.5 rounded-lg border transition-all duration-200",
                    "bg-white/5 hover:bg-white/10",
                    isOpen
                        ? "border-primary/50 ring-1 ring-primary/50"
                        : "border-white/10 hover:border-white/20",
                    disabled && "opacity-50 cursor-not-allowed hover:bg-white/5",
                    activeProfile && "border-green-500/30 bg-green-500/5"
                )}
            >
                {/* Profile Icon */}
                <User2 className={cn(
                    "w-4 h-4 shrink-0 transition-colors",
                    activeProfile ? "text-green-400" : "text-gray-500"
                )} />

                {/* Profile Name or Placeholder */}
                <span className={cn(
                    "flex-1 text-left text-sm truncate",
                    activeProfile ? "text-white" : "text-gray-500"
                )}>
                    {activeProfile ? activeProfile.name : 'Select a profile...'}
                </span>

                {/* Active Indicator & Clear Button */}
                {activeProfile && onClearSelection && (
                    <div
                        role="button"
                        tabIndex={0}
                        onClick={handleClear}
                        onKeyDown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault();
                                handleClear(e as any);
                            }
                        }}
                        className="p-0.5 rounded hover:bg-white/10 transition-colors cursor-pointer"
                        aria-label="Clear selection"
                    >
                        <X className="w-3 h-3 text-gray-400 hover:text-white" />
                    </div>
                )}

                {/* Chevron */}
                <ChevronDown className={cn(
                    "w-4 h-4 shrink-0 text-gray-500 transition-transform duration-200",
                    isOpen && "rotate-180"
                )} />
            </button>

            {/* Dropdown Menu */}
            {isOpen && (
                <div
                    className={cn(
                        "absolute z-50 w-full mt-1 py-1 rounded-lg border border-white/10",
                        "bg-background/95 backdrop-blur-xl shadow-xl",
                        "animate-in fade-in slide-in-from-top-2 duration-200"
                    )}
                    role="listbox"
                    aria-label="Connection profiles"
                >
                    {profiles.map((profile) => {
                        const isActive = profile.id === activeProfileId;

                        return (
                            <button
                                key={profile.id}
                                type="button"
                                role="option"
                                aria-selected={isActive}
                                onClick={() => handleSelect(profile.id)}
                                className={cn(
                                    "w-full flex items-center gap-3 px-3 py-2.5 text-left transition-colors",
                                    "hover:bg-white/10 focus:bg-white/10 focus:outline-none",
                                    isActive && "bg-green-500/10"
                                )}
                            >
                                {/* Selection Indicator */}
                                <div className={cn(
                                    "w-5 h-5 rounded-full border-2 flex items-center justify-center shrink-0 transition-colors",
                                    isActive
                                        ? "border-green-500 bg-green-500"
                                        : "border-white/20"
                                )}>
                                    {isActive && (
                                        <Check className="w-3 h-3 text-black stroke-[3]" />
                                    )}
                                </div>

                                {/* Profile Info */}
                                <div className="flex-1 min-w-0">
                                    <div className={cn(
                                        "text-sm font-medium truncate",
                                        isActive ? "text-green-400" : "text-white"
                                    )}>
                                        {profile.name}
                                    </div>
                                    <div className="text-xs text-gray-500 truncate">
                                        {profile.host}:{profile.port}/{profile.database}
                                    </div>
                                </div>
                            </button>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
