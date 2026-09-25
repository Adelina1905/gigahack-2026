import { useState } from "react";
import type { ChatMessage } from "../types/chat";
import SourceList from "./sources/SourceList";

interface AssistantMessageProps {
  message?: ChatMessage;
  isTyping?: boolean;
  onCopy?: (content: string) => void;
  onRegenerate?: (id: string) => void;
}

function TypingDots() {
  return (
    <div className="flex items-center gap-1 py-1.5" aria-label="Assistant is typing">
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          className="h-2 w-2 animate-bounce rounded-full bg-text-subtle"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </div>
  );
}

function AssistantMessage({ message, isTyping = false, onCopy, onRegenerate }: AssistantMessageProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (!message) return;
    if (onCopy) onCopy(message.content);
    else await navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="group flex items-start gap-3">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-border bg-background-secondary text-text-muted">
        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor">
          <path d="M12 2l2.4 7.6L22 12l-7.6 2.4L12 22l-2.4-7.6L2 12l7.6-2.4z" />
        </svg>
      </div>

      <div className="flex max-w-[75%] flex-col gap-1">
        <div className="whitespace-pre-wrap break-words rounded-2xl rounded-tl-sm border border-border bg-background px-4 py-2.5 text-base text-text">
          {isTyping || !message ? (
            <TypingDots />
          ) : (
            <>
              {message.content}
              {message.sources && <SourceList sources={message.sources} />}
            </>
          )}
        </div>

        {message && !isTyping && (
          <div className="flex gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
            <button
              type="button"
              onClick={handleCopy}
              className="rounded-md px-2 py-1 text-xs text-text-subtle hover:bg-background-secondary hover:text-text-muted"
            >
              {copied ? "Copied" : "Copy"}
            </button>
            {onRegenerate && (
              <button
                type="button"
                onClick={() => onRegenerate(message.id)}
                className="rounded-md px-2 py-1 text-xs text-text-subtle hover:bg-background-secondary hover:text-text-muted"
              >
                Regenerate
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default AssistantMessage;
