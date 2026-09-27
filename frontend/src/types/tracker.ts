export interface PlanTracker {
  id: string;
  projectId: string | null;
  name: string;
  plan: string;
  location: string;
  summary: string;
  topics: string[];
  risks: string[];
  opportunities: string[];
  dataThrough: string;
  isExample: boolean;
  updatedAt: number;
}

