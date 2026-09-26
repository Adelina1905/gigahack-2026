import { useState } from "react";
import { useI18n } from "../i18n/context";
import type { ChatMessage } from "../types/chat";
import { CityEmblem } from "./brand/Landmarks";
import SourceList from "./sources/SourceList";
import CitationPills from "./CitationPills";

interface AssistantMessageProps {
  message?: ChatMessage;
  isTyping?: boolean;
  onCopy?: (content: string) => void;
  onRegenerate?: (id: string) => void;
}

function TypingDots() {
  const { t } = useI18n();
  return (
    <div className="flex items-center gap-1 py-1.5" aria-label={t.message.typing}>
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

// The RAG answer ends each claim with markers like "[S1] [S2]"; the cited documents
// are shown as pills under the text instead.
const stripCitationMarkers = (text: string) => text.replace(/[ \t]*\[S\d+\]/g, "");

// Only **bold** is supported; an unmatched "**" stays as literal text.
function renderBold(text: string) {
  return text.split(/\*\*(.+?)\*\*/gs).map((part, i) =>
    i % 2 === 1 ? (
      <strong key={i} className="font-semibold">
        {part}
      </strong>
    ) : (
      part
    ),
  );
}

function AssistantMessage({ message, isTyping = false, onCopy, onRegenerate }: AssistantMessageProps) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (!message) return;
    const text = stripCitationMarkers(message.content);
    if (onCopy) onCopy(text);
    else await navigator.clipboard.writeText(text);
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
              {renderBold(stripCitationMarkers(message.content))}
              {message.sources && <CitationPills sources={message.sources} />}
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
              {copied ? t.message.copied : t.message.copy}
            </button>
            {onRegenerate && (
              <button
                type="button"
                onClick={() => onRegenerate(message.id)}
                className="rounded-sm px-2 py-1 text-xs text-text-subtle hover:bg-background hover:text-primary"
              >
                {t.message.regenerate}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default AssistantMessage;
