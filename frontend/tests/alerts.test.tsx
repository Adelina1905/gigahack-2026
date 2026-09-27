import React from "react";
import { afterEach, describe, expect, it } from "vitest";
import { act, cleanup, fireEvent, render as renderRaw, screen, waitFor, within } from "@testing-library/react";
import AlertBell from "../src/components/alerts/AlertBell";
import AlertsDialog from "../src/components/alerts/AlertsDialog";
import ChatAlertPrompt, { ChatAlertNotice } from "../src/components/alerts/ChatAlertPrompt";
import Sidebar from "../src/components/Sidebar";
import { toAlert, toAlertSettings, toUnreadAlertCounts } from "../src/api/mappers";
import * as mockClient from "../src/api/mockClient";
import type { AlertScanView, AlertSettingsView, AlertTopicView, AlertUnreadCountView, AlertView } from "../src/api/types";
import { adjustUnread, useAlerts, type AlertsClient } from "../src/hooks/useAlerts";
import { alertScopeForChat, useAlertOptIn, type AlertOptInClient } from "../src/hooks/useAlertOptIn";
import { useAlertOfferPreference } from "../src/hooks/useAlertOfferPreference";
import type { AlertSettingsClient } from "../src/hooks/useAlertSettings";
import { ApiError } from "../src/api/client";
import { I18nContext } from "../src/i18n/context";
import { MESSAGES } from "../src/i18n/messages";
import type { Alert, AlertScope } from "../src/types/alerts";
import { DEFAULT_CHAT_NAME, type ChatSummary, type ProjectSummary } from "../src/types/chat";

afterEach(cleanup);
const en = MESSAGES.en;
const render = (ui: React.ReactElement) =>
  renderRaw(<I18nContext.Provider value={{ locale: "en", setLocale: () => {}, t: en }}>{ui}</I18nContext.Provider>);

const alertView = (overrides: Partial<AlertView> = {}): AlertView => ({
  id: 1, projectId: "p1", chatId: null, topicId: 7, topicLabel: "Transport public", documentId: "doc-1",
  title: "New trolleybus schedule", url: "https://www.chisinau.md/", source: "RTEC", district: "Centru",
  category: "Transport", publishedDate: "2026-09-24", excerpt: "Buses run every 8 minutes.", score: 0.7,
  createdAt: "2026-09-26T10:00:00Z", readAt: null, ...overrides,
});

const topicView = (overrides: Partial<AlertTopicView> = {}): AlertTopicView => ({
  id: 7, label: "Transport public", query: "transport public", source: "AUTO", minScore: null, ...overrides,
});

const settingsView = (overrides: Partial<AlertSettingsView> = {}): AlertSettingsView => ({
  projectId: "p1", chatId: null, enabled: false, prompted: false, topics: [], lastScanAt: null, ...overrides,
});

// The wire settings of one scope.
const scopeSettings = (scope: AlertScope, overrides: Partial<AlertSettingsView> = {}) =>
  settingsView({
    projectId: scope.kind === "project" ? scope.id : null,
    chatId: scope.kind === "chat" ? scope.id : null,
    ...overrides,
  });

const label = (scope: AlertScope) => `${scope.kind} ${scope.id}`;

describe("alert mappers", () => {
  it("maps an alert and derives its read state", () => {
    expect(toAlert(alertView())).toEqual({
      id: 1, projectId: "p1", chatId: null, topicId: 7, topicLabel: "Transport public", documentId: "doc-1",
      title: "New trolleybus schedule", url: "https://www.chisinau.md/", source: "RTEC", district: "Centru",
      category: "Transport", publishedDate: "2026-09-24", excerpt: "Buses run every 8 minutes.", score: 0.7,
      createdAt: Date.parse("2026-09-26T10:00:00Z"), isRead: false,
    });
    expect(toAlert(alertView({ readAt: "2026-09-26T11:00:00Z" })).isRead).toBe(true);
    expect(toAlert(alertView({ projectId: null, chatId: "c1" }))).toMatchObject({ projectId: null, chatId: "c1" });
  });
  it("maps settings with their topics", () => {
    const settings = toAlertSettings(settingsView({
      enabled: true, prompted: true, lastScanAt: "2026-09-26T12:00:00Z",
      topics: [topicView(), topicView({ id: 8, label: "Parks", source: "USER", minScore: 0.8 })],
    }));
    expect(settings).toEqual({
      projectId: "p1", chatId: null, enabled: true, prompted: true, lastScanAt: Date.parse("2026-09-26T12:00:00Z"),
      topics: [
        { id: 7, label: "Transport public", query: "transport public", isAuto: true, minScore: null },
        { id: 8, label: "Parks", query: "transport public", isAuto: false, minScore: 0.8 },
      ],
    });
    expect(toAlertSettings(settingsView()).lastScanAt).toBeNull();
    expect(toAlertSettings(settingsView({ projectId: null, chatId: "c1" }))).toMatchObject({ projectId: null, chatId: "c1" });
  });
  it("maps unread counts and adjusts them per project or chat", () => {
    const counts = toUnreadAlertCounts({ total: 4, byProject: { p1: 2, p2: 1 }, byChat: { c1: 1 } });
    const project = (id: string): AlertScope => ({ kind: "project", id });
    expect(adjustUnread(counts, project("p1"), -1)).toEqual({ total: 3, byProject: { p1: 1, p2: 1 }, byChat: { c1: 1 } });
    expect(adjustUnread(counts, project("p2"), -5)).toEqual({ total: 3, byProject: { p1: 2 }, byChat: { c1: 1 } });
    expect(adjustUnread(counts, { kind: "chat", id: "c1" }, -1)).toEqual({ total: 3, byProject: { p1: 2, p2: 1 }, byChat: {} });
    expect(adjustUnread(counts, { kind: "chat", id: "c2" }, 1).byChat).toEqual({ c1: 1, c2: 1 });
    // Older servers without byChat still map.
    expect(toUnreadAlertCounts({ total: 0, byProject: {} } as unknown as AlertUnreadCountView).byChat).toEqual({});
  });
});

