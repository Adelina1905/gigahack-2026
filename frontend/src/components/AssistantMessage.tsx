import { useState } from "react";
import type { ChatMessage } from "../types/chat";
import { CityEmblem } from "./brand/Landmarks";
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
          className="h-2 w-2 animate-bounce rounded-full bg-primary/60"
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
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-sm bg-primary text-text-inverted">
        <CityEmblem className="h-6 w-6" />
      </div>

      <div className="flex min-w-0 max-w-[85%] flex-col gap-1">
        <div className="whitespace-pre-wrap break-words rounded-sm border border-border bg-background px-4 py-3 text-[0.9375rem] leading-relaxed text-text shadow-[0_1px_2px_rgb(0_0_0/0.04)]">
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
              className="rounded-sm px-2 py-1 text-xs text-text-subtle hover:bg-background hover:text-primary"
            >
              {copied ? "Copied" : "Copy"}
            </button>
            {onRegenerate && (
              <button
                type="button"
                onClick={() => onRegenerate(message.id)}
                className="rounded-sm px-2 py-1 text-xs text-text-subtle hover:bg-background hover:text-primary"
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
