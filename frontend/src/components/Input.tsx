import { useEffect, useRef, useState, type KeyboardEvent } from "react";

interface ChatInputProps {
  onSend: (text: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

const MAX_HEIGHT_PX = 160; // ~6 lines

function ChatInput({ onSend, disabled = false, placeholder = "Ask something…" }: ChatInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const canSend = value.trim().length > 0 && value.trim().length <= 8000 && !disabled;

  // Grow with content up to MAX_HEIGHT_PX, then scroll.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT_PX)}px`;
  }, [value]);

  const submit = () => {
    if (!canSend) return;
    onSend(value.trim());
    setValue("");
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="flex items-end gap-2 rounded-4xl border border-border bg-background px-4 py-2 shadow-sm transition-colors focus-within:border-border-strong">
      <textarea
        ref={textareaRef}
        rows={1}
        maxLength={8000}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        className="max-h-40 flex-1 resize-none bg-transparent py-1.5 text-base text-text placeholder:text-text-subtle focus:outline-none"
      />
      <button
        type="button"
        onClick={submit}
        disabled={!canSend}
        aria-label="Send message"
        className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition-colors ${
          canSend
            ? "bg-primary text-text-inverted hover:bg-primary-dark"
            : "cursor-not-allowed bg-background-secondary text-text-subtle"
        }`}
      >
        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 19V5M5 12l7-7 7 7" />
        </svg>
      </button>
    </div>
  );
}

export default ChatInput;
