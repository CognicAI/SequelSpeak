/**
 * Profile Storage Service
 * 
 * Manages connection profiles in browser LocalStorage.
 * Provides CRUD operations with error handling for corrupted data.
 */

import type { ConnectionProfile } from '../types/profile';

const STORAGE_KEY = 'sequel-speak-profiles';

/**
 * Validates if the data structure matches ConnectionProfile interface
 */
function isValidProfile(data: unknown): data is ConnectionProfile {
    if (!data || typeof data !== 'object') return false;

    const profile = data as Record<string, unknown>;

    return (
        typeof profile.id === 'string' &&
        typeof profile.name === 'string' &&
        typeof profile.connectionUrl === 'string' &&
        typeof profile.createdAt === 'string' &&
        (profile.lastUsed === undefined || typeof profile.lastUsed === 'string')
    );
}

/**
 * Safely retrieves and parses profiles from LocalStorage
 * Returns empty array if data is corrupted or missing
 */
function getStoredProfiles(): ConnectionProfile[] {
    try {
        const data = localStorage.getItem(STORAGE_KEY);

        if (!data) {
            return [];
        }

        const parsed = JSON.parse(data);

        if (!Array.isArray(parsed)) {
            console.warn('Invalid profile data structure in LocalStorage. Expected array.');
            return [];
        }

        // Filter out invalid profiles
        const validProfiles = parsed.filter(isValidProfile);

        if (validProfiles.length !== parsed.length) {
            console.warn(`Filtered out ${parsed.length - validProfiles.length} invalid profile(s)`);
        }

        return validProfiles;
    } catch (error) {
        console.error('Failed to retrieve profiles from LocalStorage:', error);
        return [];
    }
}

/**
 * Safely writes profiles to LocalStorage
 */
function setStoredProfiles(profiles: ConnectionProfile[]): boolean {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(profiles));
        return true;
    } catch (error) {
        if (error instanceof Error && error.name === 'QuotaExceededError') {
            console.error('LocalStorage quota exceeded. Cannot save profile.');
        } else {
            console.error('Failed to save profiles to LocalStorage:', error);
        }
        return false;
    }
}

/**
 * Generates a user-friendly profile name from connection URL
 * Format: {user}@{host}/{database}
 */
function generateProfileName(connectionUrl: string): string {
    try {
        // Parse PostgreSQL URL: postgres://user:pass@host:port/database
        const match = connectionUrl.match(/^postgres(?:ql)?:\/\/([^:]+)(?::[^@]*)?@([^:\/]+)(?::\d+)?\/([^?]+)/);

        if (match) {
            const [, user, host, database] = match;
            return `${user}@${host}/${database}`;
        }

        // Fallback to timestamp-based name if parsing fails
        return `Profile ${new Date().toLocaleString()}`;
    } catch {
        return `Profile ${new Date().toLocaleString()}`;
    }
}

/**
 * Saves a new connection profile after successful connection test
 * 
 * @param connectionUrl - Full PostgreSQL connection URL
 * @param name - Optional custom name (auto-generated if not provided)
 * @returns The saved profile, or null if save failed
 */
export function saveProfile(connectionUrl: string, name?: string): ConnectionProfile | null {
    try {
        const profiles = getStoredProfiles();

        const newProfile: ConnectionProfile = {
            id: crypto.randomUUID(),
            name: name || generateProfileName(connectionUrl),
            connectionUrl,
            createdAt: new Date().toISOString(),
        };

        profiles.push(newProfile);

        const success = setStoredProfiles(profiles);
        return success ? newProfile : null;
    } catch (error) {
        console.error('Failed to save profile:', error);
        return null;
    }
}

/**
 * Retrieves all saved connection profiles
 * 
 * @returns Array of profiles (empty if none exist or data is corrupted)
 */
export function getProfiles(): ConnectionProfile[] {
    return getStoredProfiles();
}

/**
 * Retrieves a specific profile by ID
 * 
 * @param id - Profile UUID
 * @returns The profile if found, null otherwise
 */
export function getProfileById(id: string): ConnectionProfile | null {
    const profiles = getStoredProfiles();
    return profiles.find(profile => profile.id === id) || null;
}

/**
 * Deletes a profile by ID
 * 
 * @param id - Profile UUID to delete
 * @returns true if deleted, false if not found or delete failed
 */
export function deleteProfile(id: string): boolean {
    try {
        const profiles = getStoredProfiles();
        const filteredProfiles = profiles.filter(profile => profile.id !== id);

        if (filteredProfiles.length === profiles.length) {
            // Profile not found
            return false;
        }

        return setStoredProfiles(filteredProfiles);
    } catch (error) {
        console.error('Failed to delete profile:', error);
        return false;
    }
}

/**
 * Updates the lastUsed timestamp for a profile
 * 
 * @param id - Profile UUID
 * @returns true if updated, false if not found or update failed
 */
export function updateLastUsed(id: string): boolean {
    try {
        const profiles = getStoredProfiles();
        const profile = profiles.find(p => p.id === id);

        if (!profile) {
            return false;
        }

        profile.lastUsed = new Date().toISOString();

        return setStoredProfiles(profiles);
    } catch (error) {
        console.error('Failed to update lastUsed:', error);
        return false;
    }
}
