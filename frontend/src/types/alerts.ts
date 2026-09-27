// UI shapes of alerts. The wire types are in api/types and are mapped to
// these in api/mappers.

// Who an alert subscription belongs to: a project (shared by its chats) or a
// chat outside projects.
export type AlertScope = { kind: "project"; id: string } | { kind: "chat"; id: string };

export const scopeKey = (scope: AlertScope) => `${scope.kind}:${scope.id}`;

// The inverse of scopeKey (ids are UUIDs, so they hold no colon).
export function parseScopeKey(key: string): AlertScope {
  const separator = key.indexOf(":");
  const id = key.slice(separator + 1);
  return key.slice(0, separator) === "chat" ? { kind: "chat", id } : { kind: "project", id };
}

export interface Alert {
  id: number;
  // Exactly one of these is set.
  projectId: string | null;
  chatId: string | null;
  topicId: number | null;
  topicLabel: string;
  documentId: string;
  title: string;
  url: string | null;
  source: string | null;
  district: string | null;
  category: string | null;
  publishedDate: string | null; // YYYY-MM-DD, shown as a calendar date
  excerpt: string;
  score: number;
  createdAt: number;
  isRead: boolean;
}

export interface UnreadAlertCounts {
  total: number;
  byProject: Record<string, number>;
  byChat: Record<string, number>;
}

export interface AlertTopic {
  id: number;
  label: string;
  query: string;
  // Extracted from the questions rather than typed by the user.
  isAuto: boolean;
  minScore: number | null;
}

export interface AlertSettings {
  projectId: string | null;
  chatId: string | null;
  enabled: boolean;
  prompted: boolean;
  topics: AlertTopic[];
  lastScanAt: number | null;
}

export const NO_UNREAD_ALERTS: UnreadAlertCounts = { total: 0, byProject: {}, byChat: {} };

// The subscription an alert came from.
export const alertScope = (alert: Pick<Alert, "projectId" | "chatId">): AlertScope =>
  alert.projectId ? { kind: "project", id: alert.projectId } : { kind: "chat", id: alert.chatId ?? "" };