describe("ChatAlertPrompt", () => {
  const setup = (topics: string[], scopeKind: AlertScope["kind"] = "chat") => {
    const calls = { enabled: 0, declined: 0 };
    render(<ChatAlertPrompt scopeKind={scopeKind} topics={topics}
      onEnable={() => { calls.enabled += 1; }} onDecline={() => { calls.declined += 1; }} />);
    return calls;
  };

  it("names the topics and turns alerts on without taking focus", () => {
    const input = document.createElement("textarea");
    document.body.appendChild(input);
    input.focus();
    const calls = setup(["Școli și grădinițe", "Transport public"]);
    const region = screen.getByRole("region", { name: en.alerts.prompt.label });
    expect(within(region).getByText(en.alerts.prompt.topics(["Școli și grădinițe", "Transport public"]))).toBeTruthy();
    expect(document.activeElement).toBe(input);
    fireEvent.click(within(region).getByRole("button", { name: en.alerts.prompt.enable }));
    expect(calls).toEqual({ enabled: 1, declined: 0 });
    input.remove();
  });
  it("shows a generic line per scope, and Not now or × declines", () => {
    const calls = setup([]);
    expect(screen.getByText(en.alerts.prompt.generic.chat)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: en.alerts.prompt.notNow }));
    fireEvent.click(screen.getByRole("button", { name: en.alerts.prompt.dismiss }));
    expect(calls).toEqual({ enabled: 0, declined: 2 });
    cleanup();
    setup([], "project");
    expect(screen.getByText(en.alerts.prompt.generic.project)).toBeTruthy();
  });
  it("disables its buttons while saving", () => {
    render(<ChatAlertPrompt scopeKind="chat" topics={[]} isSaving onEnable={() => {}} onDecline={() => {}} />);
    expect((screen.getByRole("button", { name: en.alerts.prompt.enable }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByRole("status").textContent).toBe(en.alerts.prompt.saving);
  });
});

describe("alertScopeForChat", () => {
  it("uses the project for a chat in a project and the chat otherwise", () => {
    expect(alertScopeForChat({ id: "c1", projectId: null })).toEqual({ kind: "chat", id: "c1" });
    expect(alertScopeForChat({ id: "c2", projectId: "p1" })).toEqual({ kind: "project", id: "p1" });
  });
});

// Hand-written stand-in for the opt-in endpoints of both scopes.
class FakeOptInClient implements AlertOptInClient {
  calls: string[] = [];
  // The backend saves the answer, then answers 503 when the Python service is down.
  unavailable = false;
  prompted = new Set<string>();
  constructor(public topics: AlertTopicView[] = [], prompted: string[] = []) {
    prompted.forEach(key => this.prompted.add(key));
  }
  private get(scope: AlertScope) {
    this.calls.push(`get ${label(scope)}`);
    return scopeSettings(scope, { prompted: this.prompted.has(label(scope)) });
  }
  private refresh(scope: AlertScope) {
    this.calls.push(`refresh ${label(scope)}`);
    if (this.unavailable) throw new ApiError("Alerts unavailable", 503);
    return scopeSettings(scope, { prompted: this.prompted.has(label(scope)), topics: this.topics });
  }
  private put(scope: AlertScope, enabled: boolean) {
    this.calls.push(`put ${label(scope)} ${enabled}`);
    this.prompted.add(label(scope));
    if (this.unavailable) throw new ApiError("Alerts unavailable", 503);
    return scopeSettings(scope, { enabled, prompted: true, topics: this.topics });
  }
  getAlertSettings = async (id: string) => this.get({ kind: "project", id });
  refreshAlertTopics = async (id: string) => this.refresh({ kind: "project", id });
  updateAlertSettings = async (id: string, enabled: boolean) => this.put({ kind: "project", id }, enabled);
  getChatAlertSettings = async (id: string) => this.get({ kind: "chat", id });
  refreshChatAlertTopics = async (id: string) => this.refresh({ kind: "chat", id });
  updateChatAlertSettings = async (id: string, enabled: boolean) => this.put({ kind: "chat", id }, enabled);
}

interface OptInHarnessProps {
  client: AlertOptInClient;
  // The open chat; its scope comes from alertScopeForChat like in the app.
  chat: { id: string; projectId: string | null };
  onEnabled?: () => void;
  offerEnabled?: boolean;
}

