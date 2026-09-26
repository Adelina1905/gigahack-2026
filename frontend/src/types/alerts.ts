// UI shapes of project alerts. The wire types are in api/types and are mapped
// to these in api/mappers.

export interface Alert {
  id: number;
  projectId: string;
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
}

export interface AlertTopic {
  id: number;
  label: string;
  query: string;
  // Extracted from the project's questions rather than typed by the user.
  isAuto: boolean;
  minScore: number | null;
}

export interface AlertSettings {
  projectId: string;
  enabled: boolean;
  prompted: boolean;
  topics: AlertTopic[];
  lastScanAt: number | null;
}

export const NO_UNREAD_ALERTS: UnreadAlertCounts = { total: 0, byProject: {} };
