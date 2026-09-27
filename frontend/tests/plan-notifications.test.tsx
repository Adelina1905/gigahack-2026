import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render as renderRaw, renderHook, screen, within } from "@testing-library/react";
import AlertBell from "../src/components/alerts/AlertBell";
import PlanNotificationToast from "../src/components/notifications/PlanNotificationToast";
import { usePlanNotifications } from "../src/hooks/usePlanNotifications";
import { useDemoNotificationShortcut } from "../src/hooks/useDemoNotificationShortcut";
import { I18nContext } from "../src/i18n/context";
import { MESSAGES } from "../src/i18n/messages";
import type { PlanNotification } from "../src/types/planNotification";
import type { PlanTracker } from "../src/types/tracker";

const en = MESSAGES.en;
const wrapper = ({ children }: { children: React.ReactNode }) => (
  <I18nContext.Provider value={{ locale: "en", setLocale: () => {}, t: en }}>{children}</I18nContext.Provider>
);
const render = (ui: React.ReactElement) => renderRaw(ui, { wrapper });

const tracker: PlanTracker = {
  id: "t1", projectId: null, name: "Coffee shop on Dacia Street", plan: "Open a coffee shop",
  location: "Dacia Street", summary: "", topics: ["Road construction and access restrictions"],
  risks: [], opportunities: [], dataThrough: "2026-09-24", isExample: true, updatedAt: 1,
};

const notification: PlanNotification = {
  id: "n1", trackerId: tracker.id, trackerName: tracker.name, scenarioId: "roadWorks",
  matchedTopic: tracker.topics[0], sourceTitle: "Example source", sourceUrl: "https://www.chisinau.md/ro",
  publishedDate: "2026-09-27", createdAt: 2, isRead: false, isExample: true,
};

beforeEach(() => localStorage.clear());
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe("plan notification prototype", () => {
  it("deterministically creates, persists and reads an example update", () => {
    const { result } = renderHook(() => usePlanNotifications());
    act(() => { result.current.triggerExample([tracker]); });
    expect(result.current.notifications[0]).toMatchObject({
      trackerId: "t1", scenarioId: "roadWorks", matchedTopic: tracker.topics[0], isRead: false,
    });
    expect(result.current.unreadCount).toBe(1);
    expect(JSON.parse(localStorage.getItem("municipal-plan-notifications-v1") ?? "[]")).toHaveLength(1);
    act(() => { result.current.markRead(result.current.notifications[0].id); });
    expect(result.current.unreadCount).toBe(0);
  });

  it("combines plan updates with the existing notification bell", () => {
    const calls = { opened: [] as string[] };
    render(<AlertBell alerts={[]} unreadTotal={0} projects={[]} onOpen={() => {}}
      onMarkRead={() => {}} onMarkAllRead={() => {}} onNotRelevant={() => {}} onAsk={() => {}}
      planNotifications={[notification]} planUnreadTotal={1}
      onOpenPlanNotification={(item) => calls.opened.push(item.id)} onMarkPlanRead={() => {}}
      onMarkAllPlanRead={() => {}} onDismissPlanNotification={() => {}} />);

    fireEvent.click(screen.getByRole("button", { name: en.alerts.bell(1) }));
    const item = screen.getByRole("listitem", { name: en.planNotifications.scenarios.roadWorks.title });
    expect(item.textContent).toContain(en.planNotifications.exampleBadge);
    fireEvent.click(within(item).getByRole("button", { name: en.planNotifications.viewUpdate }));
    expect(calls.opened).toEqual(["n1"]);
  });

  it("triggers from 9 but not while typing", () => {
    const trigger = vi.fn();
    renderHook(() => useDemoNotificationShortcut(true, trigger));
    fireEvent.keyDown(window, { key: "9" });
    expect(trigger).toHaveBeenCalledOnce();
    const input = document.createElement("input");
    document.body.appendChild(input);
    fireEvent.keyDown(input, { key: "9" });
    expect(trigger).toHaveBeenCalledOnce();
    input.remove();
  });

  it("auto-dismisses the temporary notification", () => {
    vi.useFakeTimers();
    const close = vi.fn();
    render(<PlanNotificationToast notification={notification} onOpen={() => {}} onClose={close} />);
    expect(screen.getByRole("status").textContent).toContain(en.planNotifications.toast(tracker.name));
    act(() => { vi.advanceTimersByTime(7000); });
    expect(close).toHaveBeenCalledOnce();
  });
});
