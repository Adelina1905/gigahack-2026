import { useEffect, useRef } from "react";
import type { ChatMessage } from "../types/chat";
import ChatInput from "./Input";
import UserMessage from "./UserMessage";
import AssistantMessage from "./AssistantMessage";

interface ChatWindowProps {
  messages: ChatMessage[];
  isTyping: boolean;
  onSend: (text: string) => void;
  onRetry?: (id: string) => void;
  onRegenerate?: (id: string) => void;
}

const SUGGESTIONS = [
  "What can you help me with?",
  "Summarize an uploaded document",
  "Explain how this works",
];

function ChatWindow({ messages, isTyping, onSend, onRetry, onRegenerate }: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  const isEmpty = messages.length === 0 && !isTyping;

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto px-4 py-6">
        {isEmpty ? (
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

      <div className="px-4 pb-4">
        <ChatInput onSend={onSend} disabled={isTyping} />
      </div>
    </div>
  );
}

export default ChatWindow;
