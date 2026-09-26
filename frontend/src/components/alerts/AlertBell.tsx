import { useCallback, useEffect, useId, useRef, useState } from "react";
import { useI18n } from "../../i18n/context";
import type { ErrorKey } from "../../i18n/messages";
import type { Alert } from "../../types/alerts";
import type { ProjectSummary } from "../../types/chat";
import { iconProps } from "../sidebar/iconProps";
import { safeHttpUrl } from "../sources/safeLink";
import { formatCalendarDate } from "./format";

interface AlertBellProps {
  alerts: Alert[];
  unreadTotal: number;
  projects: ProjectSummary[];
  isLoading?: boolean;
  error?: ErrorKey | null;
  // Called each time the panel opens, to fetch the latest list.
  onOpen: () => void;
  onMarkRead: (alertId: number) => void;
  onMarkAllRead: () => void;
  onNotRelevant: (alertId: number) => void;
  onAsk: (alert: Alert) => void;
  onDismissError?: () => void;
}

const BellIcon = ({ className }: { className: string }) => (
  <svg {...iconProps} className={className} aria-hidden="true">
    <path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.94 1.94 0 0 0 3.4 0" />
  </svg>
);

const smallActionClass =
  "inline-flex cursor-pointer items-center gap-1 rounded-sm px-1.5 py-1 text-xs font-semibold text-primary hover:bg-primary-50";

// Alerts are shown under their project, in the order the newest alert of each arrived.
function groupByProject(alerts: Alert[]) {
  const groups = new Map<string, Alert[]>();
  for (const alert of alerts) groups.set(alert.projectId, [...(groups.get(alert.projectId) ?? []), alert]);
  return [...groups.entries()];
}

interface AlertCardProps {
  alert: Alert;
  onMarkRead: (alertId: number) => void;
  onNotRelevant: (alertId: number) => void;
  onAsk: (alert: Alert) => void;
}

function AlertCard({ alert, onMarkRead, onNotRelevant, onAsk }: AlertCardProps) {
  const { t } = useI18n();
  const link = safeHttpUrl(alert.url);
  const meta = [alert.source, alert.district, formatCalendarDate(alert.publishedDate, t.meta.intl)].filter(Boolean);

  return (
    <li
      aria-label={alert.title}
      className={`relative border-l-[3px] py-3 pr-3 pl-3 ${alert.isRead ? "border-transparent" : "border-accent bg-primary-50/50"}`}
    >
      {!alert.isRead && (
        <span className="mb-1 inline-block rounded-sm bg-accent px-1.5 py-px text-[10px] font-bold uppercase tracking-wide text-primary-900">
          {t.alerts.unread}
        </span>
      )}
      <h4 className="font-serif text-[0.9375rem] leading-snug text-text">{alert.title}</h4>
      {meta.length > 0 && <p className="mt-0.5 text-xs text-text-subtle">{meta.join(" · ")}</p>}
      {alert.excerpt && <p className="mt-1.5 line-clamp-3 text-sm text-text-muted">{alert.excerpt}</p>}
      <p className="mt-2 flex flex-wrap items-center gap-1 text-xs text-text-muted">
        <span>{t.alerts.because}</span>
        <span className="rounded-sm border border-primary-200 bg-background px-1.5 py-px font-medium text-primary-700">
          {alert.topicLabel}
        </span>
      </p>

      <div className="mt-2 -ml-1.5 flex flex-wrap items-center gap-x-1 gap-y-0.5">
        {link && (
          <a
            href={link}
            target="_blank"
            rel="noopener noreferrer"
            onClick={() => onMarkRead(alert.id)}
            className={smallActionClass}
          >
            <svg {...iconProps} className="h-3.5 w-3.5" aria-hidden="true">
              <path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
            </svg>
            {t.alerts.openSource}
          </a>
        )}
        <button type="button" onClick={() => onAsk(alert)} className={smallActionClass}>
          <svg {...iconProps} className="h-3.5 w-3.5" aria-hidden="true">
            <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12Z" />
          </svg>
          {t.alerts.askAbout}
        </button>
        {!alert.isRead && (
          <button type="button" onClick={() => onMarkRead(alert.id)} className={smallActionClass}>
            <svg {...iconProps} className="h-3.5 w-3.5" aria-hidden="true">
              <path d="m5 12 5 5L20 7" />
            </svg>
            {t.alerts.markRead}
          </button>
        )}
        <button
          type="button"
          onClick={() => onNotRelevant(alert.id)}
          className="inline-flex cursor-pointer items-center gap-1 rounded-sm px-1.5 py-1 text-xs font-medium text-text-subtle hover:bg-danger-light hover:text-danger"
        >
          <svg {...iconProps} className="h-3.5 w-3.5" aria-hidden="true">
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
          {t.alerts.notRelevant}
        </button>
      </div>
    </li>
  );
}