function OptInHarness({ client, chat, onEnabled, offerEnabled = true }: OptInHarnessProps) {
  const optIn = useAlertOptIn(client, { onEnabled, enabled: offerEnabled, noticeMs: 50 });
  const offer = optIn.offer?.chatId === chat.id ? optIn.offer : null;
  return (
    <>
      <button type="button" onClick={() => void optIn.consider(alertScopeForChat(chat), chat.id)}>reply arrived</button>
      {offer && (
        <ChatAlertPrompt scopeKind={offer.scope.kind} topics={offer.topics.map(topic => topic.label)}
          isSaving={optIn.isSaving} error={optIn.error} onEnable={optIn.enable} onDecline={optIn.decline} />
      )}
      {!offer && optIn.notice && (
        <ChatAlertNotice message={optIn.notice.kind === "enabled" ? en.alerts.prompt.enabled : en.errors.alertsUnavailable} />
      )}
    </>
  );
}

const promptRegion = () => screen.findByRole("region", { name: en.alerts.prompt.label });
const noPrompt = () => expect(screen.queryByRole("region", { name: en.alerts.prompt.label })).toBeNull();

describe("alert opt-in trigger", () => {
  it("asks about a chat outside projects with the chat's own topics, once", async () => {
    const client = new FakeOptInClient([topicView()]);
    let enabled = 0;
    render(<OptInHarness client={client} chat={{ id: "c1", projectId: null }} onEnabled={() => { enabled += 1; }} />);
    fireEvent.click(screen.getByRole("button", { name: "reply arrived" }));
    const region = await promptRegion();
    expect(within(region).getByText(en.alerts.prompt.topics(["Transport public"]))).toBeTruthy();

    fireEvent.click(within(region).getByRole("button", { name: en.alerts.prompt.enable }));
    await waitFor(noPrompt);
    expect(enabled).toBe(1);
    expect(screen.getByRole("status").textContent).toContain(en.alerts.prompt.enabled);
    // The confirmation goes away on its own.
    await waitFor(() => expect(screen.queryByTestId("chat-alert-notice")).toBeNull());

    // Later replies in the same chat never ask again.
    fireEvent.click(screen.getByRole("button", { name: "reply arrived" }));
    await act(async () => {});
    noPrompt();
    expect(client.calls).toEqual(["get chat c1", "refresh chat c1", "put chat c1 true"]);
  });
  it("asks about the project for a chat inside a project", async () => {
    const client = new FakeOptInClient();
    render(<OptInHarness client={client} chat={{ id: "c2", projectId: "p1" }} />);
    fireEvent.click(screen.getByRole("button", { name: "reply arrived" }));
    const region = await promptRegion();
    expect(within(region).getByText(en.alerts.prompt.generic.project)).toBeTruthy();
    fireEvent.click(within(region).getByRole("button", { name: en.alerts.prompt.notNow }));
    await waitFor(noPrompt);
    expect(client.calls).toEqual(["get project p1", "refresh project p1", "put project p1 false"]);
  });
  it("saves × as disabled", async () => {
    const client = new FakeOptInClient();
    render(<OptInHarness client={client} chat={{ id: "c1", projectId: null }} />);
    fireEvent.click(screen.getByRole("button", { name: "reply arrived" }));
    fireEvent.click(within(await promptRegion()).getByRole("button", { name: en.alerts.prompt.dismiss }));
    await waitFor(noPrompt);
    expect(client.calls.at(-1)).toBe("put chat c1 false");
  });
  it("does not ask when the scope was already prompted", async () => {
    const client = new FakeOptInClient([], ["chat c1"]);
    render(<OptInHarness client={client} chat={{ id: "c1", projectId: null }} />);
    fireEvent.click(screen.getByRole("button", { name: "reply arrived" }));
    await act(async () => {});
    noPrompt();
    expect(client.calls).toEqual(["get chat c1"]);
  });
  it("never asks while the global switch is off", async () => {
    const client = new FakeOptInClient();
    render(<OptInHarness client={client} chat={{ id: "c1", projectId: null }} offerEnabled={false} />);
    fireEvent.click(screen.getByRole("button", { name: "reply arrived" }));
    await act(async () => {});
    noPrompt();
    expect(client.calls).toEqual([]);
  });
  it("asks with the generic line and never re-asks after a saved answer when matching is unavailable", async () => {
    const client = new FakeOptInClient();
    client.unavailable = true;
    let enabled = 0;
    render(<OptInHarness client={client} chat={{ id: "c1", projectId: null }} onEnabled={() => { enabled += 1; }} />);
    fireEvent.click(screen.getByRole("button", { name: "reply arrived" }));
    expect(within(await promptRegion()).getByText(en.alerts.prompt.generic.chat)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: en.alerts.prompt.enable }));
    await waitFor(noPrompt);
    expect(screen.getByRole("status").textContent).toContain(en.errors.alertsUnavailable);
    expect(enabled).toBe(0);
    fireEvent.click(screen.getByRole("button", { name: "reply arrived" }));
    await act(async () => {});
    noPrompt();
  });
});

function PreferenceHarness() {
  const [enabled, setEnabled] = useAlertOfferPreference();
  return <button type="button" aria-pressed={enabled} onClick={() => setEnabled(!enabled)}>offer</button>;
}

