import { useState, useEffect, useRef, useCallback, type FormEvent } from 'react';
import { Check, Database, AlertCircle, ArrowRight, Server, User, Key, Globe, Folder, Loader2 } from 'lucide-react';
import { useAuth } from '@clerk/clerk-react';
import { cn } from '../lib/utils';
import type { TestConnectionSuccessResponse, TestConnectionErrorResponse } from '../types/api';
import { getErrorMessage } from '../types/api';
import { ProfileSelector } from './ProfileSelector';
import { ConnectionStatusBanner, type ConnectionStatus } from './ConnectionStatusBanner';
import { useProfileSelection } from '../hooks/useProfileSelection';
import type { ConnectionProfile } from '../types/profile';
import { saveProfile } from '../services/profileStorage';

type ConnectionMode = 'url' | 'fields';

export function ConnectionForm() {
    const { getToken } = useAuth();  // Get Clerk authentication hook
    const [mode, setMode] = useState<ConnectionMode>('url');
    const [url, setUrl] = useState('');

    // Field states
    const [host, setHost] = useState('localhost');
    const [port, setPort] = useState('5432');
    const [user, setUser] = useState('');
    const [password, setPassword] = useState('');
    const [database, setDatabase] = useState('');

    /**
     * Auto-fill form fields from a connection profile.
     * Switches to 'fields' mode to show the filled values.
     */
    const fillFormFromProfile = useCallback((profile: ConnectionProfile) => {
        setHost(profile.host);
        setPort(profile.port);
        setUser(profile.username);
        // Password is never stored, so leave it empty for user to enter
        setPassword('');
        setDatabase(profile.database);

        // Switch to fields mode to show the filled values
        setMode('fields');

        // Clear any previous status messages when switching profiles
        setStatusMessage(null);
    }, []);

    /**
     * Clear form fields when profile selection is cleared.
     */
    const clearFormFields = useCallback(() => {
        setHost('localhost');
        setPort('5432');
        setUser('');
        setPassword('');
        setDatabase('');
        setUrl('');
        setStatusMessage(null);
    }, []);

    // Profile selection hook
    const {
        profiles,
        activeProfileId,
        isLoading: profilesLoading,
        error: profilesError,
        selectProfile,
        clearSelection,
        deleteProfile,
        renameProfile,
    } = useProfileSelection({
        onProfileSelect: fillFormFromProfile,
        onProfileClear: clearFormFields,
    });

    const [isValid, setIsValid] = useState<boolean | null>(null);
    const [error, setError] = useState('');
    const [isFocused, setIsFocused] = useState(false);

    // Regex for basic PostgreSQL connection string validation
    const postgresRegex = /^postgres(?:ql)?:\/\/(?:[^:@]+)(?::[^:@]*)?@(?:[^:@\/]+)(?::\d+)?\/[^:@\/]+$/;

    const validateUrl = (value: string) => {
        if (!value) {
            setIsValid(null);
            setError('');
            return;
        }

        if (postgresRegex.test(value)) {
            setIsValid(true);
            setError('');
        } else {
            setIsValid(false);
            setError('Invalid PostgreSQL connection URL format.');
        }
    };

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const value = e.target.value;
        setUrl(value);
        validateUrl(value);
    };

    // Auto-update URL when fields change
    useEffect(() => {
        if (mode === 'fields') {
            const encodedUser = user ? encodeURIComponent(user) : '<user>';
            const encodedPassword = password ? encodeURIComponent(password) : '<password>';
            const encodedHost = host ? host : '<host>';
            const encodedPort = port ? port : '<port>';
            const encodedDb = database ? database : '<dbname>';

            const generatedUrl = `postgres://${encodedUser}:${encodedPassword}@${encodedHost}:${encodedPort}/${encodedDb}`;
            if (user && database) {
                validateUrl(generatedUrl);
            } else {
                setIsValid(null);
                setError('');
            }
        }
    }, [host, port, user, password, database, mode]);

    const [isLoading, setIsLoading] = useState(false);
    const [statusMessage, setStatusMessage] = useState<{ type: 'success' | 'error', text: string } | null>(null);

    // Connection status tracking for notifications
    const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('unknown');
    const wasDisconnectedRef = useRef(false);

    // AbortController ref for cancelling in-flight requests
    const abortControllerRef = useRef<AbortController | null>(null);

    const handleSubmit = async (e: FormEvent) => {
        e.preventDefault();

        let connectionUrl = url;
        if (mode === 'fields') {
            const encodedUser = encodeURIComponent(user);
            const encodedPassword = encodeURIComponent(password);
            connectionUrl = `postgres://${encodedUser}:${encodedPassword}@${host}:${port}/${database}`;
        }

        if ((mode === 'url' && !isValid) || (mode === 'fields' && (!user || !database))) {
            return;
        }

        // Cancel any in-flight request
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }

        // Create new AbortController for this request
        abortControllerRef.current = new AbortController();

        setIsLoading(true);
        setStatusMessage(null);

        try {
            // Get JWT token from Clerk
            const token = await getToken();
            
            if (!token) {
                // This shouldn't happen if user is signed in, but handle gracefully
                setStatusMessage({
                    type: 'error',
                    text: 'Authentication failed. Please sign in again.'
                });
                return;
            }

            const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
            const response = await fetch(`${API_BASE_URL}/api/v1/utils/test-connection`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`,  // Add JWT token
                },
                body: JSON.stringify({ connection_url: connectionUrl }),
                signal: abortControllerRef.current.signal,
            });

            const data = await response.json();

            if (response.ok) {
                const successData = data as TestConnectionSuccessResponse;

                // Check if recovering from a disconnected state
                if (wasDisconnectedRef.current) {
                    setConnectionStatus('connected');
                    wasDisconnectedRef.current = false;
                }

                // Save profile to LocalStorage after successful connection
                const result = saveProfile(connectionUrl);

                if (result) {
                    // Use the isNew flag to determine if this was a new profile or an update
                    const action = result.isNew ? 'saved' : 'updated';

                    setStatusMessage({
                        type: 'success',
                        text: `${successData.message} Profile "${result.profile.name}" ${action} successfully.`
                    });
                } else {
                    // Connection succeeded but profile save failed (e.g., quota exceeded)
                    setStatusMessage({
                        type: 'success',
                        text: `${successData.message} (Note: Profile could not be saved to browser storage)`
                    });
                }
            } else {
                const errorData = data as TestConnectionErrorResponse;

                // Check for CONNECTION_LOST error code
                if (errorData.error_code === 'CONNECTION_LOST') {
                    setConnectionStatus('disconnected');
                    wasDisconnectedRef.current = true;
                }

                // Handle 401 authentication errors specifically
                if (response.status === 401) {
                    setStatusMessage({
                        type: 'error',
                        text: 'Your session has expired. Please sign in again.'
                    });
                } else {
                    setStatusMessage({
                        type: 'error',
                        text: getErrorMessage(errorData.detail)
                    });
                }
            }
        } catch (err) {
            // Don't show error if request was aborted (user cancelled)
            if (err instanceof Error && err.name === 'AbortError') {
                return;
            }
            setStatusMessage({ type: 'error', text: 'Failed to connect to backend server. Please check your network connection.' });
        } finally {
            setIsLoading(false);
            abortControllerRef.current = null;
        }
    };

    return (
        <div className="w-full max-w-md mx-auto p-1 rounded-2xl bg-gradient-to-br from-white/10 to-white/5 shadow-2xl backdrop-blur-xl border border-white/10">
            <div className="bg-background/80 rounded-xl p-8 transition-all duration-300">
                {/* Connection Status Banner */}
                <ConnectionStatusBanner
                    status={connectionStatus}
                    onDismiss={() => setConnectionStatus('unknown')}
                />
                <div className="flex flex-col items-center gap-6">
                    <div className={cn(
                        "p-4 rounded-full bg-primary/10 transition-all duration-500 relative",
                        isValid ? "bg-green-500/20 text-green-400" : "text-primary"
                    )}>
                        <Database className="w-8 h-8" />
                        {isValid && (
                            <div className="absolute -bottom-1 -right-1 bg-green-500 text-black rounded-full p-0.5 animate-in fade-in zoom-in duration-300 border-2 border-background">
                                <Check className="w-3 h-3 stroke-[3]" />
                            </div>
                        )}
                    </div>

                    <div className="text-center space-y-2">
                        <h2 className="text-2xl font-bold bg-gradient-to-br from-white to-white/60 bg-clip-text text-transparent">
                            Connect Database
                        </h2>
                        <p className="text-sm text-gray-400">
                            Enter your PostgreSQL connection details
                        </p>
                        <p className="text-xs text-gray-500/80 mt-1">
                            <span className="font-medium text-yellow-500/80">Security Note:</span> Your connection string is encrypted in transit. We never log your credentials.
                        </p>
                        <p className="text-xs text-green-400/70 mt-1 px-2">
                            🔒 Passwords are NEVER stored. Saved profiles only contain connection metadata (host, port, username, database).
                        </p>
                    </div>

                    {/* Profile Selector */}
                    <div className="w-full space-y-2">
                        <label className="text-xs text-gray-400 ml-1 flex items-center gap-1.5">
                            <span>Saved Profiles</span>
                            {activeProfileId && (
                                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-green-500/20 text-green-400 text-[10px] font-medium">
                                    <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                                    Active
                                </span>
                            )}
                        </label>
                        <ProfileSelector
                            profiles={profiles}
                            activeProfileId={activeProfileId}
                            isLoading={profilesLoading}
                            error={profilesError}
                            onProfileSelect={selectProfile}
                            onClearSelection={clearSelection}
                            onDeleteProfile={deleteProfile}
                            onRenameProfile={renameProfile}
                            disabled={isLoading}
                        />
                    </div>

                    {/* Divider */}
                    <div className="w-full flex items-center gap-3">
                        <div className="flex-1 h-px bg-gradient-to-r from-transparent via-white/10 to-transparent" />
                        <span className="text-xs text-gray-600 uppercase tracking-wider">or enter manually</span>
                        <div className="flex-1 h-px bg-gradient-to-r from-transparent via-white/10 to-transparent" />
                    </div>

                    {/* Mode Toggles */}
                    <div className="flex p-1 bg-white/5 rounded-lg w-full">
                        <button
                            type="button"
                            onClick={() => setMode('url')}
                            disabled={isLoading}
                            className={cn(
                                "flex-1 py-1.5 text-sm font-medium rounded-md transition-all duration-300",
                                mode === 'url' ? "bg-primary/20 text-primary shadow-sm" : "text-gray-400 hover:text-white",
                                isLoading ? "cursor-not-allowed opacity-50" : "cursor-pointer"
                            )}
                        >
                            Connection String
                        </button>
                        <button
                            type="button"
                            onClick={() => setMode('fields')}
                            disabled={isLoading}
                            className={cn(
                                "flex-1 py-1.5 text-sm font-medium rounded-md transition-all duration-300",
                                mode === 'fields' ? "bg-primary/20 text-primary shadow-sm" : "text-gray-400 hover:text-white",
                                isLoading ? "cursor-not-allowed opacity-50" : "cursor-pointer"
                            )}
                        >
                            Parameters
                        </button>
                    </div>

                    <form onSubmit={handleSubmit} className="w-full space-y-4">
                        {mode === 'url' ? (
                            <div className="space-y-3">
                                <div className="relative group">
                                    <input
                                        type="text"
                                        value={url}
                                        onChange={handleChange}
                                        onFocus={() => setIsFocused(true)}
                                        onBlur={() => setIsFocused(false)}
                                        placeholder=" "
                                        disabled={isLoading}
                                        className={cn(
                                            "w-full pl-11 pr-12 py-3 rounded-xl bg-background/50 border outline-none transition-all duration-300 peer",
                                            "text-sm font-mono tracking-wide pt-5 pb-2", // Adjusted padding for label effect
                                            isLoading && "opacity-50 cursor-not-allowed",
                                            isValid === false
                                                ? "border-red-500/50 focus:border-red-500 focus:ring-1 focus:ring-red-500/50"
                                                : isValid === true
                                                    ? "border-green-500/50 focus:border-green-500 focus:ring-1 focus:ring-green-500/50"
                                                    : "border-white/10 focus:border-primary/50 focus:ring-1 focus:ring-primary/50"
                                        )}
                                    />

                                    {/* Floating Label / Placeholder */}
                                    <div className={cn(
                                        "absolute left-11 top-3.5 text-gray-500 text-sm font-mono pointer-events-none transition-all duration-200 truncate right-14",
                                        (isFocused || url) && "text-[10px] -translate-y-2.5 opacity-70"
                                    )}>
                                        postgres://user:pass@host:5432/db
                                    </div>

                                    <Database className={cn(
                                        "absolute left-3.5 top-3.5 w-4 h-4 transition-colors duration-300",
                                        isFocused ? "text-primary" : "text-gray-600"
                                    )} />

                                    {/* Prominent Success Indicator */}
                                    <div className="absolute right-3 top-1/2 -translate-y-1/2">
                                        {isValid ? (
                                            <div className="bg-green-500 text-black rounded-full p-1 animate-in fade-in zoom-in">
                                                <Check className="w-3 h-3 stroke-[3]" />
                                            </div>
                                        ) : isValid === false ? (
                                            <div className="bg-red-500/20 rounded-full p-1 animate-in fade-in zoom-in">
                                                <AlertCircle className="w-4 h-4 text-red-500" />
                                            </div>
                                        ) : null}
                                    </div>
                                </div>

                                {/* Persistent Format Hint */}
                                <div className="px-3 py-2.5 bg-white/5 rounded-lg border border-white/5 flex flex-col gap-1.5">
                                    <span className="text-xs text-gray-500 uppercase tracking-wider font-semibold">Format Template</span>
                                    <code className="text-sm text-gray-400 font-mono whitespace-nowrap overflow-x-auto block pb-1">
                                        postgres://<span className="text-blue-400">user</span>:<span className="text-red-400">password</span>@<span className="text-green-400">host</span>:<span className="text-yellow-400">5432</span>/<span className="text-purple-400">dbname</span>
                                    </code>
                                </div>
                            </div>
                        ) : (
                            <div className="space-y-3 animate-in slide-in-from-right-4 fade-in duration-300">
                                <div className="grid grid-cols-2 gap-3">
                                    <div className="space-y-1">
                                        <label className="text-xs text-gray-400 ml-1">Host</label>
                                        <div className="relative">
                                            <Server className="absolute left-3 top-2.5 w-4 h-4 text-gray-500" />
                                            <input
                                                value={host}
                                                onChange={(e) => setHost(e.target.value)}
                                                disabled={isLoading}
                                                className={cn(
                                                    "w-full bg-background/50 border border-white/10 rounded-lg py-2 pl-9 pr-8 text-sm focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/50",
                                                    isLoading && "opacity-50 cursor-not-allowed"
                                                )}
                                                placeholder="localhost"
                                            />
                                            {host && /^([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]*[a-zA-Z0-9])(\.([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]*[a-zA-Z0-9]))*$|^localhost$/.test(host) && (
                                                <div className="absolute right-2.5 top-2.5 animate-in fade-in zoom-in">
                                                    <Check className="w-4 h-4 text-green-500" />
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-xs text-gray-400 ml-1">Port</label>
                                        <div className="relative">
                                            <Globe className="absolute left-3 top-2.5 w-4 h-4 text-gray-500" />
                                            <input
                                                value={port}
                                                maxLength={5}
                                                onChange={(e) => {
                                                    const val = e.target.value;
                                                    if (/^\d*$/.test(val)) setPort(val);
                                                }}
                                                disabled={isLoading}
                                                className={cn(
                                                    "w-full bg-background/50 border border-white/10 rounded-lg py-2 pl-9 pr-8 text-sm focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/50",
                                                    isLoading && "opacity-50 cursor-not-allowed"
                                                )}
                                                placeholder="5432"
                                            />
                                            {port.length === 6 && (
                                                <div className="absolute right-2.5 top-2.5 animate-in fade-in zoom-in">
                                                    <Check className="w-4 h-4 text-green-500" />
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </div>

                                <div className="grid grid-cols-2 gap-3">
                                    <div className="space-y-1">
                                        <label className="text-xs text-gray-400 ml-1">User</label>
                                        <div className="relative">
                                            <User className="absolute left-3 top-2.5 w-4 h-4 text-gray-500" />
                                            <input
                                                value={user}
                                                onChange={(e) => setUser(e.target.value)}
                                                disabled={isLoading}
                                                className={cn(
                                                    "w-full bg-background/50 border border-white/10 rounded-lg py-2 pl-9 pr-8 text-sm focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/50",
                                                    isLoading && "opacity-50 cursor-not-allowed"
                                                )}
                                                placeholder="postgres"
                                            />
                                            {user && (
                                                <div className="absolute right-2.5 top-2.5 animate-in fade-in zoom-in">
                                                    <Check className="w-4 h-4 text-green-500" />
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-xs text-gray-400 ml-1">Password</label>
                                        <div className="relative">
                                            <Key className="absolute left-3 top-2.5 w-4 h-4 text-gray-500" />
                                            <input
                                                type="password"
                                                value={password}
                                                onChange={(e) => setPassword(e.target.value)}
                                                disabled={isLoading}
                                                className={cn(
                                                    "w-full bg-background/50 border border-white/10 rounded-lg py-2 pl-9 pr-8 text-sm focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/50",
                                                    isLoading && "opacity-50 cursor-not-allowed"
                                                )}
                                                placeholder="••••••"
                                            />
                                            {password && (
                                                <div className="absolute right-2.5 top-2.5 animate-in fade-in zoom-in">
                                                    <Check className="w-4 h-4 text-green-500" />
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </div>

                                <div className="space-y-1">
                                    <label className="text-xs text-gray-400 ml-1">Database Name</label>
                                    <div className="relative">
                                        <Folder className="absolute left-3 top-2.5 w-4 h-4 text-gray-500" />
                                        <input
                                            value={database}
                                            onChange={(e) => setDatabase(e.target.value)}
                                            disabled={isLoading}
                                            className={cn(
                                                "w-full bg-background/50 border border-white/10 rounded-lg py-2 pl-9 pr-8 text-sm focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/50",
                                                isLoading && "opacity-50 cursor-not-allowed"
                                            )}
                                            placeholder="my_database"
                                        />
                                        {database && (
                                            <div className="absolute right-2.5 top-2.5 animate-in fade-in zoom-in">
                                                <Check className="w-4 h-4 text-green-500" />
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>
                        )}

                        <div className="space-y-2">
                            {/* Validation Error */}
                            <div className={cn(
                                "flex items-center gap-2 text-xs transition-all duration-300 overflow-hidden",
                                ((mode === 'url' && isValid === false) && !statusMessage) ? "h-6 opacity-100 text-red-400" : "h-0 opacity-0"
                            )}>
                                <AlertCircle className="w-3 h-3" />
                                <span>{error}</span>
                            </div>

                            {/* API Status Message */}
                            {statusMessage && (
                                <div className={cn(
                                    "flex items-center gap-2 text-xs p-3 rounded-lg animate-in fade-in slide-in-from-top-2",
                                    statusMessage.type === 'success'
                                        ? "bg-green-500/10 text-green-400 border border-green-500/20"
                                        : "bg-red-500/10 text-red-400 border border-red-500/20"
                                )}>
                                    {statusMessage.type === 'success' ? (
                                        <Check className="w-4 h-4 shrink-0" />
                                    ) : (
                                        <AlertCircle className="w-4 h-4 shrink-0" />
                                    )}
                                    <span>{statusMessage.text}</span>
                                </div>
                            )}
                        </div>

                        <button
                            type="submit"
                            disabled={isLoading || (!isValid && mode === 'url') || (mode === 'fields' && (!user || !database))}
                            className={cn(
                                "w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl font-medium transition-all duration-300",
                                (isValid || (mode === 'fields' && user && database)) && !isLoading
                                    ? "bg-gradient-to-r from-primary to-secondary hover:opacity-90 hover:scale-[1.02] shadow-lg shadow-primary/25 cursor-pointer text-white"
                                    : "bg-white/5 text-gray-500 cursor-not-allowed border border-white/5"
                            )}
                        >
                            {isLoading ? (
                                <>
                                    <Loader2 className="w-4 h-4 animate-spin" />
                                    <span>Testing Connection...</span>
                                </>
                            ) : (
                                <>
                                    <span>Test Connection</span>
                                    <ArrowRight className={cn(
                                        "w-4 h-4 transition-transform duration-300",
                                        (isValid || (mode === 'fields' && user && database)) && "group-hover:translate-x-1"
                                    )} />
                                </>
                            )}
                        </button>
                    </form>
                </div>
            </div>
        </div>
    );
}
