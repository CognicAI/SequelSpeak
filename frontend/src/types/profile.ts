/**
 * Connection Profile Types
 * 
 * Defines the data contract for database connection profiles
 * stored in browser LocalStorage.
 */

/**
 * Represents a saved database connection profile
 */
export interface ConnectionProfile {
    /** Unique identifier for the profile (UUID) */
    id: string;

    /** User-friendly name for the profile */
    name: string;

    /** Full PostgreSQL connection URL */
    connectionUrl: string;

    /** ISO timestamp when the profile was created */
    createdAt: string;

    /** ISO timestamp when the profile was last used (optional) */
    lastUsed?: string;
}
