/**
 * Connection Profile Types
 * 
 * Stable contract for connection profiles.
 * This interface will be used by both the UI and the future LocalStorage persistence layer.
 */

/** Connection fields required to establish a database connection */
export interface ConnectionFields {
    host: string;
    port: string;
    user: string;
    password: string;
    database: string;
}

/** 
 * Connection Profile
 * Represents a saved database connection configuration.
 */
export interface ConnectionProfile {
    /** Unique identifier for the profile */
    id: string;
    /** Human-readable name for the profile */
    profileName: string;
    /** Connection fields to auto-fill the form */
    connection: ConnectionFields;
    /** Timestamp when the profile was created */
    createdAt: string;
    /** Timestamp when the profile was last updated */
    updatedAt: string;
}

/**
 * Profile Adapter Interface
 * Abstraction layer for profile data source.
 * UI components depend on this interface, not on concrete implementations.
 * This allows easy swapping between mock data and LocalStorage persistence.
 */
export interface ProfileAdapter {
    /** Get all available connection profiles */
    getProfiles(): ConnectionProfile[];
    /** Get a profile by its ID */
    getProfileById(id: string): ConnectionProfile | undefined;
}

/**
 * Profile Selection State
 * Represents the current selection state in the UI.
 */
export interface ProfileSelectionState {
    /** Currently selected/active profile ID, null if none selected */
    activeProfileId: string | null;
    /** List of available profiles */
    profiles: ConnectionProfile[];
    /** Whether profiles are currently loading */
    isLoading: boolean;
    /** Error message if profile loading failed */
    error: string | null;
}
