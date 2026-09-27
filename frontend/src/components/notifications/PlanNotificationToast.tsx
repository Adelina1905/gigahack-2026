import { useEffect, useState } from "react";
import { useI18n } from "../../i18n/context";
import type { PlanNotification } from "../../types/planNotification";

interface PlanNotificationToastProps {
  notification: PlanNotification;
  onOpen: () => void;
  onClose: () => void;
}

export default function PlanNotificationToast({ notification, onOpen, onClose }: PlanNotificationToastProps) {
  const { t } = useI18n();
  const [paused, setPaused] = useState(false);
  const scenario = t.planNotifications.scenarios[notification.scenarioId];

  useEffect(() => {
    if (paused) return;
    const timer = window.setTimeout(onClose, 7000);
    return () => window.clearTimeout(timer);
  }, [onClose, paused]);

  return (
    <div
      role="status"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setPaused(false);
      }}
      className="animate-[toast-in_200ms_ease-out] rounded-[6px] border border-border/70 bg-background p-4 shadow-[0_12px_36px_rgba(0,30,71,0.16)] motion-reduce:animate-none"
    >
      <div className="flex items-start gap-3">
        <span className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full bg-accent" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold text-primary">{t.planNotifications.exampleBadge}</p>
          <h2 className="mt-1 font-serif text-base leading-snug text-text">{scenario.title}</h2>
          <p className="mt-1 text-sm leading-relaxed text-text-muted">{t.planNotifications.toast(notification.trackerName)}</p>
        </div>
        <button type="button" onClick={onClose} aria-label={t.planNotifications.closeToast} className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[5px] text-text-subtle hover:bg-background-secondary hover:text-text">×</button>
      </div>
      <button type="button" onClick={onOpen} className="mt-3 min-h-10 rounded-[5px] bg-primary px-4 text-sm font-semibold text-white hover:bg-primary-dark focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary">
        {t.planNotifications.viewUpdate}
      </button>
    </div>
  );
}
