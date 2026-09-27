import React from "react";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render as renderRaw, screen } from "@testing-library/react";
import TrackersView from "../src/components/trackers/TrackersView";
import { I18nContext } from "../src/i18n/context";
import { MESSAGES } from "../src/i18n/messages";
import type { PlanTracker } from "../src/types/tracker";

afterEach(cleanup);
const en = MESSAGES.en;
const render = (ui: React.ReactElement) =>
  renderRaw(<I18nContext.Provider value={{ locale: "en", setLocale: () => {}, t: en }}>{ui}</I18nContext.Provider>);

const tracker: PlanTracker = {
  id: "t1",
  projectId: null,
  name: "Coffee shop on Dacia Street",
  plan: "Open a small coffee shop",
  location: "Dacia Street, Chișinău",
  summary: "A neighborhood coffee shop.",
  topics: ["Public transport", "Parking"],
  risks: [],
  opportunities: [],
  dataThrough: "2026-09-24",
  isExample: true,
  updatedAt: Date.now(),
};

const baseProps = {
  trackers: [tracker],
  projects: [],
  isCreating: false,
  creationProject: undefined,
  onBackToList: () => {},
  onStartCreate: () => {},
  onCancelCreate: () => {},
  onCompleteCreate: () => {},
  onUpdate: () => {},
  onRemove: () => {},
};

describe("Plan trackers", () => {
  it("uses a list landing view before opening a tracker", () => {
    const selected: string[] = [];
    render(<TrackersView {...baseProps} selectedId={null} onSelect={(id) => selected.push(id)} />);

    expect(screen.getByText("Dacia Street, Chișinău")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: en.trackers.openTracker(tracker.name) }));
    expect(selected).toEqual(["t1"]);
  });

  it("shows freshness, topics and updates but hides empty analytical sections", () => {
    render(<TrackersView {...baseProps} selectedId="t1" onSelect={() => {}} />);

    expect(screen.getByText(en.trackers.notLive)).toBeTruthy();
    expect(screen.getByText("Public transport")).toBeTruthy();
    expect(screen.getByText(en.trackers.noUpdates)).toBeTruthy();
    expect(screen.queryByText(en.trackers.risks)).toBeNull();
    expect(screen.queryByText(en.trackers.opportunities)).toBeNull();
  });

  it("creates a tracker through the deterministic three-step setup", () => {
    const completed: Array<Partial<PlanTracker>> = [];
    render(<TrackersView {...baseProps} trackers={[]} selectedId={null} isCreating creationProject={null}
      onSelect={() => {}} onCompleteCreate={(details) => completed.push(details)} />);

    fireEvent.change(screen.getByPlaceholderText(en.trackers.guidePlanPlaceholder), { target: { value: "Open a bakery" } });
    fireEvent.click(screen.getByRole("button", { name: en.trackers.continue }));
    fireEvent.change(screen.getByPlaceholderText(en.trackers.guideLocationPlaceholder), { target: { value: "Central Market" } });
    fireEvent.click(screen.getByRole("button", { name: en.trackers.continue }));
    fireEvent.click(screen.getByRole("button", { name: /Commercial permits/ }));
    fireEvent.click(screen.getByRole("button", { name: en.trackers.continue }));
    fireEvent.click(screen.getByRole("button", { name: en.trackers.confirmCreate }));

    expect(completed).toEqual([expect.objectContaining({
      name: "Open a bakery",
      plan: "Open a bakery",
      location: "Central Market",
      topics: ["Commercial permits"],
    })]);
  });

  it("supports cancelling setup and returning from details", () => {
    const calls: string[] = [];
    const { rerender } = render(<TrackersView {...baseProps} selectedId={null} isCreating onSelect={() => {}}
      onCancelCreate={() => calls.push("cancel")} />);
    fireEvent.click(screen.getByRole("button", { name: en.trackers.cancel }));

    rerender(<I18nContext.Provider value={{ locale: "en", setLocale: () => {}, t: en }}>
      <TrackersView {...baseProps} selectedId="t1" onSelect={() => {}} onBackToList={() => calls.push("back")} />
    </I18nContext.Provider>);
    fireEvent.click(screen.getByRole("button", { name: en.trackers.backToTrackers }));
    expect(calls).toEqual(["cancel", "back"]);
  });
});

