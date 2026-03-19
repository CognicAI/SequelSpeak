/**
 * ClarificationPromptCard — inline card for answering pending clarification questions.
 *
 * Rendered below the conversation thread when status === 'clarification_needed'.
 * Supports multi-question lists (one text input per question).
 */

import { useState, useRef, useEffect, type FormEvent } from 'react';
import { Send, HelpCircle } from 'lucide-react';
import { cn } from '../lib/utils';

interface ClarificationPromptCardProps {
    questions: string[];
    isSubmitting: boolean;
    onSubmit: (answers: string[]) => void;
    className?: string;
}

export function ClarificationPromptCard({
    questions,
    isSubmitting,
    onSubmit,
    className,
}: ClarificationPromptCardProps) {
    const [answers, setAnswers] = useState<string[]>(() => questions.map(() => ''));
    const firstInputRef = useRef<HTMLInputElement>(null);

    const [prevQuestions, setPrevQuestions] = useState(questions);
    
    // Derive answers state from questions (better than calling setState in useEffect)
    if (questions !== prevQuestions) {
        setPrevQuestions(questions);
        setAnswers(questions.map(() => ''));
    }

    // Focus first input whenever questions change
    useEffect(() => {
        const timer = setTimeout(() => firstInputRef.current?.focus(), 50);
        return () => clearTimeout(timer);
    }, [questions]);

    const allAnswered = answers.every(a => a.trim().length > 0);

    const handleSubmit = (e: FormEvent) => {
        e.preventDefault();
        if (!allAnswered || isSubmitting) return;
        onSubmit(answers);
    };

    const updateAnswer = (index: number, value: string) => {
        setAnswers(prev => prev.map((a, i) => (i === index ? value : a)));
    };

    return (
        <div
            className={cn(
                'rounded-2xl border border-amber-500/20 bg-amber-500/5 backdrop-blur-sm p-4',
                className,
            )}
            data-testid="clarification-prompt-card"
        >
            <div className="flex items-center gap-2 mb-3">
                <HelpCircle className="w-4 h-4 text-amber-400 shrink-0" aria-hidden />
                <p className="text-xs font-semibold text-amber-400 uppercase tracking-wide">
                    {questions.length === 1 ? 'Please clarify' : `${questions.length} clarifications needed`}
                </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-3" noValidate>
                {questions.map((q, i) => (
                    <div key={i} className="space-y-1.5">
                        <label
                            htmlFor={`clarification-answer-${i}`}
                            className="block text-sm text-gray-300"
                        >
                            {q}
                        </label>
                        <input
                            id={`clarification-answer-${i}`}
                            ref={i === 0 ? firstInputRef : undefined}
                            type="text"
                            value={answers[i]}
                            onChange={e => updateAnswer(i, e.target.value)}
                            disabled={isSubmitting}
                            placeholder="Your answer…"
                            required
                            aria-required="true"
                            className={cn(
                                'w-full px-3 py-2 rounded-lg text-sm text-white bg-white/5 border border-white/10',
                                'placeholder:text-gray-600 focus:outline-none focus:ring-2 focus:ring-amber-500/40 focus:border-amber-500/40',
                                'disabled:opacity-50 disabled:cursor-not-allowed',
                            )}
                        />
                    </div>
                ))}

                <button
                    type="submit"
                    disabled={!allAnswered || isSubmitting}
                    data-testid="clarification-submit"
                    className={cn(
                        'w-full flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition-all',
                        'focus:outline-none focus:ring-2 focus:ring-amber-500/40',
                        allAnswered && !isSubmitting
                            ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30 hover:bg-amber-500/30'
                            : 'bg-white/5 text-gray-500 border border-white/10 cursor-not-allowed',
                    )}
                >
                    <Send className="w-3.5 h-3.5" aria-hidden />
                    {isSubmitting ? 'Submitting…' : 'Submit answers'}
                </button>
            </form>
        </div>
    );
}
