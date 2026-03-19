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
import { useAuth } from '@clerk/clerk-react';
import type { ConnectionProfile } from '../types/profile';
import { apiProfileAdapter, type ProfileAdapter } from '../data/apiProfileAdapter';
import { deleteProfile as deleteProfileFromBackend, updateProfileName } from '../services/profileStorage';



interface ProfileSelectionState {
    activeProfileId: string | null;
    profiles: ConnectionProfile[];
    isLoading: boolean;
    error: string | null;
}

interface UseProfileSelectionOptions {
    /** Optional custom adapter (defaults to apiProfileAdapter) */
    adapter?: ProfileAdapter;
    /** Callback when a profile is selected */
    onProfileSelect?: (profile: ConnectionProfile) => void;
    /** Callback when profile is cleared/deselected */
    onProfileClear?: () => void;
    /** Callback when a profile is deleted */
    onProfileDelete?: (profileId: string) => void;
    /** Callback when a profile is renamed */
    onProfileRename?: (profileId: string, newName: string) => void;
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
    /** Delete a profile by ID */
    deleteProfile: (profileId: string) => Promise<boolean>;
    /** Rename a profile */
    renameProfile: (profileId: string, newName: string) => Promise<boolean>;
}

/**
 * Custom hook for managing connection profile selection.
 */
export function useProfileSelection(options: UseProfileSelectionOptions = {}): UseProfileSelectionReturn {
    const {
        adapter = apiProfileAdapter,
        onProfileSelect,
        onProfileClear,
        onProfileDelete,
        onProfileRename,
    } = options;

    const { getToken, isSignedIn } = useAuth();

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
    const loadProfiles = useCallback(async () => {
        if (!isSignedIn) {
            setProfiles([]);
            setIsLoading(false);
            return;
        }

        setIsLoading(true);
        setError(null);

        try {
            const token = await getToken();
            if (!token) throw new Error("No token available");
            const loadedProfiles = await adapter.getProfiles(token);

            // Defensive: ensure we have an array
            if (!Array.isArray(loadedProfiles)) {
                throw new Error('Invalid profiles data received');
            }

            setProfiles(loadedProfiles);
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : 'Failed to load profiles';
            setError(errorMessage);
            setProfiles([]);
        } finally {
            setIsLoading(false);
        }
        // Only depends on adapter — removing activeProfileId prevents reload loops (section 2.1)
    }, [adapter, getToken, isSignedIn]);

    // Separately handle the case where the active profile is removed from the list.
    // Keeping this in a dedicated effect avoids re-creating loadProfiles on every selection change.
    useEffect(() => {
        if (activeProfileId && !profiles.some(p => p.id === activeProfileId)) {
            setActiveProfileId(null);
            latestSelectionRef.current = null;
        }
    }, [activeProfileId, profiles]);

    // Load profiles on mount
    useEffect(() => {
        if (isSignedIn) {
            loadProfiles();
        }
    }, [loadProfiles, isSignedIn]);

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

    /**
     * Delete a profile by ID.
     * Clears selection if the deleted profile was active.
     */
    const deleteProfile = useCallback(async (profileId: string): Promise<boolean> => {
        // Defensive: validate input
        if (!profileId || typeof profileId !== 'string') {
            console.warn('Invalid profile ID provided to deleteProfile');
            return false;
        }

        // Attempt to delete from backend
        const token = await getToken();
        if(!token) return false;
        const success = await deleteProfileFromBackend(profileId, token);

        if (success) {
            // Clear selection if the deleted profile was active
            if (activeProfileId === profileId) {
                setActiveProfileId(null);
                latestSelectionRef.current = null;
                onProfileClear?.();
            }

            // Refresh profiles to update the list
            await loadProfiles();

            // Notify parent component
            onProfileDelete?.(profileId);
        }

        return success;
    }, [activeProfileId, loadProfiles, onProfileClear, onProfileDelete, getToken]);

    /**
     * Rename a profile.
     */
    const renameProfile = useCallback(async (profileId: string, newName: string): Promise<boolean> => {
        // Defensive: validate input
        if (!profileId || typeof profileId !== 'string') {
            console.warn('Invalid profile ID provided to renameProfile');
            return false;
        }

        if (!newName || typeof newName !== 'string' || newName.trim().length === 0) {
            console.warn('Invalid name provided to renameProfile');
            return false;
        }

        // Attempt to update name in backend
        const token = await getToken();
        if(!token) return false;
        const success = await updateProfileName(profileId, newName, token);

        if (success) {
            // Refresh profiles to update the list
            await loadProfiles();

            // Notify parent component
            onProfileRename?.(profileId, newName);
        }

        return success;
    }, [loadProfiles, onProfileRename, getToken]);

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
        deleteProfile,
        renameProfile,
    };
}
