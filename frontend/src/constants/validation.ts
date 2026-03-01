/**
 * Constants for form field validation.
 * Centralises magic numbers used across connection form components.
 */
export const VALIDATION = {
    /** Maximum number of digits in a port number (5 = "65535") */
    PORT_MAX_LENGTH: 5,
    /** Minimum valid TCP port */
    PORT_MIN: 1,
    /** Maximum valid TCP port */
    PORT_MAX: 65535,
} as const;
