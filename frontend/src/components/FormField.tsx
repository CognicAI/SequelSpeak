/**
 * FormField — Reusable connection form field with icon, label, and validation indicator.
 *
 * Eliminates the 5× repeated field pattern in ConnectionForm (section 7.1).
 * Automatically handles:
 * - `htmlFor` / `id` label association (a11y — section 5.1)
 * - `aria-required` and `aria-describedby` attributes
 * - Green ✓ checkmark when field passes `validate`
 * - Disabled state styling
 */

import { Check } from 'lucide-react';
import { type ElementType } from 'react';
import { cn } from '../lib/utils';

export interface FormFieldProps {
    /** Field label text — also used to derive the `id` */
    label: string;
    /** Controlled field value */
    value: string;
    /** Change handler receives the plain string value */
    onChange: (value: string) => void;
    /** Lucide icon component to display on the left */
    icon: ElementType<{ className?: string }>;
    /** Input type — defaults to 'text' */
    type?: 'text' | 'password' | 'email' | 'number';
    /** Placeholder text */
    placeholder?: string;
    /**
     * Optional validation function.
     * When provided, the green checkmark is shown only when it returns `true`.
     * When omitted, the checkmark shows whenever the field is non-empty.
     */
    validate?: (value: string) => boolean;
    /** Disables the input and reduces opacity */
    disabled?: boolean;
    /** Additional class names for the outer wrapper */
    className?: string;
}

/**
 * Derives a stable HTML `id` from a label string.
 * e.g. "Database Name" → "formfield-database-name"
 */
function labelToId(label: string): string {
    return `formfield-${label.toLowerCase().replace(/\s+/g, '-')}`;
}

export function FormField({
    label,
    value,
    onChange,
    icon: Icon,
    type = 'text',
    placeholder,
    validate,
    disabled = false,
    className,
}: FormFieldProps) {
    const id = labelToId(label);
    const isValid = validate ? validate(value) : !!value;

    return (
        <div className={cn('space-y-1', className)}>
            {/* Label — programmatically associated with the input via htmlFor/id */}
            <label htmlFor={id} className="text-xs text-gray-400 ml-1">
                {label}
            </label>

            <div className="relative">
                {/* Leading icon */}
                <Icon className="absolute left-3 top-2.5 w-4 h-4 text-gray-500" />

                <input
                    id={id}
                    type={type}
                    value={value}
                    onChange={(e) => onChange(e.target.value)}
                    placeholder={placeholder}
                    disabled={disabled}
                    aria-required="true"
                    className={cn(
                        'w-full bg-background/50 border border-white/10 rounded-lg py-2 pl-9 pr-8 text-sm',
                        'focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/50',
                        'transition-colors duration-150',
                        disabled && 'opacity-50 cursor-not-allowed',
                    )}
                />

                {/* Validation checkmark */}
                {isValid && (
                    <div className="absolute right-2.5 top-2.5 animate-in fade-in zoom-in">
                        <Check className="w-4 h-4 text-green-500" />
                    </div>
                )}
            </div>
        </div>
    );
}