describe("useAlertOfferPreference", () => {
  it("defaults to on and remembers the choice", () => {
    localStorage.clear();
    render(<PreferenceHarness />);
    const toggle = screen.getByRole("button", { name: "offer" });
    expect(toggle.getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-pressed")).toBe("false");
    cleanup();
    render(<PreferenceHarness />);
    expect(screen.getByRole("button", { name: "offer" }).getAttribute("aria-pressed")).toBe("false");
    localStorage.clear();
  });
});

const projects: ProjectSummary[] = [
  { id: "p1", name: "Transport", updatedAt: 2 },
  { id: "p2", name: "Education", updatedAt: 1 },
];

const chats: ChatSummary[] = [
  { id: "c1", name: "Water outages", projectId: null, updatedAt: 3 },
  { id: "c2", name: DEFAULT_CHAT_NAME, projectId: null, updatedAt: 2 },
];

describe("AlertBell", () => {
  const alerts: Alert[] = [
    toAlert(alertView()),
    toAlert(alertView({ id: 2, projectId: "p2", topicLabel: "Școli", title: "Kindergarten enrolment",
      url: "javascript:alert(1)", readAt: "2026-09-26T11:00:00Z", createdAt: "2026-09-26T09:00:00Z" })),
  ];

  const setup = (overrides: Partial<React.ComponentProps<typeof AlertBell>> = {}) => {
    const calls = { opened: 0, read: [] as number[], allRead: 0, notRelevant: [] as number[], asked: [] as Alert[] };
    render(<AlertBell alerts={alerts} unreadTotal={1} projects={projects} chats={chats}
      onOpen={() => { calls.opened += 1; }}
      onMarkRead={id => calls.read.push(id)}
      onMarkAllRead={() => { calls.allRead += 1; }}
      onNotRelevant={id => calls.notRelevant.push(id)}
      onAsk={alert => calls.asked.push(alert)} {...overrides} />);
    return calls;
  };
  const bell = (count: number) => screen.getByRole("button", { name: en.alerts.bell(count) });

  it("shows the unread count and loads the list when opened", () => {
    const calls = setup();
    expect(screen.getByTestId("alert-badge").textContent).toBe("1");
    expect(bell(1).getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(bell(1));
    expect(calls.opened).toBe(1);
    expect(bell(1).getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("dialog", { name: en.alerts.panelTitle })).toBeTruthy();
  });
  it("labels each alert with its project, source and topic", () => {
    setup();
    fireEvent.click(bell(1));
    const transport = screen.getByRole("region", { name: "Transport" });
    const alert = within(transport).getByRole("listitem", { name: "New trolleybus schedule" });
    expect(alert.textContent).toContain("RTEC · Centru");
    expect(alert.textContent).toContain(`${en.alerts.because}Transport public`);
    const source = within(alert).getByRole("link", { name: en.alerts.openSource });
    expect(source.getAttribute("href")).toBe("https://www.chisinau.md/");
    expect(source.getAttribute("target")).toBe("_blank");

    // Unsafe links are not rendered; read alerts have no Mark read action.
    const education = within(screen.getByRole("region", { name: "Education" }))
      .getByRole("listitem", { name: "Kindergarten enrolment" });
    expect(within(education).queryByRole("link")).toBeNull();
    expect(within(education).queryByRole("button", { name: en.alerts.markRead })).toBeNull();
  });
  it("marks read, dismisses, asks and marks all read", () => {
    const calls = setup();
    fireEvent.click(bell(1));
    const alert = screen.getByRole("listitem", { name: "New trolleybus schedule" });
    fireEvent.click(within(alert).getByRole("button", { name: en.alerts.markRead }));
    fireEvent.click(within(alert).getByRole("button", { name: en.alerts.notRelevant }));
    fireEvent.click(screen.getByRole("button", { name: en.alerts.markAllRead }));
    expect(calls).toMatchObject({ read: [1], notRelevant: [1], allRead: 1 });

    fireEvent.click(within(alert).getByRole("button", { name: en.alerts.askAbout }));
    expect(calls.asked.map(alert => alert.id)).toEqual([1]);
    // Asking closes the panel.
    expect(screen.queryByRole("dialog")).toBeNull();
  });
  it("labels conversation alerts with the conversation's name and asks there", () => {
    const calls = setup({ alerts: [
      toAlert(alertView({ id: 3, projectId: null, chatId: "c1", title: "Water outage on Alba Iulia" })),
      toAlert(alertView({ id: 4, projectId: null, chatId: "c2", title: "Unnamed chat alert", documentId: "doc-4" })),
      toAlert(alertView({ id: 5, projectId: null, chatId: "gone", title: "Orphan alert", documentId: "doc-5" })),
    ] });
    fireEvent.click(bell(1));
    const water = screen.getByRole("region", { name: "Water outages" });
    const alert = within(water).getByRole("listitem", { name: "Water outage on Alba Iulia" });
    // The stored default name is shown translated.
    expect(within(screen.getByRole("region", { name: en.sidebar.newChat })).getByRole("listitem")).toBeTruthy();
    expect(screen.getByRole("region", { name: en.alerts.unknownChat })).toBeTruthy();

    fireEvent.click(within(alert).getByRole("button", { name: en.alerts.askAbout }));
    expect(calls.asked.map(asked => [asked.id, asked.chatId, asked.projectId])).toEqual([[3, "c1", null]]);
  });
  it("switches offering alerts in conversations from the panel", () => {
    const changes: boolean[] = [];
    setup({ offerAlerts: true, onOfferAlertsChange: value => changes.push(value) });
    fireEvent.click(bell(1));
    const toggle = screen.getByRole("switch", { name: en.alerts.offer.label });
    expect(toggle.getAttribute("aria-checked")).toBe("true");
    fireEvent.click(toggle);
    expect(changes).toEqual([false]);
  });
  it("shows an empty state and closes on Escape", () => {
    setup({ alerts: [], unreadTotal: 0 });
    expect(screen.queryByTestId("alert-badge")).toBeNull();
    fireEvent.click(bell(0));
    expect(screen.getByText(en.alerts.empty)).toBeTruthy();
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(bell(0));
  });
});

// Hand-written stand-in for the alert list endpoints.
class FakeAlertsClient implements AlertsClient {
  calls: string[] = [];
  failFeedback = false;
  constructor(public rows: AlertView[]) {}
  private counts(): AlertUnreadCountView {
    const byProject: Record<string, number> = {};
    const byChat: Record<string, number> = {};
    for (const row of this.rows.filter(candidate => !candidate.readAt)) {
      if (row.projectId) byProject[row.projectId] = (byProject[row.projectId] ?? 0) + 1;
      else if (row.chatId) byChat[row.chatId] = (byChat[row.chatId] ?? 0) + 1;
    }
    return { total: this.rows.filter(row => !row.readAt).length, byProject, byChat };
  }
  getAlerts = async () => [...this.rows];
  getAlertUnreadCount = async () => this.counts();
  markAlertRead = async (id: number) => {
    this.calls.push(`read ${id}`);
    const row = this.rows.find(candidate => candidate.id === id)!;
    row.readAt = "2026-09-26T12:00:00Z";
    return row;
  };
  markAllAlertsRead = async (request: { projectId?: string | null; chatId?: string | null } = {}) => {
    this.calls.push(`read-all ${JSON.stringify(request)}`);
    for (const row of this.rows) row.readAt ??= "2026-09-26T12:00:00Z";
    return { updated: this.rows.length };
  };
  markAlertNotRelevant = async (id: number) => {
    this.calls.push(`not-relevant ${id}`);
    if (this.failFeedback) throw new ApiError("boom", 500);
    this.rows = this.rows.filter(row => row.id !== id);
  };
}

function BellHarness({ client }: { client: AlertsClient }) {
  const alerts = useAlerts(client);
  return (
    <AlertBell alerts={alerts.alerts} unreadTotal={alerts.unread.total} projects={projects} chats={chats}
      isLoading={alerts.isLoading} error={alerts.error} onOpen={() => void alerts.loadAlerts()}
      onMarkRead={id => void alerts.markRead(id)} onMarkAllRead={() => void alerts.markAllRead(null)}
      onNotRelevant={id => void alerts.notRelevant(id)} onAsk={() => {}} onDismissError={alerts.dismissError} />
  );
}

describe("useAlerts with the bell", () => {
  const rows = () => [alertView(), alertView({ id: 2, title: "Road repairs", documentId: "doc-2" })];

  it("marks an alert read and drops a not-relevant one", async () => {
    const client = new FakeAlertsClient(rows());
    render(<BellHarness client={client} />);
    fireEvent.click(await screen.findByRole("button", { name: en.alerts.bell(2) }));
    const first = await screen.findByRole("listitem", { name: "New trolleybus schedule" });

    fireEvent.click(within(first).getByRole("button", { name: en.alerts.markRead }));
    expect(screen.getByTestId("alert-badge").textContent).toBe("1");
    await waitFor(() => expect(client.calls).toEqual(["read 1"]));
    expect(within(first).queryByRole("button", { name: en.alerts.markRead })).toBeNull();

    const second = screen.getByRole("listitem", { name: "Road repairs" });
    fireEvent.click(within(second).getByRole("button", { name: en.alerts.notRelevant }));
    expect(screen.queryByRole("listitem", { name: "Road repairs" })).toBeNull();
    expect(screen.queryByTestId("alert-badge")).toBeNull();
    await waitFor(() => expect(client.calls).toEqual(["read 1", "not-relevant 2"]));
  });
  it("counts a conversation's alerts and marks everything read", async () => {
    const client = new FakeAlertsClient([alertView(), alertView({ id: 2, projectId: null, chatId: "c1", documentId: "doc-2" })]);
    render(<BellHarness client={client} />);
    fireEvent.click(await screen.findByRole("button", { name: en.alerts.bell(2) }));
    await screen.findByRole("region", { name: "Water outages" });
    fireEvent.click(screen.getByRole("button", { name: en.alerts.markAllRead }));
    expect(screen.queryByTestId("alert-badge")).toBeNull();
    await waitFor(() => expect(client.calls).toEqual(["read-all {}"]));
  });
  it("restores a dismissed alert when the server refuses", async () => {
    const client = new FakeAlertsClient(rows());
    client.failFeedback = true;
    render(<BellHarness client={client} />);
    fireEvent.click(await screen.findByRole("button", { name: en.alerts.bell(2) }));
    const alert = await screen.findByRole("listitem", { name: "Road repairs" });
    fireEvent.click(within(alert).getByRole("button", { name: en.alerts.notRelevant }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByText(en.errors.alertUpdateFailed)).toBeTruthy();
    expect(screen.getByRole("listitem", { name: "Road repairs" })).toBeTruthy();
    expect(screen.getByTestId("alert-badge").textContent).toBe("2");
  });
});

// Hand-written stand-in for one subscription's settings endpoints; every call
// records which scope it was made for.
class FakeSettingsClient implements AlertSettingsClient {
  calls: string[] = [];
  scopes = new Set<string>();
  unavailable = false;
  nextId = 100;
  scanCreated = [2, 0];
  constructor(public settings: AlertSettingsView) {}
  private seen(scope: AlertScope) {
    this.scopes.add(label(scope));
  }
  private get = async (scope: AlertScope) => {
    this.seen(scope);
    return structuredClone(this.settings);
  };
  private put = async (scope: AlertScope, enabled: boolean) => {
    this.seen(scope);
    this.calls.push(`enabled ${enabled}`);
    this.settings = { ...this.settings, enabled, prompted: true };
    if (this.unavailable) throw new ApiError("Alerts unavailable", 503);
    return structuredClone(this.settings);
  };
  private add = async (scope: AlertScope, topicLabel: string) => {
    this.seen(scope);
    this.calls.push(`add ${topicLabel}`);
    const existing = this.settings.topics.find(topic => topic.label.toLowerCase() === topicLabel.toLowerCase());
    if (existing) return { ...existing };
    const topic = topicView({ id: this.nextId++, label: topicLabel, query: topicLabel, source: "USER" });
    this.settings.topics.push(topic);
    return topic;
  };
  private rename = async (scope: AlertScope, topicId: number, topicLabel: string) => {
    this.seen(scope);
    this.calls.push(`rename ${topicId} ${topicLabel}`);
    const topic = this.settings.topics.find(candidate => candidate.id === topicId)!;
    Object.assign(topic, { label: topicLabel, query: topicLabel, source: "USER" });
    return { ...topic };
  };
  private remove = async (scope: AlertScope, topicId: number) => {
    this.seen(scope);
    this.calls.push(`remove ${topicId}`);
    this.settings.topics = this.settings.topics.filter(topic => topic.id !== topicId);
  };
  private scan = async (scope: AlertScope): Promise<AlertScanView> => {
    this.seen(scope);
    this.calls.push("scan");
    if (this.unavailable) throw new ApiError("Alerts unavailable", 503);
    this.settings.lastScanAt = "2026-09-26T12:30:00Z";
    return { created: this.scanCreated.shift() ?? 0, matcher: "lexical" };
  };
  getAlertSettings = (id: string) => this.get({ kind: "project", id });
  updateAlertSettings = (id: string, enabled: boolean) => this.put({ kind: "project", id }, enabled);
  createAlertTopic = (id: string, topicLabel: string) => this.add({ kind: "project", id }, topicLabel);
  updateAlertTopic = (id: string, topicId: number, topicLabel: string) => this.rename({ kind: "project", id }, topicId, topicLabel);
  deleteAlertTopic = (id: string, topicId: number) => this.remove({ kind: "project", id }, topicId);
  scanProjectAlerts = (id: string) => this.scan({ kind: "project", id });
  getChatAlertSettings = (id: string) => this.get({ kind: "chat", id });
  updateChatAlertSettings = (id: string, enabled: boolean) => this.put({ kind: "chat", id }, enabled);
  createChatAlertTopic = (id: string, topicLabel: string) => this.add({ kind: "chat", id }, topicLabel);
  updateChatAlertTopic = (id: string, topicId: number, topicLabel: string) => this.rename({ kind: "chat", id }, topicId, topicLabel);
  deleteChatAlertTopic = (id: string, topicId: number) => this.remove({ kind: "chat", id }, topicId);
  scanChatAlerts = (id: string) => this.scan({ kind: "chat", id });
}

describe("AlertsDialog", () => {
  const setup = (unavailable = false) => {
    const client = new FakeSettingsClient(settingsView({ prompted: true, topics: [topicView()] }));
    client.unavailable = unavailable;
    const changes = { count: 0, closed: 0 };
    render(<AlertsDialog scope={{ kind: "project", id: "p1" }} title="Transport" client={client}
      onAlertsChanged={() => { changes.count += 1; }} onClose={() => { changes.closed += 1; }} />);
    return { client, changes };
  };

  it("turns alerts on and off with a labelled switch", async () => {
    const { client, changes } = setup();
    const toggle = await screen.findByRole("switch", { name: en.alerts.settings.switchLabel });
    expect(toggle.getAttribute("aria-checked")).toBe("false");
    expect(toggle.textContent).toContain(en.alerts.settings.off);

    fireEvent.click(toggle);
    await waitFor(() => expect(toggle.getAttribute("aria-checked")).toBe("true"));
    expect(toggle.textContent).toContain(en.alerts.settings.on);
    await waitFor(() => expect(changes.count).toBe(1));

    fireEvent.click(toggle);
    await waitFor(() => expect(client.calls).toEqual(["enabled true", "enabled false"]));
    expect(toggle.getAttribute("aria-checked")).toBe("false");
  });
  it("keeps the saved switch state when the first check is unavailable", async () => {
    const { client } = setup(true);
    const toggle = await screen.findByRole("switch", { name: en.alerts.settings.switchLabel });
    fireEvent.click(toggle);
    expect(await screen.findByText(en.errors.alertsUnavailable)).toBeTruthy();
    expect(toggle.getAttribute("aria-checked")).toBe("true");
    expect(client.settings.enabled).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: en.alerts.settings.checkNow }));
    await waitFor(() => expect(client.calls).toEqual(["enabled true", "scan"]));
    expect(screen.getByText(en.errors.alertsUnavailable)).toBeTruthy();
  });
  it("does not duplicate a topic the server already has", async () => {
    setup();
    expect(await screen.findByText("Transport public")).toBeTruthy();
    fireEvent.change(screen.getByRole("textbox", { name: en.alerts.settings.topicName }),
      { target: { value: "transport PUBLIC" } });
    fireEvent.click(screen.getByRole("button", { name: en.alerts.settings.add }));
    await waitFor(() => expect((screen.getByRole("textbox", { name: en.alerts.settings.topicName }) as HTMLInputElement).value).toBe(""));
    expect(screen.getAllByText("Transport public")).toHaveLength(1);
  });
  it("adds, renames and removes topics", async () => {
    const { client } = setup();
    expect(await screen.findByText("Transport public")).toBeTruthy();
    expect(screen.getByText(en.alerts.settings.auto)).toBeTruthy();

    const input = screen.getByRole("textbox", { name: en.alerts.settings.topicName });
    fireEvent.change(input, { target: { value: "  Parks  " } });
    fireEvent.click(screen.getByRole("button", { name: en.alerts.settings.add }));
    expect(await screen.findByText("Parks")).toBeTruthy();
    expect((input as HTMLInputElement).value).toBe("");

    fireEvent.click(screen.getByRole("button", { name: en.alerts.settings.rename("Transport public") }));
    const editor = screen.getAllByRole("textbox", { name: en.alerts.settings.topicName })[0];
    fireEvent.change(editor, { target: { value: "Trolleybuses" } });
    fireEvent.keyDown(editor, { key: "Enter" });
    expect(await screen.findByText("Trolleybuses")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: en.alerts.settings.remove("Parks") }));
    await waitFor(() => expect(screen.queryByText("Parks")).toBeNull());
    expect(client.calls).toEqual(["add Parks", "rename 7 Trolleybuses", "remove 100"]);
    // A renamed topic counts as the user's own.
    expect(screen.queryByText(en.alerts.settings.auto)).toBeNull();
  });
  it("checks now and reports the result", async () => {
    const { client, changes } = setup();
    expect(await screen.findByText(en.alerts.settings.neverScanned)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: en.alerts.settings.checkNow }));
    expect(await screen.findByText(en.alerts.settings.created(2))).toBeTruthy();
    expect(screen.getByText(/Last checked:/)).toBeTruthy();
    expect(changes.count).toBe(1);

    fireEvent.click(screen.getByRole("button", { name: en.alerts.settings.checkNow }));
    expect(await screen.findByText("No new updates")).toBeTruthy();
    expect(client.calls).toEqual(["scan", "scan"]);
    expect(changes.count).toBe(1);
  });
  it("manages a conversation's own alerts through the chat endpoints", async () => {
    const client = new FakeSettingsClient(scopeSettings({ kind: "chat", id: "c1" }, { prompted: true, topics: [topicView()] }));
    render(<AlertsDialog scope={{ kind: "chat", id: "c1" }} title="Water outages" client={client} onClose={() => {}} />);
    const toggle = await screen.findByRole("switch", { name: en.alerts.settings.chatSwitchLabel });
    expect(screen.getByText(en.alerts.settings.chatOffHint)).toBeTruthy();
    expect(screen.getByText("Water outages")).toBeTruthy();
    fireEvent.click(toggle);
    await waitFor(() => expect(toggle.getAttribute("aria-checked")).toBe("true"));
    fireEvent.click(screen.getByRole("button", { name: en.alerts.settings.remove("Transport public") }));
    fireEvent.click(screen.getByRole("button", { name: en.alerts.settings.checkNow }));
    await waitFor(() => expect(client.calls).toEqual(["enabled true", "remove 7", "scan"]));
    expect([...client.scopes]).toEqual(["chat c1"]);
  });
  it("closes without leaving the dialog when a topic edit is cancelled", async () => {
    const { changes } = setup();
    fireEvent.click(await screen.findByRole("button", { name: en.alerts.settings.rename("Transport public") }));
    fireEvent.keyDown(screen.getAllByRole("textbox", { name: en.alerts.settings.topicName })[0], { key: "Escape" });
    expect(changes.closed).toBe(0);
    expect(screen.getByText("Transport public")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: en.alerts.settings.close }));
    expect(changes.closed).toBe(1);
  });
});

