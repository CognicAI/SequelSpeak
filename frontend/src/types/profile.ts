/**
 * Connection Profile Types
 * 
 * Defines the data contract for database connection profiles
 * stored in browser LocalStorage.
 * 
 * SECURITY: Passwords are NEVER stored. Only non-sensitive connection
 * metadata is persisted. Users must re-enter passwords when using saved profiles.
 */

/**
 * Represents a saved database connection profile
 * Password is intentionally excluded for security reasons
 */
export interface ConnectionProfile {
    /** Unique identifier for the profile (UUID) */
    id: string;

    /** User-friendly name for the profile */
    name: string;

    /** Database host address */
    host: string;

    /** Database port number */
    port: string;

    /** Database username (non-sensitive) */
    username: string;

    /** Database name */
    database: string;

    /** ISO timestamp when the profile was created */
    createdAt: string;

    /** ISO timestamp when the profile was last used (optional) */
    lastUsed?: string;
}

/**
 * Request body for POST /api/v1/profiles.
 * `password` is accepted here so the backend can test the connection at
 * creation time — it is never persisted or returned in responses.
 */
export interface ProfileCreateRequest {
    name: string;
    host: string;
    port: string;
    username: string;
    database: string;
    /** Transient — used for connection verification only, never stored. */
    password: string;
}

/**
 * Request body for PUT /api/v1/profiles/:id.
 * All fields are optional so callers can send partial updates.
 */
export interface ProfileUpdateRequest {
    name?: string;
    host?: string;
    port?: string;
    username?: string;
    database?: string;
    lastUsed?: string;
}
