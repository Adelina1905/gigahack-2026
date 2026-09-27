import { useCallback, useState } from "react";
import type { PlanNotification, DemoScenarioId } from "../types/planNotification";
import type { PlanTracker } from "../types/tracker";

const STORAGE_KEY = "municipal-plan-notifications-v1";

const scenarios: Array<{
  id: DemoScenarioId;
  publishedDate: string;
  sourceTitle: string;
  sourceUrl: string;
  keywords: string[];
}> = [
  {
    id: "roadWorks",
    publishedDate: "2026-09-27",
    sourceTitle: "Example municipal road-works notice",
    sourceUrl: "https://www.chisinau.md/ro",
    keywords: ["road", "construction", "access", "lucr", "acces", "drum", "дорог", "строит", "доступ"],
  },
  {
    id: "transport",
    publishedDate: "2026-09-27",
    sourceTitle: "Example public-transport service notice",
    sourceUrl: "https://www.chisinau.md/ro",
    keywords: ["transport", "bus", "trolley", "rut", "маршрут", "транспорт"],
  },
  {
    id: "utilities",
    publishedDate: "2026-09-27",
    sourceTitle: "Example municipal utility notice",
    sourceUrl: "https://www.chisinau.md/ro",
    keywords: ["utilit", "water", "electric", "apă", "energie", "вод", "электр"],
  },
];

function loadNotifications(): PlanNotification[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function persist(notifications: PlanNotification[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(notifications));
  } catch {
    // The demonstration remains usable when storage is unavailable.
  }
}

function findMatch(trackers: PlanTracker[], offset: number) {
  const candidates = scenarios.flatMap((scenario) => trackers.flatMap((tracker) => {
    const matchedTopic = tracker.topics.find((topic) => {
      const normalized = topic.toLocaleLowerCase();
      return scenario.keywords.some((keyword) => normalized.includes(keyword));
    });
    return matchedTopic ? [{ scenario, tracker, matchedTopic }] : [];
  }));
  if (candidates.length > 0) return candidates[offset % candidates.length];
  const tracker = trackers[0];
  return tracker ? { scenario: scenarios[offset % scenarios.length], tracker, matchedTopic: tracker.topics[0] ?? tracker.plan } : null;
}

export function usePlanNotifications() {
  const [notifications, setNotifications] = useState<PlanNotification[]>(loadNotifications);

  const update = useCallback((change: (current: PlanNotification[]) => PlanNotification[]) => {
    setNotifications((current) => {
      const next = change(current);
      persist(next);
      return next;
    });
  }, []);

  const triggerExample = useCallback((trackers: PlanTracker[]) => {
    const match = findMatch(trackers, notifications.length);
    if (!match) return null;
    const notification: PlanNotification = {
      id: crypto.randomUUID(),
      trackerId: match.tracker.id,
      trackerName: match.tracker.name,
      scenarioId: match.scenario.id,
      matchedTopic: match.matchedTopic,
      sourceTitle: match.scenario.sourceTitle,
      sourceUrl: match.scenario.sourceUrl,
      publishedDate: match.scenario.publishedDate,
      createdAt: Date.now(),
      isRead: false,
      isExample: true,
    };
    update((current) => [notification, ...current]);
    return notification;
  }, [notifications.length, update]);

  const markRead = useCallback((id: string) => update((current) =>
    current.map((item) => item.id === id ? { ...item, isRead: true } : item)), [update]);
  const markAllRead = useCallback(() => update((current) =>
    current.map((item) => ({ ...item, isRead: true }))), [update]);
  const dismiss = useCallback((id: string) => update((current) =>
    current.filter((item) => item.id !== id)), [update]);

  return {
    notifications,
    unreadCount: notifications.filter((item) => !item.isRead).length,
    triggerExample,
    markRead,
    markAllRead,
    dismiss,
  };
}
