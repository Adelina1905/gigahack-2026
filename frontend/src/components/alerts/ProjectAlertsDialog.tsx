import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { useAlertSettings, type AlertSettingsClient } from "../../hooks/useAlertSettings";
import { useI18n } from "../../i18n/context";
import type { AlertTopic } from "../../types/alerts";
import { actionButtonClass, dangerButtonClass, iconProps } from "../sidebar/iconProps";
import AlertDialogFrame from "./AlertDialogFrame";
import { formatDateTime } from "./format";

interface ProjectAlertsDialogProps {
  projectId: string;
  projectName: string;
  onClose: () => void;
  // Turning alerts on or "Check now" may have created alerts.
  onAlertsChanged?: () => void;
  // Defaults to the app's API; tests pass their own.
  client?: AlertSettingsClient;
}

interface TopicRowProps {
  topic: AlertTopic;
  onRename: (topicId: number, label: string) => void;
  onRemove: (topicId: number) => void;
}

function TopicRow({ topic, onRename, onRemove }: TopicRowProps) {
  const { t } = useI18n();
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(topic.label);
  const inputRef = useRef<HTMLInputElement>(null);
  // Escape unmounts the input, which can fire a blur; don't save on that one.
  const cancelledRef = useRef(false);

  useEffect(() => {
    if (isEditing) inputRef.current?.select();
  }, [isEditing]);

  const startEditing = () => {
    setDraft(topic.label);
    cancelledRef.current = false;
    setIsEditing(true);
  };

  const commit = () => {
    if (cancelledRef.current) return;
    setIsEditing(false);
    if (draft.trim() && draft.trim() !== topic.label) onRename(topic.id, draft);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      commit();
    }
    if (e.key === "Escape") {
      // Leaves the dialog open.
      e.stopPropagation();
      e.nativeEvent.stopImmediatePropagation();
      cancelledRef.current = true;
      setIsEditing(false);
    }
  };

  if (isEditing) {
    return (
      <li>
        <input
          ref={inputRef}
          value={draft}
          maxLength={80}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={handleKeyDown}
          aria-label={t.alerts.settings.topicName}
          className="w-full rounded-sm border border-primary bg-background px-3 py-2 text-sm text-text focus:outline-none"
        />
      </li>
    );
  }

  return (
    <li className="flex items-center gap-2 rounded-sm border border-border bg-background px-3 py-1.5">
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium text-text" title={topic.label}>
          {topic.label}
        </span>
        {topic.isAuto && <span className="block text-[11px] text-text-subtle">{t.alerts.settings.auto}</span>}
      </span>
      <button type="button" onClick={startEditing} aria-label={t.alerts.settings.rename(topic.label)} className={actionButtonClass}>
        <svg {...iconProps} className="h-3.5 w-3.5">
          <path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
        </svg>
      </button>
      <button type="button" onClick={() => onRemove(topic.id)} aria-label={t.alerts.settings.remove(topic.label)} className={dangerButtonClass}>
        <svg {...iconProps} className="h-3.5 w-3.5">
          <path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m2 0v14a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V6" />
        </svg>
      </button>
    </li>
  );
}

