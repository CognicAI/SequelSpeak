import { describe, it, expect, beforeEach, vi } from 'vitest';
import { saveProfile, getProfiles, deleteProfile } from '../profileStorage';
import { apiClient } from '../api/client';
import type { ConnectionProfile } from '../../types/profile';

vi.mock('../api/client', () => ({
    apiClient: {
        getProfiles: vi.fn(),
        createProfile: vi.fn(),
        updateProfile: vi.fn(),
        deleteProfile: vi.fn(),
    }
}));

describe('profileStorage', () => {
    const mockToken = "fake-jwt-token";

    beforeEach(() => {
        vi.clearAllMocks();
        localStorage.clear();
    });

    describe('saveProfile', () => {
        it('saves a new profile and marks it as new', async () => {
            const url = 'postgres://user:pass@localhost:5432/testdb';
            
            vi.mocked(apiClient.getProfiles).mockResolvedValueOnce([]);
            vi.mocked(apiClient.createProfile).mockResolvedValueOnce({
                id: 'new-id',
                name: 'user@localhost/testdb',
                host: 'localhost',
                port: '5432',
                username: 'user',
                database: 'testdb',
                createdAt: new Date().toISOString()
            } as unknown as ConnectionProfile);

            const result = await saveProfile(url, mockToken);

            expect(result).not.toBeNull();
            expect(result?.isNew).toBe(true);
            expect(result?.profile.host).toBe('localhost');
            expect(result?.profile.port).toBe('5432');
            expect(result?.profile.username).toBe('user');
            expect(result?.profile.database).toBe('testdb');
            expect(apiClient.createProfile).toHaveBeenCalledWith(expect.objectContaining({
                password: 'pass'
            }), mockToken);
        });

        it('updates an existing profile (same connection) and marks it as not new', async () => {
            const url = 'postgres://user:pass@localhost:5432/testdb';
            
            const existingProfile = {
                id: 'existing-id',
                name: 'user@localhost/testdb',
                host: 'localhost',
                port: '5432',
                username: 'user',
                database: 'testdb',
                createdAt: new Date().toISOString()
            };

            vi.mocked(apiClient.getProfiles).mockResolvedValueOnce([existingProfile] as unknown as ConnectionProfile[]);
            vi.mocked(apiClient.updateProfile).mockResolvedValueOnce(existingProfile as unknown as ConnectionProfile);

            const result = await saveProfile(url, mockToken);

            expect(result?.isNew).toBe(false);
            expect(result?.profile.id).toBe('existing-id');
            expect(apiClient.updateProfile).toHaveBeenCalledWith('existing-id', expect.objectContaining({
                password: 'pass'
            }), mockToken);
        });

        it('returns null for a malformed URL', async () => {
            const result = await saveProfile('not-a-postgres-url', mockToken);
            expect(result).toBeNull();
        });
    });

    describe('getProfiles', () => {
        it('returns an empty array when no profiles are returned by api', async () => {
            vi.mocked(apiClient.getProfiles).mockResolvedValueOnce([]);
            expect(await getProfiles(mockToken)).toEqual([]);
        });

        it('migrates from local storage if available', async () => {
            localStorage.setItem(
                'sequel-speak-profiles',
                JSON.stringify([{ id: 'old-id', name: 'migrated', host: 'h', port: '5432', username: 'u', database: 'd' }]),
            );
            
            vi.mocked(apiClient.createProfile).mockResolvedValueOnce({} as unknown as ConnectionProfile);
            vi.mocked(apiClient.getProfiles).mockResolvedValueOnce([{ id: 'new-id' }] as unknown as ConnectionProfile[]);

            const profiles = await getProfiles(mockToken);
            expect(profiles).toHaveLength(1);
            expect(apiClient.createProfile).toHaveBeenCalled();
            expect(localStorage.getItem('sequel-speak-profiles')).toBeNull();
        });
    });

    describe('deleteProfile', () => {
        it('removes an existing profile and returns true', async () => {
            vi.mocked(apiClient.deleteProfile).mockResolvedValueOnce(undefined as void);
            expect(await deleteProfile('some-id', mockToken)).toBe(true);
            expect(apiClient.deleteProfile).toHaveBeenCalledWith('some-id', mockToken);
        });

        it('returns false when api throws', async () => {
            vi.mocked(apiClient.deleteProfile).mockRejectedValueOnce(new Error('fail'));
            expect(await deleteProfile('00000000-0000-4000-8000-000000000000', mockToken)).toBe(false);
        });
    });
});
