/// <reference types="vite/client" />

/**
 * Type-safe definitions for Vite's `import.meta.env` variables.
 * Document all VITE_ prefixed variables used in this project here.
 */
interface ImportMetaEnv {
    /** Backend API base URL. Defaults to http://localhost:8000 if not set. */
    readonly VITE_API_URL: string;
    /** Clerk publishable key for authentication. */
    readonly VITE_CLERK_PUBLISHABLE_KEY: string;
}

interface ImportMeta {
    readonly env: ImportMetaEnv;
}