describe("Sidebar trackers", () => {
  const noop = () => {};
  it("opens the dedicated tracker area and creates one from an expanded project", () => {
    const opened: string[] = [];
    const created: string[] = [];
    render(<Sidebar chats={[]} projects={projects} activeChatId={null} draftProjectId={null} isLoaded
      onNewChat={noop} onSelect={noop} onDelete={noop} onMoveChat={noop}
      onCreateProject={async () => null} onRenameProject={noop} onDeleteProject={noop} onNewChatInProject={noop}
      trackerCount={2} isTrackersOpen={false} onOpenTrackers={() => opened.push("trackers")}
      onCreateTracker={project => created.push(project.id)}
      isOpen onClose={noop} />);

    fireEvent.click(screen.getByRole("button", { name: en.trackers.open }));
    expect(opened).toEqual(["trackers"]);

    fireEvent.click(screen.getByRole("button", { name: "Education" }));
    fireEvent.click(screen.getByRole("button", { name: en.trackers.createForProject }));
    expect(created).toEqual(["p2"]);
  });
  it("shows a conversation's unread badge and opens its alert settings", () => {
    const opened: string[] = [];
    const now = Date.now();
    const sidebarChats: ChatSummary[] = [
      { id: "c1", name: "Water outages", projectId: null, updatedAt: now },
      { id: "c2", name: "Fairs", projectId: null, updatedAt: now },
      { id: "c3", name: "Buses", projectId: "p1", updatedAt: now },
      { id: "c4", name: "Kindergartens", projectId: "p2", updatedAt: now },
    ];
    render(<Sidebar chats={sidebarChats} projects={projects} activeChatId="c3" draftProjectId={null} isLoaded
      onNewChat={noop} onSelect={noop} onDelete={noop} onMoveChat={noop}
      onCreateProject={async () => null} onRenameProject={noop} onDeleteProject={noop} onNewChatInProject={noop}
      unreadAlertsByChat={{ c1: 2, c3: 1 }} onOpenChatAlerts={chat => opened.push(chat.id)}
      isOpen onClose={noop} />);
    const row = screen.getByRole("button", { name: "Water outages" });
    expect(within(row).getByTestId("chat-alert-badge").textContent).toBe("2");
    expect(document.getElementById(row.getAttribute("aria-describedby")!)!.textContent)
      .toBe(en.alerts.projectUnread(2));
    // Three actions need more room than two while they show.
    expect(row.className).toContain("group-hover:pr-[5.5rem]");
    expect(within(screen.getByRole("button", { name: "Fairs" })).queryByTestId("chat-alert-badge")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: en.alerts.settings.open("Fairs") }));
    expect(opened).toEqual(["c2"]);

    // A project chat with its own alerts keeps its badge and bell; others follow the project.
    const buses = screen.getByRole("button", { name: "Buses" });
    expect(within(buses).getByTestId("chat-alert-badge").textContent).toBe("1");
    fireEvent.click(screen.getByRole("button", { name: en.alerts.settings.open("Buses") }));
    expect(opened).toEqual(["c2", "c3"]);
    fireEvent.click(screen.getByRole("button", { name: "Education" }));
    expect(screen.queryByRole("button", { name: en.alerts.settings.open("Kindergartens") })).toBeNull();
  });
});

