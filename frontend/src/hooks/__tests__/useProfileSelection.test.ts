import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useProfileSelection } from '../useProfileSelection';
import type { ProfileAdapter } from '../../data/apiProfileAdapter';
import type { ConnectionProfile } from '../../types/profile';

vi.mock('@clerk/clerk-react', () => ({
    useAuth: () => ({
        getToken: vi.fn().mockResolvedValue('fake-token'),
        isSignedIn: true,
    })
}));

/** Creates a fake profile with sane defaults */
function makeProfile(overrides: Partial<ConnectionProfile> = {}): ConnectionProfile {
    return {
        id: '00000000-0000-4000-8000-000000000001',
        name: 'Test Profile',
        host: 'localhost',
        port: '5432',
        username: 'user',
        database: 'testdb',
        createdAt: new Date().toISOString(),
        ...overrides,
    };
}

/** Mock adapter backed by an in-memory array */
function makeMockAdapter(initial: ConnectionProfile[] = []): ProfileAdapter {
    const store = [...initial];
    return {
        getProfiles: async () => store,
        getProfileById: async (id: string, _token: string) => store.find(p => p.id === id),
    };
}

describe('useProfileSelection', () => {
    beforeEach(() => {
        localStorage.clear();
    });

    it('initialises with empty profiles when adapter returns []', async () => {
        const adapter = makeMockAdapter([]);
        const { result } = renderHook(() => useProfileSelection({ adapter }));

        expect(result.current.profiles).toEqual([]);
        expect(result.current.activeProfileId).toBeNull();
        expect(result.current.isLoading).toBe(true);

        await act(async () => {
            await new Promise(resolve => setTimeout(resolve, 0));
        });

        expect(result.current.isLoading).toBe(false);
        expect(result.current.profiles).toEqual([]);
    });

    it('loads profiles from the adapter on mount', async () => {
        const profile = makeProfile();
        const adapter = makeMockAdapter([profile]);
        
        // renderHook acts like mounting
        const { result } = renderHook(() => useProfileSelection({ adapter }));

        expect(result.current.isLoading).toBe(true);
        // Wait for async load to finish
        // We can just await the macrotask / promises
        await act(async () => {
            await new Promise(resolve => setTimeout(resolve, 0));
        });

        expect(result.current.isLoading).toBe(false);
        expect(result.current.profiles).toHaveLength(1);
        expect(result.current.profiles[0].id).toBe(profile.id);
    });

    it('calls onProfileSelect callback when selecting a profile', async () => {
        const profile = makeProfile();
        const adapter = makeMockAdapter([profile]);
        const onProfileSelect = vi.fn();

        const { result } = renderHook(() =>
            useProfileSelection({ adapter, onProfileSelect }),
        );
        
        await act(async () => {
             await new Promise(resolve => setTimeout(resolve, 0));
        });

        act(() => {
            result.current.selectProfile(profile.id);
        });

        expect(result.current.activeProfileId).toBe(profile.id);
        expect(onProfileSelect).toHaveBeenCalledWith(profile);
    });

    it('clears active profile on clearSelection', async () => {
        const profile = makeProfile();
        const adapter = makeMockAdapter([profile]);
        const onProfileClear = vi.fn();

        const { result } = renderHook(() =>
            useProfileSelection({ adapter, onProfileClear }),
        );
        
        await act(async () => {
             await new Promise(resolve => setTimeout(resolve, 0));
        });

        act(() => { result.current.selectProfile(profile.id); });
        act(() => { result.current.clearSelection(); });

        expect(result.current.activeProfileId).toBeNull();
        expect(onProfileClear).toHaveBeenCalledOnce();
    });

    it('sets error state when adapter throws', async () => {
        const badAdapter: ProfileAdapter = {
            ...makeMockAdapter(),
            getProfiles: async () => { throw new Error('Storage failure'); },
        };

        const { result } = renderHook(() => useProfileSelection({ adapter: badAdapter }));
        
        await act(async () => {
             await new Promise(resolve => setTimeout(resolve, 0));
        });

        expect(result.current.error).toBe('Storage failure');
        expect(result.current.profiles).toEqual([]);
    });

    it('clears activeProfileId when the active profile is absent after reload', async () => {
        // Start with one profile and select it.
        const profile = makeProfile();
        let availableProfiles: ConnectionProfile[] = [profile];
        const adapter: ProfileAdapter = {
            getProfiles: async () => availableProfiles,
            getProfileById: async (id) => availableProfiles.find(p => p.id === id),
        };

        const { result } = renderHook(() => useProfileSelection({ adapter }));
        
        await act(async () => {
             await new Promise(resolve => setTimeout(resolve, 0));
        });

        act(() => { result.current.selectProfile(profile.id); });
        expect(result.current.activeProfileId).toBe(profile.id);

        // Simulate the profile being removed from the underlying data source.
        availableProfiles = [];

        // Trigger a reload — loadProfiles now returns an empty list.
        await act(async () => { 
            result.current.refreshProfiles();
            await new Promise(resolve => setTimeout(resolve, 0));
        });

        // The cleanup effect detects the active profile is gone and nulls the ID.
        expect(result.current.activeProfileId).toBeNull();
        expect(result.current.profiles).toHaveLength(0);
    });
});
