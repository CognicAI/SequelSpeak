/**
 * Profile Storage Service
 * 
 * Manages connection profiles in the backend API (migrated from LocalStorage).
 */

import type { ConnectionProfile } from '../types/profile';
import { apiClient } from './api/client';

export interface SaveProfileResult {
    profile: ConnectionProfile;
    isNew: boolean;
}

/**
 * Parses a PostgreSQL connection URL and extracts connection fields
 */
function parseConnectionUrl(connectionUrl: string): { host: string; port: string; username: string; database: string; password?: string } | null {
    try {
        const urlToParse = connectionUrl.replace(/^postgres(ql)?:\/\//, 'http://');
        const url = new URL(urlToParse);

        const username = url.username;
        if (!username) return null;

        const host = url.hostname;
        if (!host) return null;

        const port = url.port || '5432';
        const password = url.password || undefined;

        const pathname = url.pathname.substring(1);
        const database = pathname.split('?')[0];

        if (!database) return null;

        return { host, port, username, database, password };
    } catch {
        // Fallback to regex
        try {
            const match = connectionUrl.match(
                /^postgres(?:ql)?:\/\/([^:@]+)(?::([^@]*))?@(\[[\da-fA-F:]+\]|[^:/]+)(?::(\d+))?\/([^?]+)/
            );
            if (!match) return null;

            const [, encodedUsername, password, host, port = '5432', database] = match;
            const username = decodeURIComponent(encodedUsername);
            const cleanHost = host.startsWith('[') && host.endsWith(']') ? host.slice(1, -1) : host;

            return {
                host: cleanHost,
                port,
                username,
                database,
                password: password ? decodeURIComponent(password) : undefined,
            };
        } catch {
            return null;
        }
    }
}

function generateProfileName(username: string, host: string, database: string): string {
    return `${username}@${host}/${database}`;
}

export async function saveProfile(connectionUrl: string, token: string, name?: string): Promise<SaveProfileResult | null> {
    try {
        const parsedFields = parseConnectionUrl(connectionUrl);
        if (!parsedFields) return null;

        const profiles = await getProfiles(token);
        
        // Check if existing profile matches
        const existingProfile = profiles.find(p => 
            p.host === parsedFields.host && 
            p.port === parsedFields.port && 
            p.username === parsedFields.username && 
            p.database === parsedFields.database
        );

        if (existingProfile) {
            existingProfile.lastUsed = new Date().toISOString();
            if (name && name !== existingProfile.name) {
                existingProfile.name = name;
            }
            
            const updated = await apiClient.updateProfile(existingProfile.id, {
                lastUsed: existingProfile.lastUsed,
                name: existingProfile.name
            }, token);
            
            return { profile: updated, isNew: false };
        }

        const newProfileData = {
            name: name || generateProfileName(parsedFields.username, parsedFields.host, parsedFields.database),
            host: parsedFields.host,
            port: parsedFields.port,
            username: parsedFields.username,
            database: parsedFields.database,
            password: parsedFields.password || ""
        };

        const newProfile = await apiClient.createProfile(newProfileData, token);
        return { profile: newProfile, isNew: true };
    } catch (error) {
        console.error('Failed to save profile:', error);
        return null;
    }
}

const STORAGE_KEY = 'sequel-speak-profiles';

export async function getProfiles(token: string): Promise<ConnectionProfile[]> {
    try {
        // Migration path for existing locally-stored profiles
        const localData = localStorage.getItem(STORAGE_KEY);
        if (localData) {
            try {
                const parsed = JSON.parse(localData);
                if (Array.isArray(parsed) && parsed.length > 0) {
                    console.warn(`Migrating ${parsed.length} profiles from LocalStorage to backend...`);
                    // Migrate in parallel, tracking per-profile success/failure
                    const results = await Promise.all(parsed.map(async (p: { name: string; host: string; port: string; username: string; database: string }) => {
                        try {
                            await apiClient.createProfile({
                                name: p.name,
                                host: p.host,
                                port: p.port,
                                username: p.username,
                                database: p.database,
                                password: "", // Need user to re-enter
                            }, token);
                            return { success: true as const, profile: p };
                        } catch (err) {
                            console.error(`Failed to migrate profile ${p.name}`, err);
                            return { success: false as const, profile: p };
                        }
                    }));

                    const failed = results.filter(r => !r.success).map(r => r.profile);
                    if (failed.length === 0) {
                        // All profiles migrated — safe to clear
                        localStorage.removeItem(STORAGE_KEY);
                    } else {
                        // Retain only profiles that failed so they can be retried next time
                        localStorage.setItem(STORAGE_KEY, JSON.stringify(failed));
                        console.warn(`${failed.length} profile(s) could not be migrated and were kept in LocalStorage for retry.`);
                    }
                } else {
                    // Empty or malformed array — nothing to migrate, safe to clear
                    localStorage.removeItem(STORAGE_KEY);
                }
            } catch (err) {
                // Parsing failed — do NOT clear; data may still be salvageable
                console.error('Migration parsing failed', err);
            }
        }

        return await apiClient.getProfiles(token);
    } catch (error) {
        console.error('Failed to get profiles:', error);
        return [];
    }
}

export async function getProfileById(id: string, token: string): Promise<ConnectionProfile | null> {
    try {
        const profiles = await getProfiles(token);
        return profiles.find(p => p.id === id) || null;
    } catch {
        return null;
    }
}

export async function deleteProfile(id: string, token: string): Promise<boolean> {
    try {
        await apiClient.deleteProfile(id, token);
        return true;
    } catch (error) {
        console.error('Failed to delete profile:', error);
        return false;
    }
}

export async function updateLastUsed(id: string, token: string): Promise<boolean> {
    try {
        await apiClient.updateProfile(id, { lastUsed: new Date().toISOString() }, token);
        return true;
    } catch {
        return false;
    }
}

export async function updateProfileName(id: string, newName: string, token: string): Promise<boolean> {
    try {
        await apiClient.updateProfile(id, { name: newName.trim() }, token);
        return true;
    } catch {
        return false;
    }
}
