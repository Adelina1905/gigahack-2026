import type { ChatMessage } from "../types/chat";

interface UserMessageProps {
  message: ChatMessage;
  onRetry?: (id: string) => void;
}

const formatTime = (ts: number) =>
  new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

function UserMessage({ message, onRetry }: UserMessageProps) {
  const isSending = message.status === "sending";
  const isError = message.status === "error";

  return (
    <div className="flex flex-col items-end gap-1">
      <div
        className={`max-w-[75%] whitespace-pre-wrap break-words rounded-2xl rounded-br-sm bg-[#EBEBEB] px-4 py-2.5 text-base text-text transition-opacity ${
          isSending ? "opacity-60" : ""
        } ${isError ? "border border-danger" : ""}`}
      >
        {message.content}
      </div>

      {isError ? (
        <p className="text-xs text-danger">
          Not saved yet
          {onRetry && (
            <>
              {" · "}
              <button
                type="button"
                onClick={() => onRetry(message.id)}
                className="font-semibold underline-offset-2 hover:underline"
              >
                Retry
              </button>
            </>
          )}
        </p>
      ) : (
        <span className="text-xs text-text-subtle">
          {isSending ? "Sending…" : formatTime(message.createdAt)}
        </span>
      )}
    </div>
  );
}

export default UserMessage;
