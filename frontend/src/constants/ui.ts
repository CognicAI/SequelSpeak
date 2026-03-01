/**
 * Constants for UI timing and animation delays.
 * Centralises magic numbers used across UI components.
 */
export const UI = {
    /** Default delay (ms) before auto-dismissing a status banner after reconnection */
    AUTO_DISMISS_DELAY: 3000,
    /** Debounce delay (ms) for expensive input-driven operations like URL validation */
    DEBOUNCE_DELAY: 300,
} as const;
