import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Api } from "../api";
import { toAlert, toUnreadAlertCounts } from "../api/mappers";
import type { ErrorKey } from "../i18n/messages";
import { NO_UNREAD_ALERTS, alertScope, type Alert, type AlertScope, type UnreadAlertCounts } from "../types/alerts";

export type AlertsClient = Pick<
  Api,
  "getAlerts" | "getAlertUnreadCount" | "markAlertRead" | "markAllAlertsRead" | "markAlertNotRelevant"
>;

const POLL_MS = 30_000;
const LIST_LIMIT = 50;

const byNewest = (a: Alert, b: Alert) => b.createdAt - a.createdAt || b.id - a.id;

const unreadIn = (counts: UnreadAlertCounts, scope: AlertScope) =>
  (scope.kind === "project" ? counts.byProject : counts.byChat)[scope.id] ?? 0;

// Moves one project's or chat's unread count by delta, never below zero.
export function adjustUnread(counts: UnreadAlertCounts, scope: AlertScope, delta: number): UnreadAlertCounts {
  const field = scope.kind === "project" ? "byProject" : "byChat";
  const current = unreadIn(counts, scope);
  const next = Math.max(0, current + delta);
  const updated = { ...counts[field] };
  if (next > 0) updated[scope.id] = next;
  else delete updated[scope.id];
  return { ...counts, [field]: updated, total: Math.max(0, counts.total + (next - current)) };
}

const inScope = (alert: Alert, scope: AlertScope) =>
  scope.kind === "project" ? alert.projectId === scope.id : alert.chatId === scope.id;

// The header bell's alerts: unread counts are polled (and refetched when the
// tab regains focus); the list itself is loaded when the panel opens.
export function useAlerts(client: AlertsClient = api, { pollMs = POLL_MS } = {}) {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [unread, setUnread] = useState<UnreadAlertCounts>(NO_UNREAD_ALERTS);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ErrorKey | null>(null);
  const clientRef = useRef(client);
  useEffect(() => {
    clientRef.current = client;
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

  // The actions read the rendered alerts, not a ref synced after render, so a
  // click right after the list loads always finds its alert.
  const markRead = useCallback(async (alertId: number) => {
    const alert = alerts.find((candidate) => candidate.id === alertId);
    if (!alert || alert.isRead) return;
    setRead(alertId, true);
    setUnread((counts) => adjustUnread(counts, alertScope(alert), -1));
    try {
      await clientRef.current.markAlertRead(alertId);
    } catch (markError) {
      console.error("Failed to mark alert read", markError);
      setRead(alertId, false);
      setUnread((counts) => adjustUnread(counts, alertScope(alert), 1));
      setError("alertUpdateFailed");
    }
  }, [alerts]);

  // null marks every alert as read.
  const markAllRead = useCallback(async (scope: AlertScope | null = null) => {
    const previousAlerts = alerts;
    const previousUnread = unread;
    setAlerts((current) =>
      current.map((alert) => (!scope || inScope(alert, scope) ? { ...alert, isRead: true } : alert)),
    );
    setUnread((counts) => (scope ? adjustUnread(counts, scope, -unreadIn(counts, scope)) : NO_UNREAD_ALERTS));
    try {
      await clientRef.current.markAllAlertsRead(
        !scope ? {} : scope.kind === "project" ? { projectId: scope.id } : { chatId: scope.id },
      );
    } catch (markError) {
      console.error("Failed to mark alerts read", markError);
      setAlerts(previousAlerts);
      setUnread(previousUnread);
      setError("alertUpdateFailed");
    }
  }, [alerts, unread]);

  // The alert goes away for good; the backend also makes its topic stricter.
  const notRelevant = useCallback(async (alertId: number) => {
    const alert = alerts.find((candidate) => candidate.id === alertId);
    if (!alert) return;
    setAlerts((current) => current.filter((candidate) => candidate.id !== alertId));
    if (!alert.isRead) setUnread((counts) => adjustUnread(counts, alertScope(alert), -1));
    try {
      await clientRef.current.markAlertNotRelevant(alertId);
    } catch (feedbackError) {
      console.error("Failed to dismiss alert", feedbackError);
      setAlerts((current) => [...current.filter((candidate) => candidate.id !== alertId), alert].sort(byNewest));
      if (!alert.isRead) setUnread((counts) => adjustUnread(counts, alertScope(alert), 1));
      setError("alertUpdateFailed");
    }
  }, [alerts]);

  const dismissError = useCallback(() => setError(null), []);

  return { alerts, unread, isLoading, error, loadAlerts, refreshUnread, markRead, markAllRead, notRelevant, dismissError };
}
