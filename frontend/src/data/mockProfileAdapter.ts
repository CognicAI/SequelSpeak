/**
 * Mock Profile Adapter
 * 
 * Provides simulated connection profiles for UI testing.
 * This will be replaced with LocalStorage-backed implementation in a later phase.
 * 
 * IMPORTANT: This mock data follows the stable connection profile contract exactly.
 */

import type { ConnectionProfile, ProfileAdapter } from '../types/connectionProfile';

/**
 * Mock connection profiles for UI development and testing.
 * Simulates various real-world scenarios:
 * - Development database (localhost)
 * - Staging/QA database
 * - Production database (read-only)
 */
const MOCK_PROFILES: ConnectionProfile[] = [
    {
        id: 'profile-dev-001',
        profileName: 'Local Development',
        connection: {
            host: 'localhost',
            port: '5432',
            user: 'dev_user',
            password: 'dev_password_123',
            database: 'sequelspeak_dev',
        },
        createdAt: '2026-01-15T10:30:00Z',
        updatedAt: '2026-01-15T10:30:00Z',
    },
    {
        id: 'profile-staging-002',
        profileName: 'Staging Database',
        connection: {
            host: 'staging-db.example.com',
            port: '5432',
            user: 'staging_user',
            password: 'staging_secure_pass',
            database: 'sequelspeak_staging',
        },
        createdAt: '2026-01-10T08:00:00Z',
        updatedAt: '2026-01-18T14:22:00Z',
    },
    {
        id: 'profile-prod-003',
        profileName: 'Production (Read-Only)',
        connection: {
            host: 'prod-replica.example.com',
            port: '5433',
            user: 'readonly_user',
            password: 'prod_readonly_pass',
            database: 'sequelspeak_prod',
        },
        createdAt: '2026-01-05T12:00:00Z',
        updatedAt: '2026-01-05T12:00:00Z',
    },
];

/**
 * Mock Profile Adapter Implementation
 * Implements the ProfileAdapter interface with in-memory mock data.
 */
class MockProfileAdapter implements ProfileAdapter {
    private profiles: ConnectionProfile[];

    constructor(profiles: ConnectionProfile[] = MOCK_PROFILES) {
        // Create a defensive copy to prevent external mutations
        this.profiles = [...profiles];
    }

    /**
     * Returns all available connection profiles.
     * Returns an empty array if no profiles exist (defensive).
     */
    getProfiles(): ConnectionProfile[] {
        return [...this.profiles];
    }

    /**
     * Returns a profile by its ID.
     * Returns undefined if profile not found (defensive).
     */
    getProfileById(id: string): ConnectionProfile | undefined {
        if (!id) return undefined;
        return this.profiles.find(profile => profile.id === id);
    }
}

/**
 * Singleton instance of the mock adapter.
 * UI components should import and use this instance.
 */
export const mockProfileAdapter = new MockProfileAdapter();

/**
 * Factory function to create a mock adapter with custom profiles.
 * Useful for testing edge cases (empty list, single profile, etc.)
 */
export function createMockAdapter(profiles: ConnectionProfile[]): ProfileAdapter {
    return new MockProfileAdapter(profiles);
}

/**
 * Empty adapter for testing "no profiles" edge case.
 */
export const emptyProfileAdapter = new MockProfileAdapter([]);

/**
 * Single profile adapter for testing "one profile" scenario.
 */
export const singleProfileAdapter = new MockProfileAdapter([MOCK_PROFILES[0]]);

// Export mock data for testing purposes
export { MOCK_PROFILES };
