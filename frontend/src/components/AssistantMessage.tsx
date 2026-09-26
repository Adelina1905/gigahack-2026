import { useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { safeHttpUrl } from "./sources/safeLink";
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
  const pending = message?.generationStatus === "PENDING";
  const failed = message?.generationStatus === "FAILED";
  const definitions = message?.mode ? (message.sources ?? []).map((source, index) => {
    const url = safeHttpUrl(source.link);
    return url ? `[S${index + 1}]: <${url}>` : "";
  }).join("\n") : "";

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
        <div className="break-words rounded-2xl rounded-tl-sm border border-border bg-background px-4 py-2.5 text-base text-text">
          {isTyping || !message ? (
            <TypingDots />
          ) : (
            <>
              {message.mode === "demo" && <p className="mb-2 text-xs font-semibold text-text-muted">Demo response</p>}
              {message.content && <Markdown remarkPlugins={[remarkGfm]} skipHtml disallowedElements={["img"]}
                components={{
                  a: ({ href, children }) => {
                    const url = safeHttpUrl(href);
                    return url ? <a href={url} target="_blank" rel="noopener noreferrer" className="text-primary underline">{children}</a> : <span>{children}</span>;
                  },
                  p: ({ children }) => <p className="mb-2 last:mb-0 whitespace-pre-wrap">{children}</p>,
                  ul: ({ children }) => <ul className="list-disc pl-5">{children}</ul>,
                  ol: ({ children }) => <ol className="list-decimal pl-5">{children}</ol>,
                  pre: ({ children }) => <pre className="overflow-x-auto rounded bg-background-secondary p-2">{children}</pre>,
                }}>{`${message.content}\n\n${definitions}`}</Markdown>}
              {message.sources && <SourceList sources={message.sources} />}
              {pending && <p role="status" className="mt-2 text-sm text-text-muted">Waiting for response…</p>}
              {failed && <p className="mt-2 text-sm text-danger">Response failed{message.content ? ". Previous answer kept." : ""}
                {onRegenerate && <> · <button type="button" onClick={() => onRegenerate(message.id)} className="underline">Retry</button></>}
              </p>}
            </>
          )}
        </div>

        {message && message.content && !isTyping && !pending && (
          <div className="flex gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
            <button
              type="button"
              onClick={handleCopy}
              className="rounded-md px-2 py-1 text-xs text-text-subtle hover:bg-background-secondary hover:text-text-muted"
            >
              {copied ? "Copied" : "Copy"}
            </button>
            {onRegenerate && !failed && (
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
