/**
 * useProfileSelection Hook
 * 
 * Manages connection profile selection state.
 * Decoupled from persistence - uses ProfileAdapter interface.
 * 
 * Features:
 * - Explicit selection state (activeProfileId)
 * - Defensive error handling
 * - Support for rapid profile switching
 */

import { useState, useCallback, useMemo, useRef, useEffect } from 'react';
import type { ConnectionProfile } from '../types/profile';
import { localStorageProfileAdapter, type ProfileAdapter } from '../data/localStorageProfileAdapter';



interface ProfileSelectionState {
    activeProfileId: string | null;
    profiles: ConnectionProfile[];
    isLoading: boolean;
    error: string | null;
}

interface UseProfileSelectionOptions {
    /** Optional custom adapter (defaults to localStorageProfileAdapter) */
    adapter?: ProfileAdapter;
    /** Callback when a profile is selected */
    onProfileSelect?: (profile: ConnectionProfile) => void;
    /** Callback when profile is cleared/deselected */
    onProfileClear?: () => void;
}

interface UseProfileSelectionReturn extends ProfileSelectionState {
    /** Select a profile by ID */
    selectProfile: (profileId: string) => void;
    /** Clear the current selection */
    clearSelection: () => void;
    /** Get connection fields for the active profile (without password) */
    getActiveConnectionFields: () => Omit<ConnectionProfile, 'id' | 'name' | 'createdAt' | 'lastUsed'> | null;
    /** Get the currently active profile */
    activeProfile: ConnectionProfile | null;
    /** Check if a specific profile is active */
    isProfileActive: (profileId: string) => boolean;
    /** Refresh profiles from adapter */
    refreshProfiles: () => void;
}

/**
 * Custom hook for managing connection profile selection.
 */
export function useProfileSelection(options: UseProfileSelectionOptions = {}): UseProfileSelectionReturn {
    const {
        adapter = localStorageProfileAdapter,
        onProfileSelect,
        onProfileClear,
    } = options;

    // State
    const [activeProfileId, setActiveProfileId] = useState<string | null>(null);
    const [profiles, setProfiles] = useState<ConnectionProfile[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // Ref to track latest selection for handling rapid switches
    const latestSelectionRef = useRef<string | null>(null);

    /**
     * Load profiles from adapter.
     * Defensive: handles adapter failures gracefully.
     */
    const loadProfiles = useCallback(() => {
        setIsLoading(true);
        setError(null);

        try {
            const loadedProfiles = adapter.getProfiles();

            // Defensive: ensure we have an array
            if (!Array.isArray(loadedProfiles)) {
                throw new Error('Invalid profiles data received');
            }

            setProfiles(loadedProfiles);

            // Clear active profile if it no longer exists
            if (activeProfileId && !loadedProfiles.some(p => p.id === activeProfileId)) {
                setActiveProfileId(null);
                latestSelectionRef.current = null;
            }
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : 'Failed to load profiles';
            setError(errorMessage);
            setProfiles([]);
        } finally {
            setIsLoading(false);
        }
    }, [adapter, activeProfileId]);

    // Load profiles on mount
    useEffect(() => {
        loadProfiles();
    }, [loadProfiles]);

    /**
     * Select a profile by ID.
     * Handles rapid switching by tracking latest selection.
     */
    const selectProfile = useCallback((profileId: string) => {
        // Defensive: validate input
        if (!profileId || typeof profileId !== 'string') {
            console.warn('Invalid profile ID provided to selectProfile');
            return;
        }

        // Track this as the latest selection (for rapid switching)
        latestSelectionRef.current = profileId;

        // Find the profile
        const profile = profiles.find(p => p.id === profileId);

        if (!profile) {
            console.warn(`Profile with ID "${profileId}" not found`);
            return;
        }

        // Only update if this is still the latest selection
        // This handles rapid switching scenarios
        if (latestSelectionRef.current === profileId) {
            setActiveProfileId(profileId);
            onProfileSelect?.(profile);
        }
    }, [profiles, onProfileSelect]);

    /**
     * Clear the current profile selection.
     */
    const clearSelection = useCallback(() => {
        latestSelectionRef.current = null;
        setActiveProfileId(null);
        onProfileClear?.();
    }, [onProfileClear]);

    /**
     * Get the currently active profile.
     * Memoized to prevent unnecessary recalculations.
     */
    const activeProfile = useMemo(() => {
        if (!activeProfileId) return null;
        return profiles.find(p => p.id === activeProfileId) ?? null;
    }, [activeProfileId, profiles]);

    /**
     * Get connection fields for the active profile.
     * Returns null if no profile is active.
     */
    const getActiveConnectionFields = useCallback((): Omit<ConnectionProfile, 'id' | 'name' | 'createdAt' | 'lastUsed'> | null => {
        if (!activeProfile) return null;

        // Return connection fields without metadata (password is never stored)
        return {
            host: activeProfile.host,
            port: activeProfile.port,
            username: activeProfile.username,
            database: activeProfile.database,
        };
    }, [activeProfile]);

    /**
     * Check if a specific profile is currently active.
     */
    const isProfileActive = useCallback((profileId: string): boolean => {
        return activeProfileId === profileId;
    }, [activeProfileId]);

    /**
     * Refresh profiles from adapter.
     */
    const refreshProfiles = useCallback(() => {
        loadProfiles();
    }, [loadProfiles]);

    return {
        // State
        activeProfileId,
        profiles,
        isLoading,
        error,
        activeProfile,

        // Actions
        selectProfile,
        clearSelection,
        getActiveConnectionFields,
        isProfileActive,
        refreshProfiles,
    };
}
