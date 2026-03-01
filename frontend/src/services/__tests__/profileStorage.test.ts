import { describe, it, expect, beforeEach } from 'vitest';
import { saveProfile, getProfiles, deleteProfile } from '../profileStorage';

describe('profileStorage', () => {
    beforeEach(() => {
        localStorage.clear();
    });

    describe('saveProfile', () => {
        it('saves a new profile and marks it as new', () => {
            const url = 'postgres://user:pass@localhost:5432/testdb';
            const result = saveProfile(url);

            expect(result).not.toBeNull();
            expect(result?.isNew).toBe(true);
            expect(result?.profile.host).toBe('localhost');
            expect(result?.profile.port).toBe('5432');
            expect(result?.profile.username).toBe('user');
            expect(result?.profile.database).toBe('testdb');
        });

        it('updates an existing profile (same connection) and marks it as not new', () => {
            const url = 'postgres://user:pass@localhost:5432/testdb';
            const firstSave = saveProfile(url);
            const secondSave = saveProfile(url);

            expect(secondSave?.isNew).toBe(false);
            expect(secondSave?.profile.id).toBe(firstSave?.profile.id);
        });

        it('does NOT store the password in localStorage', () => {
            const url = 'postgres://user:supersecret@localhost:5432/testdb';
            saveProfile(url);

            const raw = localStorage.getItem('sequel-speak-profiles') ?? '';
            expect(raw).not.toContain('supersecret');
        });

        it('returns null for a malformed URL', () => {
            const result = saveProfile('not-a-postgres-url');
            expect(result).toBeNull();
        });
    });

    describe('getProfiles', () => {
        it('returns an empty array when no profiles are stored', () => {
            expect(getProfiles()).toEqual([]);
        });

        it('returns only valid profiles (filters corrupted data)', () => {
            // Inject invalid data directly into localStorage
            localStorage.setItem(
                'sequel-speak-profiles',
                JSON.stringify([{ id: 'bad-id', name: 'broken' }]),
            );
            expect(getProfiles()).toEqual([]);
        });

        it('returns saved profiles after saving', () => {
            saveProfile('postgres://user:pass@host:5432/db');
            const profiles = getProfiles();
            expect(profiles).toHaveLength(1);
        });
    });

    describe('deleteProfile', () => {
        it('removes an existing profile and returns true', () => {
            const result = saveProfile('postgres://user:pass@host:5432/db');
            const id = result!.profile.id;

            expect(deleteProfile(id)).toBe(true);
            expect(getProfiles()).toHaveLength(0);
        });

        it('returns false when profile is not found', () => {
            expect(deleteProfile('00000000-0000-4000-8000-000000000000')).toBe(false);
        });
    });
});