// A project's alert switch, its followed topics and a manual "Check now".
function ProjectAlertsDialog({ projectId, projectName, onClose, onAlertsChanged, client }: ProjectAlertsDialogProps) {
  const { t } = useI18n();
  const alerts = useAlertSettings(projectId, client, { onAlertsChanged });
  const { settings } = alerts;
  const [newTopic, setNewTopic] = useState("");
  const enabled = settings?.enabled ?? false;

  const submitTopic = async (e: FormEvent) => {
    e.preventDefault();
    const label = newTopic.trim();
    if (!label) return;
    if (await alerts.addTopic(label)) setNewTopic("");
  };

  return (
    <AlertDialogFrame title={t.alerts.settings.title} onClose={onClose} testId="project-alerts" className="max-w-md">
      <p className="mt-2 truncate text-sm text-text-muted" title={projectName}>
        {projectName}
      </p>

      {alerts.isLoading ? (
        <p className="mt-4 text-sm text-text-subtle">{t.alerts.settings.loading}</p>
      ) : settings && (
        <>
          <div
            className={`mt-4 flex items-center gap-3 rounded-sm border px-3 py-3 ${
              enabled ? "border-primary-200 bg-primary-50" : "border-border bg-background-secondary"
            }`}
          >
            <div className="min-w-0 flex-1">
              <p id={`alerts-switch-${projectId}`} className="text-sm font-semibold text-text">
                {t.alerts.settings.switchLabel}
              </p>
              <p className="text-xs text-text-muted">{enabled ? t.alerts.settings.onHint : t.alerts.settings.offHint}</p>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={enabled}
              aria-labelledby={`alerts-switch-${projectId}`}
              onClick={() => void alerts.setEnabled(!enabled)}
              disabled={alerts.isSaving}
              className="inline-flex shrink-0 cursor-pointer items-center gap-2 rounded-sm px-1 py-1 text-xs font-semibold focus-visible:outline-2 focus-visible:outline-primary disabled:cursor-wait"
            >
              <span aria-hidden="true" className={enabled ? "text-primary-700" : "text-text-muted"}>
                {enabled ? t.alerts.settings.on : t.alerts.settings.off}
              </span>
              <span aria-hidden="true" className={`relative h-5 w-9 rounded-full transition-colors ${enabled ? "bg-primary" : "bg-border-strong"}`}>
                <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${enabled ? "translate-x-[18px]" : "translate-x-0.5"}`} />
              </span>
            </button>
          </div>

          <section aria-labelledby={`alerts-topics-${projectId}`} className="mt-5">
            <h3 id={`alerts-topics-${projectId}`} className="pb-1.5">
              <span className="inline-block rounded-sm border border-border-strong bg-background px-1.5 py-px text-[11px] font-medium text-text-muted">
                {t.alerts.settings.topics}
              </span>
            </h3>
            {settings.topics.length === 0 ? (
              <p className="py-1 text-sm text-text-subtle">{t.alerts.settings.noTopics}</p>
            ) : (
              <ul className="flex flex-col gap-1.5">
                {settings.topics.map((topic) => (
                  <TopicRow
                    key={topic.id}
                    topic={topic}
                    onRename={(topicId, label) => void alerts.renameTopic(topicId, label)}
                    onRemove={(topicId) => void alerts.removeTopic(topicId)}
                  />
                ))}
              </ul>
            )}

            <form onSubmit={(e) => void submitTopic(e)} className="mt-2 flex gap-2">
              <input
                value={newTopic}
                maxLength={80}
                onChange={(e) => setNewTopic(e.target.value)}
                placeholder={t.alerts.settings.addPlaceholder}
                aria-label={t.alerts.settings.topicName}
                className="min-w-0 flex-1 rounded-sm border border-border-strong bg-background px-3 py-2 text-sm text-text focus:border-primary focus:outline-none"
              />
              <button
                type="submit"
                disabled={!newTopic.trim()}
                className="flex shrink-0 cursor-pointer items-center gap-1 rounded-sm border border-primary px-3 py-2 text-sm font-semibold text-primary hover:bg-primary-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <svg {...iconProps} className="h-3.5 w-3.5" aria-hidden="true">
                  <path d="M12 5v14M5 12h14" />
                </svg>
                {t.alerts.settings.add}
              </button>
            </form>
          </section>
        </>
      )}

      {alerts.error && (
        <div role="alert" className="mt-4 flex items-center justify-between gap-3 rounded-sm border border-danger bg-danger-light px-3 py-2 text-sm text-danger">
          <span>{t.errors[alerts.error]}</span>
          <button type="button" onClick={alerts.dismissError} aria-label={t.chat.dismissError} className="shrink-0 rounded-sm px-1.5 text-base leading-none hover:bg-background">
            ×
          </button>
        </div>
      )}

      <div className="mt-5 flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-border pt-4">
        {settings && (
          <button
            type="button"
            onClick={() => void alerts.checkNow()}
            disabled={alerts.isScanning}
            className="flex cursor-pointer items-center gap-1.5 rounded-sm bg-primary px-3 py-2 text-sm font-semibold text-text-inverted transition-colors hover:bg-primary-dark disabled:cursor-wait disabled:opacity-60"
          >
            <svg {...iconProps} className={`h-3.5 w-3.5 ${alerts.isScanning ? "animate-spin" : ""}`} aria-hidden="true">
              <path d="M21 12a9 9 0 1 1-2.6-6.4M21 4v5h-5" />
            </svg>
            {alerts.isScanning ? t.alerts.settings.checking : t.alerts.settings.checkNow}
          </button>
        )}
        <div className="min-w-0 flex-1 text-xs">
          <p role="status" aria-live="polite" className="font-semibold text-primary-700">
            {alerts.lastScanCreated !== null && t.alerts.settings.created(alerts.lastScanCreated)}
          </p>
          {settings && (
            <p className="text-text-subtle">
              {settings.lastScanAt
                ? t.alerts.settings.lastScan(formatDateTime(settings.lastScanAt, t.meta.intl))
                : t.alerts.settings.neverScanned}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="cursor-pointer rounded-sm px-3 py-2 text-sm font-medium text-text-muted hover:bg-background-secondary hover:text-text"
        >
          {t.alerts.settings.close}
        </button>
      </div>
    </AlertDialogFrame>
  );
}

export default ProjectAlertsDialog;
