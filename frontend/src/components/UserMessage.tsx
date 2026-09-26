import { useI18n } from "../i18n/context";
import type { ChatMessage } from "../types/chat";

interface UserMessageProps {
  message: ChatMessage;
  onRetry?: (id: string) => void;
}

const formatTime = (ts: number, locale: string) =>
  new Date(ts).toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" });

function UserMessage({ message, onRetry }: UserMessageProps) {
  const { t } = useI18n();
  const isSending = message.status === "sending";
  const isError = message.status === "error";

  return (
    <div className="flex flex-col items-end gap-1">
      <div
        className={`max-w-[85%] whitespace-pre-wrap break-words rounded-sm bg-primary px-4 py-2.5 text-[0.9375rem] leading-relaxed text-text-inverted transition-opacity ${
          isSending ? "opacity-60" : ""
        } ${isError ? "ring-2 ring-danger ring-offset-2 ring-offset-background-canvas" : ""}`}
      >
        {message.content}
      </div>

      {isError ? (
        <p className="text-xs text-danger">
          {t.message.failed}
          {onRetry && (
            <>
              {" · "}
              <button
                type="button"
                onClick={() => onRetry(message.id)}
                className="font-semibold underline-offset-2 hover:underline"
              >
                {t.message.retry}
              </button>
            </>
          )}
        </p>
      ) : (
        <span className="text-xs text-text-subtle">
          {isSending ? t.message.sending : formatTime(message.createdAt, t.meta.intl)}
        </span>
      )}
    </div>
  );
}

export default UserMessage;