describe("mock alerts API", () => {
  it("extracts topics, backfills on opt-in and learns from Not relevant", async () => {
    localStorage.clear();
    const project = await mockClient.createProject("Education");
    const chat = await mockClient.createChat("Schools", undefined, project.id);
    await mockClient.createResponse(chat.id, "Când începe înscrierea la grădinițe și școli?");

    expect(await mockClient.getAlertSettings(project.id)).toMatchObject({ enabled: false, prompted: false, topics: [] });
    const refreshed = await mockClient.refreshAlertTopics(project.id);
    expect(refreshed.topics.map(topic => topic.label)).toEqual(["Școli și grădinițe"]);

    const enabled = await mockClient.updateAlertSettings(project.id, true);
    expect(enabled).toMatchObject({ enabled: true, prompted: true });
    const alerts = await mockClient.getAlerts();
    expect(alerts.length).toBeGreaterThan(0);
    expect(alerts.length).toBeLessThanOrEqual(3);
    expect(alerts[0]).toMatchObject({ projectId: project.id, topicLabel: "Școli și grădinițe", readAt: null });
    expect((await mockClient.getAlertUnreadCount()).byProject[project.id]).toBe(alerts.length);

    await mockClient.markAlertNotRelevant(alerts[0].id);
    const after = await mockClient.getAlerts();
    expect(after.map(alert => alert.id)).not.toContain(alerts[0].id);
    const topic = (await mockClient.getAlertSettings(project.id)).topics[0];
    expect(topic.minScore).toBeCloseTo(alerts[0].score + 0.01);

    await mockClient.markAllAlertsRead({ projectId: project.id });
    expect((await mockClient.getAlertUnreadCount()).total).toBe(0);
    // Dismissed documents are never alerted again.
    await mockClient.scanProjectAlerts(project.id);
    expect((await mockClient.getAlerts()).map(alert => alert.documentId)).not.toContain(alerts[0].documentId);
  });
  it("gives a chat outside projects its own subscription", async () => {
    localStorage.clear();
    const chat = await mockClient.createChat("Buses");
    await mockClient.createResponse(chat.id, "Ce rute de autobuz noi sunt în oraș?");

    expect(await mockClient.getChatAlertSettings(chat.id)).toMatchObject({ chatId: chat.id, projectId: null, prompted: false });
    const refreshed = await mockClient.refreshChatAlertTopics(chat.id);
    expect(refreshed.topics.map(topic => topic.label)).toEqual(["Transport public"]);
    await mockClient.updateChatAlertSettings(chat.id, true);
    const alerts = await mockClient.getAlerts({ chatId: chat.id });
    expect(alerts.length).toBeGreaterThan(0);
    expect(alerts[0]).toMatchObject({ chatId: chat.id, projectId: null });
    const counts = await mockClient.getAlertUnreadCount();
    expect(counts).toMatchObject({ total: alerts.length, byProject: {}, byChat: { [chat.id]: alerts.length } });

    await mockClient.markAllAlertsRead({ chatId: chat.id });
    expect((await mockClient.getAlertUnreadCount()).total).toBe(0);
    // Deleting the chat deletes its subscription and alerts.
    await mockClient.deleteChat(chat.id);
    expect(await mockClient.getAlerts()).toEqual([]);
    await expect(mockClient.getChatAlertSettings(chat.id)).rejects.toMatchObject({ status: 404 });
  });
});
