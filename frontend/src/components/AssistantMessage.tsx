import { useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useI18n } from "../i18n/context";
import { safeHttpUrl } from "./sources/safeLink";
import type { ChatMessage } from "../types/chat";
import { CityEmblem } from "./brand/Landmarks";
import CitationPills from "./CitationPills";
import type { SpeechState } from "../hooks/useVoiceMode";

interface AssistantMessageProps {
  message?: ChatMessage;
  isTyping?: boolean;
  onCopy?: (content: string) => void;
  onRegenerate?: (id: string) => void;
  onToggleSpeech?: (message: ChatMessage) => void;
  speechState?: SpeechState;
  activeSourceIndex?: number | null;
  sourcePanelId?: string;
  onSelectSource?: (message: ChatMessage, index: number, trigger: HTMLButtonElement) => void;
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
// are shown as pills under the text instead. The rest is rendered as Markdown.
const stripCitationMarkers = (text: string) => text.replace(/[ \t]*\[S\d+\]/g, "");

function AssistantMessage({ message, isTyping = false, onCopy, onRegenerate,
  onToggleSpeech, speechState = "idle", activeSourceIndex = null,
  sourcePanelId = "source-preview-panel", onSelectSource }: AssistantMessageProps) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  const pending = message?.generationStatus === "PENDING";
  const failed = message?.generationStatus === "FAILED";

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
        <div className="break-words rounded-sm border border-border bg-background px-4 py-3 text-[0.9375rem] leading-relaxed text-text shadow-[0_1px_2px_rgb(0_0_0/0.04)]">
          {isTyping || !message ? (
            <TypingDots />
          ) : (
            <>
              {message.mode === "demo" && <p className="mb-2 text-xs font-semibold text-text-muted">{t.message.demo}</p>}
              {message.content && <Markdown remarkPlugins={[remarkGfm]} skipHtml disallowedElements={["img"]}
                components={{
                  a: ({ href, children }) => {
                    const url = safeHttpUrl(href);
                    return url ? <a href={url} target="_blank" rel="noopener noreferrer" className="text-primary underline">{children}</a> : <span>{children}</span>;
                  },
                  p: ({ children }) => <p className="mb-2 last:mb-0 whitespace-pre-wrap">{children}</p>,
                  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
                  ul: ({ children }) => <ul className="list-disc pl-5">{children}</ul>,
                  ol: ({ children }) => <ol className="list-decimal pl-5">{children}</ol>,
                  pre: ({ children }) => <pre className="overflow-x-auto rounded-sm bg-background-secondary p-2">{children}</pre>,
                }}>{stripCitationMarkers(message.content)}</Markdown>}
              {message.sources && message.sources.length > 0 && onSelectSource && (
                <CitationPills
                  sources={message.sources}
                  activeIndex={activeSourceIndex}
                  controlsId={sourcePanelId}
                  onSelect={(index, trigger) => onSelectSource(message, index, trigger)}
                />
              )}
              {pending && <p role="status" className="mt-2 text-sm text-text-muted">{t.message.pending}</p>}
              {failed && <p className="mt-2 text-sm text-danger">{message.content ? t.message.generationFailedKept : t.message.generationFailed}
                {onRegenerate && <> · <button type="button" onClick={() => onRegenerate(message.id)} className="underline">{t.message.retry}</button></>}
              </p>}
            </>
          )}
        </div>

        {message && message.content && !isTyping && !pending && (
          <div className="flex gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
            <button
              type="button"
              onClick={handleCopy}
              className="rounded-sm px-2 py-1 text-xs text-text-subtle hover:bg-background hover:text-primary"
            >
              {copied ? t.message.copied : t.message.copy}
            </button>
            {onToggleSpeech && !failed && (
              <button
                type="button"
                onClick={() => onToggleSpeech(message)}
                disabled={speechState === "loading"}
                aria-label={speechState === "playing" ? t.voice.stopPlayback : t.voice.play}
                className="rounded-sm px-2 py-1 text-xs text-text-subtle hover:bg-background hover:text-primary disabled:opacity-50"
              >
                {speechState === "loading" ? t.voice.loadingAudio
                  : speechState === "playing" ? t.voice.stopPlayback : t.voice.play}
              </button>
            )}
            {onRegenerate && !failed && (
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
