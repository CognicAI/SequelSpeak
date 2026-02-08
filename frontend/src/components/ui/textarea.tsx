import { forwardRef, useEffect, useRef, useImperativeHandle, type TextareaHTMLAttributes } from "react"

import { cn } from "@/lib/utils"

export interface TextareaProps
  extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  autoResize?: boolean
}

const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, autoResize = false, ...props }, ref) => {
    const textareaRef = useRef<HTMLTextAreaElement>(null)

    // Expose the internal ref to parent components
    useImperativeHandle(ref, () => textareaRef.current as HTMLTextAreaElement)

    const adjustHeight = () => {
      const textarea = textareaRef.current
      if (textarea && autoResize) {
        // Reset height to auto to get the correct scrollHeight
        textarea.style.height = 'auto'
        // Set height to scrollHeight to fit content
        textarea.style.height = `${textarea.scrollHeight}px`
      }
    }

    useEffect(() => {
      if (autoResize) {
        adjustHeight()
      }
    }, [props.value, autoResize])

    return (
      <textarea
        className={cn(
          "flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
          autoResize && "resize-none overflow-hidden",
          className
        )}
        ref={textareaRef}
        onInput={adjustHeight}
        {...props}
      />
    )
  }
)
Textarea.displayName = "Textarea"

export { Textarea }
