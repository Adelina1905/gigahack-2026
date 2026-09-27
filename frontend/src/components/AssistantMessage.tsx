import { useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useI18n } from "../i18n/context";
import { safeHttpUrl } from "./sources/safeLink";
import type { ChatMessage } from "../types/chat";
import { CityEmblem } from "./brand/Landmarks";
import CitationPills from "./CitationPills";
import type { SpeechState } from "../hooks/useVoiceMode";
import { notFoundReason } from "../utils/unanswered";

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
  // Sends a clarification choice as the next prompt; without it the choices are disabled.
  onChoose?: (label: string) => void;
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
const citationMarkdown = (text: string) => text.replace(/\[S(\d+)\]/g, "[$1](citation:S$1)");

// The gateway lists clarification choices as trailing "- label" lines, which are
// shown as buttons instead.
const stripChoiceLines = (text: string, choices: string[]) => {
  const lines = text.split("\n");
  while (lines.length > 1 && choices.some(choice => lines.at(-1)!.trim() === `- ${choice.trim()}`)) lines.pop();
  return lines.join("\n").trimEnd();
};

function NotFoundIcon() {
  return (
    <svg viewBox="0 0 24 24" className="mt-0.5 h-5 w-5 shrink-0 text-primary" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="10.5" cy="10.5" r="6.5" />
      <path d="M15.5 15.5 20 20M8.5 8.5l4 4M12.5 8.5l-4 4" />
    </svg>
  );
}

function WarningIcon() {
  return (
    <svg viewBox="0 0 24 24" className="mt-0.5 h-4 w-4 shrink-0 text-accent-dark" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 3 2 20h20L12 3Z" />
      <path d="M12 10v4M12 17h.01" />
    </svg>
  );
}

interface AnswerMarkdownProps {
  message: ChatMessage;
  content: string;
  activeSourceIndex: number | null;
  sourcePanelId: string;
  onSelectSource?: (message: ChatMessage, index: number, trigger: HTMLButtonElement) => void;
}

function AnswerMarkdown({ message, content, activeSourceIndex, sourcePanelId, onSelectSource }: AnswerMarkdownProps) {
  const { t } = useI18n();
  return (
    <Markdown remarkPlugins={[remarkGfm]} skipHtml disallowedElements={["img"]}
      urlTransform={url => url.startsWith("citation:") ? url : (safeHttpUrl(url) ?? "")}
      components={{
        a: ({ href, children }) => {
          if (href?.startsWith("citation:S")) {
            const citationId = href.slice("citation:".length);
            const numericIndex = Number.parseInt(citationId.slice(1), 10) - 1;
            const sourceIndex = message.sources?.findIndex(source => source.id === citationId) ?? -1;
            const index = sourceIndex >= 0 ? sourceIndex : numericIndex;
            const source = message.sources?.[index];
            if (!source || !onSelectSource) return <span className="text-text-subtle">[{children}]</span>;
            return (
              <sup className="mx-0.5 inline-block align-super leading-none">
                <button
                  type="button"
                  aria-label={`${t.message.sourcePosition(index + 1, message.sources!.length)}: ${source.title}`}
                  aria-haspopup="dialog"
                  aria-expanded={activeSourceIndex === index}
                  aria-controls={sourcePanelId}
                  onClick={(event) => onSelectSource(message, index, event.currentTarget)}
                  className={`cursor-pointer rounded-sm px-1 py-0.5 text-[0.7rem] font-bold underline decoration-1 underline-offset-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${
                    activeSourceIndex === index ? "bg-primary text-text-inverted" : "bg-primary-50 text-primary hover:bg-primary-100"
                  }`}
                >
                  {children}
                </button>
              </sup>
            );
          }
          const url = safeHttpUrl(href);
          return url ? <a href={url} target="_blank" rel="noopener noreferrer" className="cursor-pointer text-primary underline hover:text-primary-dark">{children}</a> : <span>{children}</span>;
        },
        p: ({ children }) => <p className="mb-2 last:mb-0 whitespace-pre-wrap">{children}</p>,
        strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
        ul: ({ children }) => <ul className="list-disc pl-5">{children}</ul>,
        ol: ({ children }) => <ol className="list-decimal pl-5">{children}</ol>,
        pre: ({ children }) => <pre className="overflow-x-auto rounded-sm bg-background-secondary p-2">{children}</pre>,
      }}>{citationMarkdown(content)}</Markdown>
  );
}

