import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ConnectionStatusBanner } from '../ConnectionStatusBanner';

describe('ConnectionStatusBanner', () => {
    beforeEach(() => {
        vi.useFakeTimers();
    });

    it('renders nothing when status is "unknown"', () => {
        const { container } = render(<ConnectionStatusBanner status="unknown" />);
        expect(container.firstChild).toBeNull();
    });

    it('shows an alert when status is "disconnected"', () => {
        render(<ConnectionStatusBanner status="disconnected" />);
        const alert = screen.getByRole('alert');
        expect(alert).toBeInTheDocument();
    });

    it('shows connected message when status is "connected"', () => {
        render(<ConnectionStatusBanner status="connected" />);
        const alert = screen.getByRole('alert');
        expect(alert).toBeInTheDocument();
    });

    it('auto-dismisses after reconnection', async () => {
        vi.useRealTimers();
        const onDismiss = vi.fn();

        render(
            <ConnectionStatusBanner
                status="connected"
                onDismiss={onDismiss}
                autoDismissDelay={100}
            />,
        );

        await waitFor(() => expect(onDismiss).toHaveBeenCalled(), { timeout: 500 });
    });

    it('does not auto-dismiss while disconnected', async () => {
        const onDismiss = vi.fn();
        render(<ConnectionStatusBanner status="disconnected" onDismiss={onDismiss} />);

        vi.advanceTimersByTime(5000);
        expect(onDismiss).not.toHaveBeenCalled();
    });

    it('calls onDismiss when dismiss button is clicked (disconnected state)', async () => {
        // Use real timers for this test — userEvent.click() is async and doesn't work with fake timers
        vi.useRealTimers();
        const onDismiss = vi.fn();
        render(<ConnectionStatusBanner status="disconnected" onDismiss={onDismiss} />);

        const closeBtn = screen.getByRole('button', { name: /dismiss/i });
        await userEvent.click(closeBtn);
        expect(onDismiss).toHaveBeenCalledOnce();
    });
});
