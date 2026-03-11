import type { ConnectionProfile } from '../types/profile';
import { getProfiles, getProfileById } from '../services/profileStorage';

export interface ProfileAdapter {
    /** Get all available connection profiles */
    getProfiles(token: string): Promise<ConnectionProfile[]>;
    /** Get a profile by its ID */
    getProfileById(id: string, token: string): Promise<ConnectionProfile | undefined>;
}

class ApiProfileAdapter implements ProfileAdapter {
    async getProfiles(token: string): Promise<ConnectionProfile[]> {
        return await getProfiles(token);
    }

    async getProfileById(id: string, token: string): Promise<ConnectionProfile | undefined> {
        return await getProfileById(id, token) || undefined;
    }
}

export const apiProfileAdapter = new ApiProfileAdapter();
