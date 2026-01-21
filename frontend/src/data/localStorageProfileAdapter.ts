/**
 * LocalStorage Profile Adapter
 * 
 * Adapter wrapper around profileStorage service that implements the ProfileAdapter interface.
 * This allows the useProfileSelection hook to work with LocalStorage-persisted profiles.
 */

import type { ConnectionProfile } from '../types/profile';
import { getProfiles, getProfileById } from '../services/profileStorage';

/**
 * Profile Adapter Interface
 * Abstraction for profile data sources.
 */
export interface ProfileAdapter {
    /** Get all available connection profiles */
    getProfiles(): ConnectionProfile[];
    /** Get a profile by its ID */
    getProfileById(id: string): ConnectionProfile | undefined;
}

/**
 * LocalStorage Profile Adapter Implementation
 * Wraps the profileStorage service functions.
 */
class LocalStorageProfileAdapter implements ProfileAdapter {
    /**
     * Returns all available connection profiles from LocalStorage.
     * Returns an empty array if no profiles exist or data is corrupted.
     */
    getProfiles(): ConnectionProfile[] {
        return getProfiles();
    }

    /**
     * Returns a profile by its ID from LocalStorage.
     * Returns undefined if profile not found.
     */
    getProfileById(id: string): ConnectionProfile | undefined {
        const profile = getProfileById(id);
        return profile || undefined;
    }
}

/**
 * Singleton instance of the LocalStorage adapter.
 * UI components should import and use this instance.
 */
export const localStorageProfileAdapter = new LocalStorageProfileAdapter();
