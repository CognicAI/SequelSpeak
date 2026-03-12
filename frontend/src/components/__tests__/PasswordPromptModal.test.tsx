import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PasswordPromptModal } from '../PasswordPromptModal';

describe('PasswordPromptModal', () => {
    const defaultProps = {
        isOpen: true,
        onClose: vi.fn(),
        onSubmit: vi.fn().mockResolvedValue(undefined),
        profileName: 'Test Profile',
    };

    it('renders with correct ARIA attributes', () => {
        render(<PasswordPromptModal {...defaultProps} />);
        
        const dialog = screen.getByRole('dialog');
        expect(dialog).toHaveAttribute('aria-modal', 'true');
        expect(dialog).toHaveAttribute('aria-labelledby', 'modal-title');
        
        const title = screen.getByText('Credentials Required');
        expect(title).toHaveAttribute('id', 'modal-title');
    });

    it('calls onClose when Escape key is pressed', () => {
        render(<PasswordPromptModal {...defaultProps} />);
        
        fireEvent.keyDown(window, { key: 'Escape' });
        expect(defaultProps.onClose).toHaveBeenCalled();
    });

    it('traps focus when tabbing', async () => {
        render(<PasswordPromptModal {...defaultProps} />);
        
        // Focusable elements in order: Close(X), Input, Cancel
        // Connect button is disabled initially so not focusable
        const closeBtn = screen.getByRole('button', { name: 'Close modal' });
        const cancelBtn = screen.getByRole('button', { name: 'Cancel' });

        // Start at first element
        closeBtn.focus();
        expect(document.activeElement).toBe(closeBtn);

        // Tab from last to first
        cancelBtn.focus();
        fireEvent.keyDown(window, { key: 'Tab' });
        expect(document.activeElement).toBe(closeBtn);

        // Shift+Tab from first to last
        closeBtn.focus();
        fireEvent.keyDown(window, { key: 'Tab', shiftKey: true });
        expect(document.activeElement).toBe(cancelBtn);
    });

    it('does not render when isOpen is false', () => {
        render(<PasswordPromptModal {...defaultProps} isOpen={false} />);
        expect(screen.queryByRole('dialog')).toBeNull();
    });
});