function AssistantMessage({ message, isTyping = false, onCopy, onRegenerate,
  onToggleSpeech, speechState = "idle", activeSourceIndex = null,
  sourcePanelId = "source-preview-panel", onSelectSource, onChoose }: AssistantMessageProps) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  const pending = message?.generationStatus === "PENDING";
  const failed = message?.generationStatus === "FAILED";
  const missing = message ? notFoundReason(message) : null;
  const contradiction = message?.replyStatus === "CONTRADICTION" || message?.reason === "CONFLICTING_DOCUMENTS";
  const choices = message?.replyStatus === "NEEDS_CLARIFICATION" ? message.clarificationChoices ?? [] : [];
  const displayed = message ? (choices.length > 0 ? stripChoiceLines(message.content, choices) : message.content) : "";

  const handleCopy = async () => {
    if (!message) return;
    const text = stripCitationMarkers(message.content);
    if (onCopy) onCopy(text);
    else await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  // A reply without an answer cites nothing, so its markers are dropped too.
  const answer = message && <AnswerMarkdown message={message} content={missing ? stripCitationMarkers(displayed) : displayed}
    activeSourceIndex={activeSourceIndex} sourcePanelId={sourcePanelId} onSelectSource={onSelectSource} />;

  return (
    <div className="group flex items-start gap-3.5">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[5px] bg-primary-50 text-primary">
        <CityEmblem className="h-6 w-6" />
      </div>

      <div className="flex min-w-0 max-w-[calc(100%-2.875rem)] flex-col gap-1.5 sm:max-w-[92%]">
        <div className={`break-words rounded-[6px] border px-4 py-3.5 text-[0.9375rem] leading-7 text-text sm:px-5 ${missing
          ? "border-dashed border-primary-200 bg-primary-50/40"
          : "border-border/60 bg-background shadow-[0_1px_2px_rgba(0,58,141,0.025)]"}`}>
          {isTyping || !message ? (
            <TypingDots />
          ) : (
            <>
              {message.mode === "demo" && <p className="mb-2 text-xs font-semibold text-text-muted">{t.message.demo}</p>}
              {contradiction && !missing && (
                <p role="note" className="mb-3 flex items-start gap-2 rounded-sm border-l-4 border-accent bg-accent/15 px-3 py-2 text-sm font-semibold leading-snug text-text">
                  <WarningIcon />{t.message.contradiction}
                </p>
              )}
              {missing ? (
                <div role="note" className="flex items-start gap-3">
                  <NotFoundIcon />
                  <div className="min-w-0 flex-1">
                    <p className="font-serif text-[1.0625rem] leading-snug text-primary">{t.message.notFound[missing]}</p>
                    {displayed && <div className="mt-1.5 text-sm leading-6 text-text-muted">{answer}</div>}
                    <p className="mt-2 text-xs text-text-subtle">
                      {missing === "OUT_OF_SCOPE" ? t.message.outOfScopeHint : t.message.notFoundHint}
                    </p>
                  </div>
                </div>
              ) : displayed && answer}
              {choices.length > 0 && (
                <div role="group" aria-label={t.message.clarificationChoices} className="mt-3 flex flex-wrap gap-2">
                  {choices.map(label => (
                    <button
                      key={label}
                      type="button"
                      disabled={!onChoose}
                      onClick={() => onChoose?.(label)}
                      className="min-h-9 cursor-pointer rounded-sm border border-primary-200 bg-background px-3 py-1.5 text-left text-sm font-medium leading-snug text-primary transition-colors hover:border-primary hover:bg-primary-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:cursor-default disabled:border-border disabled:text-text-subtle disabled:hover:bg-background"
                    >
                      {label}
                    </button>
                  ))}
                </div>
              )}
              {!missing && message.sources && message.sources.length > 0 && onSelectSource && (
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
          <div className="flex gap-1 opacity-100 transition-opacity duration-200 sm:opacity-0 sm:group-hover:opacity-100 sm:focus-within:opacity-100 motion-reduce:transition-none">
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
