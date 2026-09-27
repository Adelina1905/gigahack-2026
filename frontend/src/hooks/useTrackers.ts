import { useCallback, useState } from "react";
import type { ProjectSummary } from "../types/chat";
import type { PlanTracker } from "../types/tracker";

const STORAGE_KEY = "municipal-plan-trackers-v1";

const exampleTracker: PlanTracker = {
  id: "example-coffee-shop",
  projectId: null,
  name: "Coffee shop on Dacia Street",
  plan: "Open a small coffee shop",
  location: "Dacia Street, Chișinău",
  summary:
    "A small neighborhood coffee shop that depends on easy pedestrian access, public transport and reliable deliveries.",
  topics: [
    "Commercial permits and authorizations",
    "Road construction and access restrictions",
    "Public transport changes",
    "Parking changes",
    "Utility interruptions",
    "Public events nearby",
  ],
  risks: ["Road closures", "Long construction projects", "Restricted delivery access"],
  opportunities: ["New transport stops", "Public events", "Improvements to sidewalks or public spaces"],
  dataThrough: "2026-09-24",
  isExample: true,
  updatedAt: Date.now(),
};

function loadTrackers(): PlanTracker[] {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    if (!value) return [exampleTracker];
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [exampleTracker];
  } catch {
    return [exampleTracker];
  }
}

function persist(trackers: PlanTracker[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(trackers));
  } catch {
    // The prototype remains usable when browser storage is unavailable.
  }
}

export function useTrackers() {
  const [trackers, setTrackers] = useState<PlanTracker[]>(loadTrackers);

  const update = useCallback((tracker: PlanTracker) => {
    setTrackers((current) => {
      const next = current.map((item) => (item.id === tracker.id ? { ...tracker, updatedAt: Date.now() } : item));
      persist(next);
      return next;
    });
  }, []);

  const create = useCallback((project?: ProjectSummary, details?: Partial<PlanTracker>) => {
    const tracker: PlanTracker = {
      id: crypto.randomUUID(),
      projectId: project?.id ?? null,
      name: details?.name ?? project?.name ?? "New plan tracker",
      plan: details?.plan ?? "",
      location: details?.location ?? "Chișinău",
      summary: details?.summary ?? "",
      topics: details?.topics ?? [],
      risks: details?.risks ?? [],
      opportunities: details?.opportunities ?? [],
      dataThrough: "2026-09-24",
      isExample: false,
      updatedAt: Date.now(),
    };
    setTrackers((current) => {
      const next = [tracker, ...current];
      persist(next);
      return next;
    });
    return tracker;
  }, []);

  const remove = useCallback((trackerId: string) => {
    setTrackers((current) => {
      const next = current.filter((item) => item.id !== trackerId);
      persist(next);
      return next;
    });
  }, []);

  return { trackers, create, update, remove };
}
