export type DemoScenarioId = "roadWorks" | "transport" | "utilities";

export interface PlanNotification {
  id: string;
  trackerId: string;
  trackerName: string;
  scenarioId: DemoScenarioId;
  matchedTopic: string;
  sourceTitle: string;
  sourceUrl: string;
  publishedDate: string;
  createdAt: number;
  isRead: boolean;
  isExample: true;
}
