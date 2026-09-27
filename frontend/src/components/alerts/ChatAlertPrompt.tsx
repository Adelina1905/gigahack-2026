import { useId } from "react";
import { useI18n } from "../../i18n/context";
import type { ErrorKey } from "../../i18n/messages";
import type { AlertScope } from "../../types/alerts";
import { iconProps } from "../sidebar/iconProps";

interface ChatAlertPromptProps {
  // A project's subscription or the chat's own; picks the generic line.
  scopeKind: AlertScope["kind"];
  topics: string[];
  isSaving?: boolean;
  error?: ErrorKey | null;
  onEnable: () => void;
  // "Not now" and × both answer no.
  onDecline: () => void;
}

const BellIcon = ({ className }: { className: string }) => (
  <svg {...iconProps} className={className} aria-hidden="true">
    <path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.94 1.94 0 0 0 3.4 0" />
  </svg>
);

// The one-time "get notified?" question just above the chat input. It is not
// a dialog: it never takes focus, so the user can keep typing.
function ChatAlertPrompt({ scopeKind, topics, isSaving = false, error, onEnable, onDecline }: ChatAlertPromptProps) {
  const { t } = useI18n();
  const questionId = useId();

  return (
    <section
      role="region"
      aria-label={t.alerts.prompt.label}
      aria-describedby={questionId}
      aria-busy={isSaving}
      data-testid="chat-alert-prompt"
      className="relative flex items-start gap-3 rounded-sm border border-primary-200 border-l-[3px] border-l-accent bg-primary-50 py-2.5 pr-9 pl-3"
    >
      <BellIcon className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
      <div className="min-w-0 flex-1">
        <p id={questionId} className="text-sm text-text">
          {topics.length > 0 ? t.alerts.prompt.topics(topics) : t.alerts.prompt.generic[scopeKind]}
        </p>
        {error && (
          <p role="alert" className="mt-1 text-xs text-danger">
            {t.errors[error]}
          </p>
        )}
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={onEnable}
            disabled={isSaving}
            className="cursor-pointer rounded-sm bg-primary px-3 py-1.5 text-xs font-semibold text-text-inverted transition-colors hover:bg-primary-dark focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:cursor-wait disabled:opacity-60"
          >
            {t.alerts.prompt.enable}
          </button>
          <button
            type="button"
            onClick={onDecline}
            disabled={isSaving}
            className="cursor-pointer rounded-sm px-3 py-1.5 text-xs font-medium text-text-muted hover:bg-background hover:text-text focus-visible:outline-2 focus-visible:outline-primary disabled:cursor-wait disabled:opacity-60"
          >
            {t.alerts.prompt.notNow}
          </button>
          {isSaving && (
            <span role="status" className="text-xs text-text-subtle">
              {t.alerts.prompt.saving}
            </span>
          )}
        </div>
      </div>
      <button
        type="button"
        onClick={onDecline}
        disabled={isSaving}
        aria-label={t.alerts.prompt.dismiss}
        className="absolute top-1.5 right-1.5 cursor-pointer rounded-sm p-1 text-text-subtle hover:bg-background hover:text-text focus-visible:outline-2 focus-visible:outline-primary disabled:cursor-wait"
      >
        <svg {...iconProps} className="h-3.5 w-3.5" aria-hidden="true">
          <path d="M18 6 6 18M6 6l12 12" />
        </svg>
      </button>
    </section>
  );
}

// What happened after the question was answered; it fades out on its own.
export function ChatAlertNotice({ message }: { message: string }) {
  return (
    <p
      role="status"
      data-testid="chat-alert-notice"
      className="flex items-center gap-2 rounded-sm border border-primary-200 bg-primary-50 px-3 py-2 text-sm text-primary-700"
    >
      <BellIcon className="h-4 w-4 shrink-0" />
      {message}
    </p>
  );
}

export default ChatAlertPrompt;
