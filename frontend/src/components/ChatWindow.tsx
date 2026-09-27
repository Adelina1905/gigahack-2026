import { useEffect, useRef, useState, type ReactNode } from "react";
import { useI18n } from "../i18n/context";
import type { ErrorKey } from "../i18n/messages";
import type { ChatMessage } from "../types/chat";
import ChatInput from "./Input";
import UserMessage from "./UserMessage";
import AssistantMessage from "./AssistantMessage";
import { Skyline } from "./brand/Landmarks";
import TitleRule from "./brand/TitleRule";
import SupportNotice from "./SupportNotice";
import { isUnanswered, notFoundReason } from "../utils/unanswered";
import { useVoiceMode } from "../hooks/useVoiceMode";
import SourcePreview from "./sources/SourcePreview";

interface ChatWindowProps {
  // Switching chats jumps to the bottom instead of smooth-scrolling through history.
  chatId?: string | null;
  messages: ChatMessage[];
  isTyping: boolean;
  isLoading?: boolean;
  onSend: (text: string) => string | null;
  onRetry?: (id: string) => void;
  onRegenerate?: (id: string) => void;
  onTrackPlan?: () => void;
  error?: ErrorKey | null;
  onDismissError?: () => void;
  // The inline alert question (or its follow-up notice), shown just above the input.
  alertPrompt?: ReactNode;
}

const SOURCE_PANEL_ID = "source-preview-panel";

interface SourcePreviewSelection {
  messageId: string;
  sourceIndex: number;
  trigger: HTMLButtonElement | null;
}


function WelcomePanel({ onSend }: { onSend: (text: string) => void }) {
  const { t } = useI18n();

  return (
    <div className="mx-auto flex min-h-full w-full max-w-5xl flex-col justify-center gap-4 py-2">
      <section className="relative overflow-hidden rounded-[6px] border border-border/60 bg-background px-5 pt-6 pb-20 sm:px-8 sm:pt-8 sm:pb-24">
        <div className="relative">
          <p className="text-sm font-semibold text-primary">{t.welcome.eyebrow}</p>
          <h2 className="mt-2 font-serif text-[1.75rem] leading-tight text-primary sm:text-4xl">{t.welcome.title}</h2>
          <TitleRule className="mt-3 sm:mt-4" />
          <p className="mt-3 max-w-xl text-[0.9375rem] leading-relaxed text-text-muted sm:mt-4 sm:text-base">
            {t.welcome.body}
          </p>
        </div>
        <Skyline
          preserveAspectRatio="xMidYMax meet"
          className="pointer-events-none absolute inset-x-0 bottom-0 h-16 w-full text-primary opacity-[0.09] sm:h-20"
        />
      </section>

      {/* Topics the indexed municipal corpus actually covers. */}
      <div className="grid gap-3 sm:grid-cols-3">
        {t.welcome.suggestions.map(({ topic, question }) => (
          <button
            key={question}
            type="button"
            onClick={() => onSend(question)}
            className="group flex min-h-36 flex-col items-start gap-3 rounded-[6px] border border-border/60 bg-background p-4 text-left transition-[border-color,background-color] duration-200 hover:border-primary-100 hover:bg-primary-50/30 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary motion-reduce:transition-none"
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
  onTrackPlan,
  error,
  onDismissError,
  alertPrompt,
}: ChatWindowProps) {
  const { t, locale } = useI18n();
  const voice = useVoiceMode({ chatId, messages, onSend, language: locale });
  const [sourcePreview, setSourcePreview] = useState<SourcePreviewSelection | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrolledRef = useRef({ chatId, hadMessages: false });

  useEffect(() => {
    const previous = scrolledRef.current;
    const jump = previous.chatId !== chatId || !previous.hadMessages;
    scrolledRef.current = { chatId, hadMessages: messages.length > 0 };
    bottomRef.current?.scrollIntoView({ behavior: jump ? "auto" : "smooth" });
  }, [chatId, messages, isTyping]);

  // A preview belongs to one chat turn. Never carry it into another chat or
  // keep it open after polling/regeneration removes that source.
  useEffect(() => { setSourcePreview(null); }, [chatId]);
  useEffect(() => {
    if (!sourcePreview) return;
    const selectedMessage = messages.find(message => message.id === sourcePreview.messageId);
    if (!selectedMessage?.sources?.[sourcePreview.sourceIndex]) setSourcePreview(null);
  }, [messages, sourcePreview]);

  const isEmpty = messages.length === 0 && !isTyping;

  // Offer the support line when the latest reply couldn't answer; dismissing hides it for that reply only.
  const [dismissedNoticeId, setDismissedNoticeId] = useState<string | null>(null);
  const lastMessage = messages.at(-1);
  const lastMissing = lastMessage ? notFoundReason(lastMessage) : null;
  const noticeFor = !isTyping && lastMessage?.role === "assistant" &&
    ((lastMissing && lastMissing !== "OUT_OF_SCOPE") || isUnanswered(lastMessage.content)) ? lastMessage.id : null;
  const previewMessage = sourcePreview
    ? messages.find(message => message.id === sourcePreview.messageId)
    : undefined;
  const previewSources = previewMessage?.sources;

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
          <div className="mx-auto flex w-full max-w-3xl flex-col gap-7">
            {messages.map((m) =>
              m.role === "user" ? (
                <UserMessage key={m.id} message={m} onRetry={onRetry} />
              ) : (
                <AssistantMessage key={m.id} message={m} onRegenerate={onRegenerate}
                  onToggleSpeech={voice.toggleSpeech} speechState={voice.speechStateFor(m)}
                  activeSourceIndex={sourcePreview?.messageId === m.id ? sourcePreview.sourceIndex : null}
                  sourcePanelId={SOURCE_PANEL_ID}
                  onSelectSource={(message, sourceIndex, trigger) => {
                    setSourcePreview({ messageId: message.id, sourceIndex, trigger });
                  }}
                  // Only the latest reply's clarification can still be answered.
                  onChoose={m.id === lastMessage?.id && !isTyping ? (label) => { onSend(label); } : undefined} />
              ),
            )}
            {isTyping && !messages.some(message => message.generationStatus === "PENDING") && <AssistantMessage isTyping />}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      <div className="px-4 pb-4">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-2">
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
        {onTrackPlan && lastMessage?.role === "assistant" && !isTyping && (
          <div className="flex justify-end">
            <button
              type="button"
              onClick={onTrackPlan}
              className="inline-flex min-h-11 items-center gap-2 rounded-[5px] px-3 text-sm font-semibold text-primary transition-colors duration-200 hover:bg-primary-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary motion-reduce:transition-none"
            >
              <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M4 19V8l8-5 8 5v11M8 21v-7h8v7M3 21h18" />
              </svg>
              {t.trackers.trackThisPlan}
            </button>
          </div>
        )}
        {alertPrompt}
        <ChatInput onSend={onSend} disabled={isTyping || isLoading} voice={voice} />
        <p className="text-center text-[11px] text-text-subtle">
          {t.chat.disclaimer}
        </p>
        </div>
      </div>

      {sourcePreview && previewSources?.[sourcePreview.sourceIndex] && (
        <SourcePreview
          id={SOURCE_PANEL_ID}
          sources={previewSources}
          activeIndex={sourcePreview.sourceIndex}
          trigger={sourcePreview.trigger}
          onSelect={(sourceIndex) => setSourcePreview(current => current
            ? { ...current, sourceIndex }
            : current)}
          onClose={() => setSourcePreview(null)}
        />
      )}
    </div>
  );
}

export default ChatWindow;
