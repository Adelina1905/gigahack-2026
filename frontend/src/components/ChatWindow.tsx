import { useEffect, useRef } from "react";
import type { ChatMessage } from "../types/chat";
import ChatInput from "./Input";
import UserMessage from "./UserMessage";
import AssistantMessage from "./AssistantMessage";

interface ChatWindowProps {
  // Switching chats jumps to the bottom instead of smooth-scrolling through history.
  chatId?: string | null;
  messages: ChatMessage[];
  isTyping: boolean;
  isLoading?: boolean;
  onSend: (text: string) => void;
  onRetry?: (id: string) => void;
  onRegenerate?: (id: string) => void;
  error?: string | null;
  onDismissError?: () => void;
}

const SUGGESTIONS = [
  "What can you help me with?",
  "Summarize an uploaded document",
  "Explain how this works",
];

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
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrolledRef = useRef({ chatId, hadMessages: false });

  useEffect(() => {
    const previous = scrolledRef.current;
    const jump = previous.chatId !== chatId || !previous.hadMessages;
    scrolledRef.current = { chatId, hadMessages: messages.length > 0 };
    bottomRef.current?.scrollIntoView({ behavior: jump ? "auto" : "smooth" });
  }, [chatId, messages, isTyping]);

  const isEmpty = messages.length === 0 && !isTyping;

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto px-4 py-6">
        {isLoading ? (
          <div className="flex h-full items-center justify-center text-sm text-text-subtle">
            Loading conversation…
          </div>
        ) : isEmpty ? (
          <div className="flex h-full flex-col items-center justify-center gap-6 text-center">
            <h2 className="text-2xl font-semibold text-text">How can I help you today?</h2>
            <div className="flex flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => onSend(s)}
                  className="rounded-full border border-border bg-background px-4 py-2 text-sm text-text-muted transition-colors hover:bg-background-secondary"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
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
            className="flex items-center justify-between gap-3 rounded-lg border border-danger bg-danger-light px-3 py-2 text-sm text-danger"
          >
            <span>{error}</span>
            {onDismissError && (
              <button
                type="button"
                onClick={onDismissError}
                aria-label="Dismiss error"
                className="shrink-0 rounded-md px-1.5 text-base leading-none hover:bg-background"
              >
                ×
              </button>
            )}
          </div>
        )}
        <ChatInput onSend={onSend} disabled={isTyping} />
      </div>
    </div>
  );
}

export default ChatWindow;