// The header bell with the unread count, and a popover listing the alerts.
function AlertBell({
  alerts,
  unreadTotal,
  projects,
  isLoading = false,
  error,
  onOpen,
  onMarkRead,
  onMarkAllRead,
  onNotRelevant,
  onAsk,
  onDismissError,
}: AlertBellProps) {
  const { t } = useI18n();
  const [isOpen, setIsOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const panelId = useId();
  const titleId = useId();

  const close = useCallback((restoreFocus: boolean) => {
    setIsOpen(false);
    if (restoreFocus) buttonRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    panelRef.current?.focus();
    const handlePointer = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) close(false);
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        close(true);
      }
    };
    document.addEventListener("pointerdown", handlePointer);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointer);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, close]);

  const toggle = () => {
    if (isOpen) {
      close(false);
      return;
    }
    setIsOpen(true);
    onOpen();
  };

  const projectName = (projectId: string) =>
    projects.find((project) => project.id === projectId)?.name ?? t.alerts.unknownProject;
  const hasUnread = unreadTotal > 0 || alerts.some((alert) => !alert.isRead);
  const badge = unreadTotal > 99 ? "99+" : String(unreadTotal);

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={buttonRef}
        type="button"
        onClick={toggle}
        aria-label={t.alerts.bell(unreadTotal)}
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        aria-controls={isOpen ? panelId : undefined}
        className={`relative flex h-10 w-10 cursor-pointer items-center justify-center rounded-sm transition-colors hover:bg-primary-50 hover:text-primary ${
          isOpen ? "bg-primary-50 text-primary" : "text-text-muted"
        }`}
      >
        <BellIcon className="h-5 w-5" />
        {unreadTotal > 0 && (
          <span
            data-testid="alert-badge"
            aria-hidden="true"
            className="absolute top-0.5 right-0.5 flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-accent px-1 text-[11px] font-bold leading-none text-primary-900 ring-2 ring-background"
          >
            {badge}
          </span>
        )}
      </button>

      {isOpen && (
        <div
          ref={panelRef}
          id={panelId}
          role="dialog"
          aria-labelledby={titleId}
          tabIndex={-1}
          className="absolute top-full right-0 z-50 mt-2 flex max-h-[min(36rem,calc(100dvh-7rem))] w-[min(26rem,calc(100vw-1.5rem))] flex-col rounded-sm border border-border bg-background shadow-lg focus:outline-none"
        >
          <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
            <h2 id={titleId} className="font-serif text-lg leading-tight text-primary">
              {t.alerts.panelTitle}
            </h2>
            <div className="flex items-center gap-1">
              {hasUnread && (
                <button type="button" onClick={onMarkAllRead} className={smallActionClass}>
                  {t.alerts.markAllRead}
                </button>
              )}
              <button
                type="button"
                onClick={() => close(true)}
                aria-label={t.alerts.close}
                className="cursor-pointer rounded-sm p-1.5 text-text-subtle hover:bg-background-secondary hover:text-text"
              >
                <svg {...iconProps} className="h-4 w-4" aria-hidden="true">
                  <path d="M18 6 6 18M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          {error && (
            <div role="alert" className="mx-4 mt-3 flex items-center justify-between gap-3 rounded-sm border border-danger bg-danger-light px-3 py-2 text-sm text-danger">
              <span>{t.errors[error]}</span>
              {onDismissError && (
                <button type="button" onClick={onDismissError} aria-label={t.chat.dismissError} className="shrink-0 rounded-sm px-1.5 text-base leading-none hover:bg-background">
                  ×
                </button>
              )}
            </div>
          )}

          <div className="min-h-0 flex-1 overflow-y-auto">
            {alerts.length === 0 ? (
              <p className="flex items-start gap-3 px-4 py-6 text-sm text-text-subtle">
                {isLoading ? (
                  t.alerts.loading
                ) : (
                  <>
                    <BellIcon className="mt-0.5 h-5 w-5 shrink-0 text-primary-300" />
                    {t.alerts.empty}
                  </>
                )}
              </p>
            ) : (
              groupByProject(alerts).map(([projectId, items]) => (
                <section key={projectId} aria-label={projectName(projectId)} className="border-b border-border last:border-b-0">
                  <h3 className="flex items-center gap-1.5 bg-background-secondary px-4 py-1.5 text-xs font-semibold text-text-muted">
                    <svg {...iconProps} className="h-3.5 w-3.5 text-primary" aria-hidden="true">
                      <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />
                    </svg>
                    <span className="truncate">{projectName(projectId)}</span>
                  </h3>
                  <ul className="divide-y divide-border">
                    {items.map((alert) => (
                      <AlertCard
                        key={alert.id}
                        alert={alert}
                        onMarkRead={onMarkRead}
                        onNotRelevant={onNotRelevant}
                        onAsk={(target) => {
                          close(false);
                          onAsk(target);
                        }}
                      />
                    ))}
                  </ul>
                </section>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default AlertBell;
