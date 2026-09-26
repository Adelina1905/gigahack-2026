import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Api } from "../api";
import { toAlert, toUnreadAlertCounts } from "../api/mappers";
import type { ErrorKey } from "../i18n/messages";
import { NO_UNREAD_ALERTS, type Alert, type UnreadAlertCounts } from "../types/alerts";

export type AlertsClient = Pick<
  Api,
  "getAlerts" | "getAlertUnreadCount" | "markAlertRead" | "markAllAlertsRead" | "markAlertNotRelevant"
>;

const POLL_MS = 30_000;
const LIST_LIMIT = 50;

const byNewest = (a: Alert, b: Alert) => b.createdAt - a.createdAt || b.id - a.id;

// Moves one project's unread count by delta, never below zero.
export function adjustUnread(counts: UnreadAlertCounts, projectId: string, delta: number): UnreadAlertCounts {
  const current = counts.byProject[projectId] ?? 0;
  const next = Math.max(0, current + delta);
  const byProject = { ...counts.byProject };
  if (next > 0) byProject[projectId] = next;
  else delete byProject[projectId];
  return { total: Math.max(0, counts.total + (next - current)), byProject };
}

// The header bell's alerts: unread counts are polled (and refetched when the
// tab regains focus); the list itself is loaded when the panel opens.
export function useAlerts(client: AlertsClient = api, { pollMs = POLL_MS } = {}) {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [unread, setUnread] = useState<UnreadAlertCounts>(NO_UNREAD_ALERTS);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ErrorKey | null>(null);
  const clientRef = useRef(client);
  const alertsRef = useRef(alerts);
  const unreadRef = useRef(unread);
  useEffect(() => {
    clientRef.current = client;
    alertsRef.current = alerts;
    unreadRef.current = unread;
  });

  // Polling failures stay quiet; the badge just keeps its last value.
  const refreshUnread = useCallback(async () => {
    try {
      setUnread(toUnreadAlertCounts(await clientRef.current.getAlertUnreadCount()));
    } catch (loadError) {
      console.error("Failed to load unread alert count", loadError);
    }
  }, []);

  useEffect(() => {
    void refreshUnread();
    const interval = setInterval(() => void refreshUnread(), pollMs);
    const onVisible = () => {
      if (document.visibilityState === "visible") void refreshUnread();
    };
    const onFocus = () => void refreshUnread();
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(interval);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [pollMs, refreshUnread]);

  const loadAlerts = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [list, counts] = await Promise.all([
        clientRef.current.getAlerts({ limit: LIST_LIMIT }),
        clientRef.current.getAlertUnreadCount(),
      ]);
      setAlerts(list.map(toAlert).sort(byNewest));
      setUnread(toUnreadAlertCounts(counts));
    } catch (loadError) {
      console.error("Failed to load alerts", loadError);
      setError("alertsLoadFailed");
    } finally {
      setIsLoading(false);
    }
  }, []);

  const setRead = (alertId: number, isRead: boolean) =>
    setAlerts((current) => current.map((alert) => (alert.id === alertId ? { ...alert, isRead } : alert)));

  const markRead = useCallback(async (alertId: number) => {
    const alert = alertsRef.current.find((candidate) => candidate.id === alertId);
    if (!alert || alert.isRead) return;
    setRead(alertId, true);
    setUnread((counts) => adjustUnread(counts, alert.projectId, -1));
    try {
      await clientRef.current.markAlertRead(alertId);
    } catch (markError) {
      console.error("Failed to mark alert read", markError);
      setRead(alertId, false);
      setUnread((counts) => adjustUnread(counts, alert.projectId, 1));
      setError("alertUpdateFailed");
    }
  }, []);

  // null marks every project's alerts as read.
  const markAllRead = useCallback(async (projectId: string | null = null) => {
    const previousAlerts = alertsRef.current;
    const previousUnread = unreadRef.current;
    setAlerts((current) =>
      current.map((alert) => (!projectId || alert.projectId === projectId ? { ...alert, isRead: true } : alert)),
    );
    setUnread((counts) =>
      projectId ? adjustUnread(counts, projectId, -(counts.byProject[projectId] ?? 0)) : NO_UNREAD_ALERTS,
    );
    try {
      await clientRef.current.markAllAlertsRead(projectId);
    } catch (markError) {
      console.error("Failed to mark alerts read", markError);
      setAlerts(previousAlerts);
      setUnread(previousUnread);
      setError("alertUpdateFailed");
    }
  }, []);

  // The alert goes away for good; the backend also makes its topic stricter.
  const notRelevant = useCallback(async (alertId: number) => {
    const alert = alertsRef.current.find((candidate) => candidate.id === alertId);
    if (!alert) return;
    setAlerts((current) => current.filter((candidate) => candidate.id !== alertId));
    if (!alert.isRead) setUnread((counts) => adjustUnread(counts, alert.projectId, -1));
    try {
      await clientRef.current.markAlertNotRelevant(alertId);
    } catch (feedbackError) {
      console.error("Failed to dismiss alert", feedbackError);
      setAlerts((current) => [...current.filter((candidate) => candidate.id !== alertId), alert].sort(byNewest));
      if (!alert.isRead) setUnread((counts) => adjustUnread(counts, alert.projectId, 1));
      setError("alertUpdateFailed");
    }
  }, []);

  const dismissError = useCallback(() => setError(null), []);

  return { alerts, unread, isLoading, error, loadAlerts, refreshUnread, markRead, markAllRead, notRelevant, dismissError };
}
