import { useEffect, useRef, useState } from "react";
import { useI18n } from "../i18n/context";
import type { ErrorKey } from "../i18n/messages";
import type { ChatMessage } from "../types/chat";
import ChatInput from "./Input";
import UserMessage from "./UserMessage";
import AssistantMessage from "./AssistantMessage";
import { Skyline } from "./brand/Landmarks";
import TitleRule from "./brand/TitleRule";
import SupportNotice from "./SupportNotice";
import { isUnanswered } from "../utils/unanswered";

interface ChatWindowProps {
  // Switching chats jumps to the bottom instead of smooth-scrolling through history.
  chatId?: string | null;
  messages: ChatMessage[];
  isTyping: boolean;
  isLoading?: boolean;
  onSend: (text: string) => void;
  onRetry?: (id: string) => void;
  onRegenerate?: (id: string) => void;
  error?: ErrorKey | null;
  onDismissError?: () => void;
}


function WelcomePanel({ onSend }: { onSend: (text: string) => void }) {
  const { t } = useI18n();

  return (
    <div className="flex min-h-full flex-col justify-center gap-4 py-2">
      {/* Modelled on the blue "Ședința PMC" tile of chisinau.md. */}
      <section className="relative overflow-hidden rounded-sm bg-primary px-5 pt-5 pb-20 text-text-inverted sm:px-8 sm:pt-6 sm:pb-28">
        <span
          aria-hidden="true"
          className="pointer-events-none absolute -top-28 -right-24 h-80 w-80 rounded-full bg-primary-dark/60"
        />
        <div className="relative">
          <p className="text-sm font-medium text-accent">{t.welcome.eyebrow}</p>
          <h2 className="mt-2 font-serif text-[1.75rem] leading-tight sm:text-4xl">{t.welcome.title}</h2>
          <TitleRule tone="light" className="mt-3 sm:mt-4" />
          <p className="mt-3 max-w-xl text-[0.9375rem] font-light leading-relaxed text-white/85 sm:mt-4 sm:text-base">
            {t.welcome.body}
          </p>
        </div>
        <Skyline
          preserveAspectRatio="xMidYMax meet"
          className="pointer-events-none absolute inset-x-0 bottom-0 h-16 w-full text-white/35 sm:h-24"
        />
      </section>

      {/* Topics the indexed municipal corpus actually covers. */}
      <div className="grid gap-3 sm:grid-cols-3">
        {t.welcome.suggestions.map(({ topic, question }) => (
          <button
            key={question}
            type="button"
            onClick={() => onSend(question)}
            className="group flex flex-col items-start gap-3 rounded-sm border border-border bg-background p-4 text-left transition hover:-translate-y-0.5 hover:border-primary-200 hover:shadow-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            <span className="rounded-sm border border-border-strong px-1.5 py-px text-[11px] font-medium text-text-muted">
              {topic}
            </span>
            <span className="font-serif text-[1.0625rem] leading-snug text-text">{question}</span>
            <span className="mt-auto inline-flex items-center gap-2 pt-1 text-sm font-medium text-primary">
              {t.welcome.ask}
              <svg
                viewBox="0 0 22 16"
                aria-hidden="true"
                className="h-3.5 w-5 text-accent transition-transform group-hover:translate-x-1"
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M2 8h18M14 2l6 6-6 6" />
              </svg>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

function ChatWindow({
  chatId = null,
  messages,
  isTyping,
  isLoading = false,
  onSend,
  onRetry,
  onRegenerate,
  error,
  onDismissError,
}: ChatWindowProps) {
  const { t } = useI18n();
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrolledRef = useRef({ chatId, hadMessages: false });

  useEffect(() => {
    const previous = scrolledRef.current;
    const jump = previous.chatId !== chatId || !previous.hadMessages;
    scrolledRef.current = { chatId, hadMessages: messages.length > 0 };
    bottomRef.current?.scrollIntoView({ behavior: jump ? "auto" : "smooth" });
  }, [chatId, messages, isTyping]);

  const isEmpty = messages.length === 0 && !isTyping;

  // Offer the support line when the latest reply couldn't answer; dismissing hides it for that reply only.
  const [dismissedNoticeId, setDismissedNoticeId] = useState<string | null>(null);
  const lastMessage = messages.at(-1);
  const noticeFor =
    !isTyping && lastMessage?.role === "assistant" && isUnanswered(lastMessage.content) ? lastMessage.id : null;

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto px-4 py-6">
        {isLoading ? (
          <div className="flex h-full items-center justify-center text-sm text-text-subtle">
            {t.chat.loading}
          </div>
        ) : isEmpty ? (
          <WelcomePanel onSend={onSend} />
        ) : (
          <div className="flex flex-col gap-5">
            {messages.map((m) =>
              m.role === "user" ? (
                <UserMessage key={m.id} message={m} onRetry={onRetry} />
              ) : (
                <AssistantMessage key={m.id} message={m} onRegenerate={onRegenerate} />
              ),
            )}
            {isTyping && <AssistantMessage isTyping />}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      <div className="flex flex-col gap-2 px-4 pb-4">
        {error && (
          <div
            role="alert"
            className="flex items-center justify-between gap-3 rounded-sm border border-danger bg-danger-light px-3 py-2 text-sm text-danger"
          >
            <span>{t.errors[error]}</span>
            {onDismissError && (
              <button
                type="button"
                onClick={onDismissError}
                aria-label={t.chat.dismissError}
                className="shrink-0 rounded-sm px-1.5 text-base leading-none hover:bg-background"
              >
                ×
              </button>
            )}
          </div>
        )}
        {noticeFor && noticeFor !== dismissedNoticeId && (
          <SupportNotice onDismiss={() => setDismissedNoticeId(noticeFor)} />
        )}
        <ChatInput onSend={onSend} disabled={isTyping} />
        <p className="text-center text-[11px] text-text-subtle">
          {t.chat.disclaimer}
        </p>
      </div>
    </div>
  );
}

export default ChatWindow;
