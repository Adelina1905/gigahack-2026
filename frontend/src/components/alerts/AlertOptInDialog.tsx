import { useI18n } from "../../i18n/context";
import type { ErrorKey } from "../../i18n/messages";
import { iconProps } from "../sidebar/iconProps";
import AlertDialogFrame from "./AlertDialogFrame";

interface AlertOptInDialogProps {
  projectName: string;
  topics: string[];
  isSaving?: boolean;
  error?: ErrorKey | null;
  onEnable: () => void;
  // "Not now"; Escape and the backdrop mean the same.
  onDecline: () => void;
}

// Asked once per project, after its first answered question.
function AlertOptInDialog({ projectName, topics, isSaving = false, error, onEnable, onDecline }: AlertOptInDialogProps) {
  const { t } = useI18n();

  return (
    <AlertDialogFrame title={t.alerts.optIn.title} onClose={() => !isSaving && onDecline()} testId="alert-opt-in">
      <div className="mt-4 flex gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-sm bg-accent/20 text-primary" aria-hidden="true">
          <svg {...iconProps} className="h-5 w-5">
            <path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.94 1.94 0 0 0 3.4 0" />
          </svg>
        </span>
        <div className="min-w-0 text-sm text-text-muted">
          <p>{topics.length > 0 ? t.alerts.optIn.body(projectName) : t.alerts.optIn.noTopics(projectName)}</p>
          {topics.length > 0 && (
            <ul aria-label={t.alerts.settings.topics} className="mt-3 flex flex-wrap gap-1.5">
              {topics.map((topic) => (
                <li key={topic} className="rounded-sm border border-primary-200 bg-primary-50 px-2 py-0.5 text-xs font-medium text-primary-700">
                  {topic}
                </li>
              ))}
            </ul>
          )}
          <p className="mt-3 text-xs text-text-subtle">{t.alerts.optIn.hint}</p>
        </div>
      </div>

      {error && (
        <p role="alert" className="mt-4 rounded-sm border border-danger bg-danger-light px-3 py-2 text-sm text-danger">
          {t.errors[error]}
        </p>
      )}

      <div className="mt-5 flex justify-end gap-2">
        <button
          type="button"
          onClick={onDecline}
          disabled={isSaving}
          className="cursor-pointer rounded-sm px-3 py-2 text-sm font-medium text-text-muted hover:bg-background-secondary hover:text-text disabled:cursor-not-allowed disabled:opacity-50"
        >
          {t.alerts.optIn.notNow}
        </button>
        <button
          type="button"
          data-autofocus
          onClick={onEnable}
          disabled={isSaving}
          className="cursor-pointer rounded-sm bg-primary px-4 py-2 text-sm font-semibold text-text-inverted transition-colors hover:bg-primary-dark disabled:cursor-not-allowed disabled:opacity-50"
        >
          {t.alerts.optIn.enable}
        </button>
      </div>
    </AlertDialogFrame>
  );
}

export default AlertOptInDialog;
