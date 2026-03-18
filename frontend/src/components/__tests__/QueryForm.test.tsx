/**
 * Integration tests for QueryForm component.
 *
 * Covers:
 * - Rendering with profiles
 * - Client-side validation prevents empty submission
 * - Successful form submission flow (202 / 200 OK)
 * - API error is displayed in the UI
 * - Loading state visible while submitting
 * - conversation_id stored in sessionStorage on success (FR-90)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryForm } from '../QueryForm';
import type { QueryStartResponse } from '../../types/query';
import type { ConnectionProfile } from '../../types/profile';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// Clerk Auth
vi.mock('@clerk/clerk-react', () => ({
    useAuth: () => ({
        getToken: vi.fn().mockResolvedValue('test-token'),
        isSignedIn: true,
    }),
}));

// Mock API client
const mockStartQuery = vi.fn();
const mockTestConnection = vi.fn();
vi.mock('../../services/api/client', () => ({
    apiClient: {
        startQuery: (...args: unknown[]) => mockStartQuery(...args),
        testConnection: (...args: unknown[]) => mockTestConnection(...args),
    },
}));

// Mock useProfileSelection so we can inject known profiles without network
const mockProfiles: ConnectionProfile[] = [
    {
        id: 'profile-uuid-1',
        name: 'Production DB',
        host: 'prod.example.com',
        port: '5432',
        username: 'admin',
        database: 'sales',
        createdAt: '2026-01-01T00:00:00Z',
    },
    {
        id: 'profile-uuid-2',
        name: 'Staging DB',
        host: 'staging.example.com',
        port: '5432',
        username: 'dev',
        database: 'sales_staging',
        createdAt: '2026-01-02T00:00:00Z',
    },
];

vi.mock('../../hooks/useProfileSelection', () => ({
    useProfileSelection: () => ({
        profiles: mockProfiles,
        isLoading: false,
        error: null,
        activeProfileId: null,
        selectProfile: vi.fn(),
        clearSelection: vi.fn(),
        deleteProfile: vi.fn(),
        renameProfile: vi.fn(),
        refreshProfiles: vi.fn(),
        getActiveConnectionFields: vi.fn(),
        isProfileActive: vi.fn(),
        activeProfile: null,
    }),
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeSuccessResponse(overrides?: Partial<QueryStartResponse>): QueryStartResponse {
    return {
        status: 'success',
        conversation_id: 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',
        query: 'Show me revenue',
        timestamp: '2026-03-14T10:00:00Z',
        message: 'Query initialized successfully',
        ...overrides,
    };
}

function renderQueryForm(props = {}) {
    return render(
        <QueryForm
            activeConnectionProfileId="profile-uuid-1"
            activeConnectionExpiresAtMs={Date.now() + 60_000}
            {...props}
        />,
    );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('QueryForm', () => {
    beforeEach(() => {
        mockStartQuery.mockReset();
        mockTestConnection.mockReset();
        sessionStorage.clear();
    });

    // -----------------------------------------------------------------------
    // Rendering
    // -----------------------------------------------------------------------

    it('renders the textarea, database select, and submit button', () => {
        renderQueryForm();
        expect(screen.getByTestId('nl-query-input')).toBeInTheDocument();
        expect(screen.getByTestId('database-select')).toBeInTheDocument();
        expect(screen.getByTestId('submit-button')).toBeInTheDocument();
    });

    it('renders all profile options in the database selector', () => {
        renderQueryForm();
        const select = screen.getByTestId('database-select');
        expect(select).toContainElement(screen.getByText(/Production DB/));
        expect(select).toContainElement(screen.getByText(/Staging DB/));
    });

    // -----------------------------------------------------------------------
    // Client-side validation
    // -----------------------------------------------------------------------

    it('shows validation error when submitting with empty query', async () => {
        const user = userEvent.setup();
        renderQueryForm();

        // Select a database but leave query empty
        await user.selectOptions(
            screen.getByTestId('database-select'),
            'profile-uuid-1',
        );
        await user.click(screen.getByTestId('submit-button'));

        expect(await screen.findByText(/please enter a query/i)).toBeInTheDocument();
        expect(mockStartQuery).not.toHaveBeenCalled();
    });

    it('shows validation error when no database is selected', async () => {
        const user = userEvent.setup();
        renderQueryForm();

        await user.type(screen.getByTestId('nl-query-input'), 'Show me revenue');
        await user.click(screen.getByTestId('submit-button'));

        // There will be a db-error alert
        const alerts = await screen.findAllByRole('alert');
        const dbAlert = alerts.find((el) =>
            el.textContent?.toLowerCase().includes('database') ||
            el.textContent?.toLowerCase().includes('select'),
        );
        expect(dbAlert).toBeTruthy();
        expect(mockStartQuery).not.toHaveBeenCalled();
    });

    it('disables submit button when query exceeds max length', () => {
        renderQueryForm();

        // Use fireEvent.change to avoid per-character userEvent overhead
        fireEvent.change(screen.getByTestId('nl-query-input'), {
            target: { value: 'x'.repeat(10_001) },
        });

        expect(screen.getByTestId('submit-button')).toBeDisabled();
    });

    // -----------------------------------------------------------------------
    // Successful submission
    // -----------------------------------------------------------------------

    it('shows loading state while submitting and success banner afterwards', async () => {
        const user = userEvent.setup();
        // Delay resolution to allow the loading state to appear
        let resolve!: (v: QueryStartResponse) => void;
        mockStartQuery.mockReturnValueOnce(
            new Promise<QueryStartResponse>((res) => {
                resolve = res;
            }),
        );

        renderQueryForm();

        await user.type(screen.getByTestId('nl-query-input'), 'Show me revenue');
        await user.selectOptions(screen.getByTestId('database-select'), 'profile-uuid-1');
        await user.click(screen.getByTestId('submit-button'));

        // Loading state must appear
        expect(screen.getByText(/processing/i)).toBeInTheDocument();
        expect(screen.getByTestId('submit-button')).toBeDisabled();

        // Resolve the request
        resolve(makeSuccessResponse());

        await waitFor(() =>
            expect(screen.getByTestId('submission-success')).toBeInTheDocument(),
        );
        expect(screen.queryByText(/processing/i)).not.toBeInTheDocument();
    });

    it('calls onConversationStarted with the returned conversation_id', async () => {
        const user = userEvent.setup();
        const onConversationStarted = vi.fn();
        mockStartQuery.mockResolvedValueOnce(makeSuccessResponse());

        renderQueryForm({ onConversationStarted });

        await user.type(screen.getByTestId('nl-query-input'), 'Show me revenue');
        await user.selectOptions(screen.getByTestId('database-select'), 'profile-uuid-1');
        await user.click(screen.getByTestId('submit-button'));

        await waitFor(() =>
            expect(onConversationStarted).toHaveBeenCalledWith(
                'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',
            ),
        );
    });

    it('persists conversation_id to sessionStorage on success (FR-90)', async () => {
        const user = userEvent.setup();
        mockStartQuery.mockResolvedValueOnce(makeSuccessResponse());

        renderQueryForm();

        await user.type(screen.getByTestId('nl-query-input'), 'Show me revenue');
        await user.selectOptions(screen.getByTestId('database-select'), 'profile-uuid-1');
        await user.click(screen.getByTestId('submit-button'));

        await waitFor(() => {
            expect(sessionStorage.getItem('sequelspeak_conversation_id')).toBe(
                'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',
            );
        });
    });

    it('sends correct request payload to the API', async () => {
        const user = userEvent.setup();
        mockStartQuery.mockResolvedValueOnce(makeSuccessResponse());

        renderQueryForm({ activeConnectionProfileId: 'profile-uuid-2' });

        // Use fireEvent.change to set the value directly (avoids per-char spacing)
        fireEvent.change(screen.getByTestId('nl-query-input'), {
            target: { value: '  Show me revenue  ' },
        });
        await user.selectOptions(screen.getByTestId('database-select'), 'profile-uuid-2');
        await user.click(screen.getByTestId('submit-button'));

        await waitFor(() => expect(mockStartQuery).toHaveBeenCalledOnce());

        const payload = mockStartQuery.mock.calls[0][0];
        expect(payload.query).toBe('Show me revenue'); // trimmed
        expect(payload.database_id).toBe('profile-uuid-2');
    });

    it('pauses and prompts for password when switching to a different profile', async () => {
        const user = userEvent.setup();
        mockTestConnection.mockResolvedValueOnce({ status: 'success', message: 'ok' });
        mockStartQuery.mockResolvedValueOnce(makeSuccessResponse());

        renderQueryForm({ activeConnectionProfileId: 'profile-uuid-1' });

        await user.type(screen.getByTestId('nl-query-input'), 'Show me revenue');
        await user.selectOptions(screen.getByTestId('database-select'), 'profile-uuid-2');
        await user.click(screen.getByTestId('submit-button'));

        expect(await screen.findByRole('dialog')).toBeInTheDocument();
        expect(mockStartQuery).not.toHaveBeenCalled();

        await user.type(screen.getByLabelText(/database password/i), 'new-secret');
        await user.click(screen.getByRole('button', { name: /connect/i }));

        await waitFor(() => {
            expect(mockTestConnection).toHaveBeenCalledWith(
                undefined,
                'test-token',
                undefined,
                'profile-uuid-2',
                'new-secret',
            );
            expect(mockStartQuery).toHaveBeenCalledOnce();
        });
    });

    // -----------------------------------------------------------------------
    // Error handling
    // -----------------------------------------------------------------------

    it('displays API error message when submission fails', async () => {
        const user = userEvent.setup();
        const { ApiError } = await import('../../services/api/errors');
        mockStartQuery.mockRejectedValueOnce(
            new ApiError('Database connection refused', 'CONNECTION_ERROR', 503),
        );

        renderQueryForm();

        await user.type(screen.getByTestId('nl-query-input'), 'Show me revenue');
        await user.selectOptions(screen.getByTestId('database-select'), 'profile-uuid-1');
        await user.click(screen.getByTestId('submit-button'));

        expect(await screen.findByTestId('submission-error')).toBeInTheDocument();
        expect(screen.getByTestId('submission-error')).toHaveTextContent(
            'Database connection refused',
        );
    });

    it('does not show success banner when submission fails', async () => {
        const user = userEvent.setup();
        const { ApiError } = await import('../../services/api/errors');
        mockStartQuery.mockRejectedValueOnce(new ApiError('fail', 'NETWORK_ERROR'));

        renderQueryForm();

        await user.type(screen.getByTestId('nl-query-input'), 'Show me revenue');
        await user.selectOptions(screen.getByTestId('database-select'), 'profile-uuid-1');
        await user.click(screen.getByTestId('submit-button'));

        await waitFor(() =>
            expect(screen.getByTestId('submission-error')).toBeInTheDocument(),
        );
        expect(screen.queryByTestId('submission-success')).not.toBeInTheDocument();
    });
});
