/**
 * Profile Storage Service
 * 
 * Manages connection profiles in browser LocalStorage.
 * Provides CRUD operations with error handling for corrupted data.
 */

import type { ConnectionProfile } from '../types/profile';

const STORAGE_KEY = 'sequel-speak-profiles';

/**
 * Result of saving a profile, indicating whether it was created or updated
 */
export interface SaveProfileResult {
    profile: ConnectionProfile;
    isNew: boolean; // true if newly created, false if updated existing
}

/**
 * Validates if the data structure matches ConnectionProfile interface
 */
function isValidProfile(data: unknown): data is ConnectionProfile {
    if (!data || typeof data !== 'object') return false;

    const profile = data as Record<string, unknown>;

    return (
        typeof profile.id === 'string' &&
        typeof profile.name === 'string' &&
        typeof profile.host === 'string' &&
        typeof profile.port === 'string' &&
        typeof profile.username === 'string' &&
        typeof profile.database === 'string' &&
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
 * Parses a PostgreSQL connection URL and extracts connection fields
 * Password is intentionally excluded for security
 * 
 * Handles:
 * - URL-encoded special characters in username/password
 * - IPv6 addresses in brackets [::1]
 * - Query parameters (stripped from database name)
 * - Both postgres:// and postgresql:// schemes
 * 
 * @param connectionUrl - Full PostgreSQL connection URL
 * @returns Parsed connection fields without password, or null if parsing fails
 */
function parseConnectionUrl(connectionUrl: string): Omit<ConnectionProfile, 'id' | 'name' | 'createdAt' | 'lastUsed'> | null {
    try {
        // Use URL API for robust parsing
        // Replace postgres:// with http:// temporarily for URL parsing
        const urlToParse = connectionUrl.replace(/^postgres(ql)?:\/\//, 'http://');
        const url = new URL(urlToParse);

        // Extract and decode username (URL API handles decoding automatically)
        const username = url.username;
        if (!username) {
            console.error('Username is required in connection URL');
            return null;
        }

        // Extract host (handles both regular hostnames and IPv6 in brackets)
        let host = url.hostname;
        if (!host) {
            console.error('Host is required in connection URL');
            return null;
        }

        // Extract port (default to 5432 if not specified)
        const port = url.port || '5432';

        // Extract database name (pathname starts with /, remove it and any query params)
        const pathname = url.pathname.substring(1); // Remove leading /
        const database = pathname.split('?')[0]; // Remove query parameters if present

        if (!database) {
            console.error('Database name is required in connection URL');
            return null;
        }

        return {
            host,
            port,
            username,
            database,
        };
    } catch (error) {
        console.error('Error parsing connection URL:', error);

        // Fallback to regex for edge cases where URL API fails
        try {
            // Enhanced regex that handles more cases
            // postgres://username[:password]@host:port/database
            // Password is optional to handle URLs without passwords
            // Supports IPv6: postgres://user:pass@[::1]:5432/db
            const match = connectionUrl.match(
                /^postgres(?:ql)?:\/\/([^:@]+)(?::([^@]*))?@(\[[\da-fA-F:]+\]|[^:\/]+)(?::(\d+))?\/([^?]+)/
            );

            if (!match) {
                console.error('Failed to parse connection URL with fallback regex');
                return null;
            }

            const [, encodedUsername, /* password (optional) */, host, port = '5432', database] = match;

            // Decode URL-encoded username
            const username = decodeURIComponent(encodedUsername);

            // Remove brackets from IPv6 addresses if present
            const cleanHost = host.startsWith('[') && host.endsWith(']')
                ? host.slice(1, -1)
                : host;

            return {
                host: cleanHost,
                port,
                username,
                database,
            };
        } catch (fallbackError) {
            console.error('Fallback parsing also failed:', fallbackError);
            return null;
        }
    }
}

/**
 * Generates a user-friendly profile name from connection fields
 * Format: {username}@{host}/{database}
 */
function generateProfileName(username: string, host: string, database: string): string {
    return `${username}@${host}/${database}`;
}

/**
 * Checks if two profiles have the same connection details (excluding password)
 */
function isSameConnection(profile: ConnectionProfile, fields: { host: string; port: string; username: string; database: string }): boolean {
    return (
        profile.host === fields.host &&
        profile.port === fields.port &&
        profile.username === fields.username &&
        profile.database === fields.database
    );
}

/**
 * Saves a new connection profile after successful connection test
 * 
 * SECURITY: Only non-sensitive connection metadata is stored.
 * Password is NEVER stored in LocalStorage. Users must re-enter
 * passwords when using saved profiles.
 * 
 * @param connectionUrl - Full PostgreSQL connection URL (password will be excluded from storage)
 * @param name - Optional custom name (auto-generated if not provided)
 * @returns SaveProfileResult with profile and isNew flag, or null if save failed
 */
export function saveProfile(connectionUrl: string, name?: string): SaveProfileResult | null {
    try {
        const parsedFields = parseConnectionUrl(connectionUrl);

        if (!parsedFields) {
            console.error('Cannot save profile: invalid connection URL');
            return null;
        }

        const profiles = getStoredProfiles();

        // Check if a profile with the same connection details already exists
        const existingProfile = profiles.find(p => isSameConnection(p, parsedFields));

        if (existingProfile) {
            // Update the lastUsed timestamp instead of creating a duplicate
            existingProfile.lastUsed = new Date().toISOString();

            // Update the profile name if a custom name was provided
            if (name && name !== existingProfile.name) {
                existingProfile.name = name;
            }

            const success = setStoredProfiles(profiles);
            return success ? { profile: existingProfile, isNew: false } : null;
        }

        // Create new profile if it doesn't exist
        const newProfile: ConnectionProfile = {
            id: crypto.randomUUID(),
            name: name || generateProfileName(parsedFields.username, parsedFields.host, parsedFields.database),
            host: parsedFields.host,
            port: parsedFields.port,
            username: parsedFields.username,
            database: parsedFields.database,
            createdAt: new Date().toISOString(),
        };

        profiles.push(newProfile);

        const success = setStoredProfiles(profiles);
        return success ? { profile: newProfile, isNew: true } : null;
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
