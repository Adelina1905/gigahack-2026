import React from "react";
import { afterEach, describe, expect, it } from "vitest";
import { act, cleanup, fireEvent, render as renderRaw, screen, waitFor, within } from "@testing-library/react";
import AlertBell from "../src/components/alerts/AlertBell";
import AlertOptInDialog from "../src/components/alerts/AlertOptInDialog";
import ProjectAlertsDialog from "../src/components/alerts/ProjectAlertsDialog";
import Sidebar from "../src/components/Sidebar";
import { toAlert, toAlertSettings, toUnreadAlertCounts } from "../src/api/mappers";
import * as mockClient from "../src/api/mockClient";
import type { AlertScanView, AlertSettingsView, AlertTopicView, AlertUnreadCountView, AlertView } from "../src/api/types";
import { adjustUnread, useAlerts, type AlertsClient } from "../src/hooks/useAlerts";
import { useAlertOptIn, type AlertOptInClient } from "../src/hooks/useAlertOptIn";
import type { AlertSettingsClient } from "../src/hooks/useAlertSettings";
import { ApiError } from "../src/api/client";
import { I18nContext } from "../src/i18n/context";
import { MESSAGES } from "../src/i18n/messages";
import type { Alert } from "../src/types/alerts";
import type { ProjectSummary } from "../src/types/chat";

afterEach(cleanup);
const en = MESSAGES.en;
const render = (ui: React.ReactElement) =>
  renderRaw(<I18nContext.Provider value={{ locale: "en", setLocale: () => {}, t: en }}>{ui}</I18nContext.Provider>);

const alertView = (overrides: Partial<AlertView> = {}): AlertView => ({
  id: 1, projectId: "p1", topicId: 7, topicLabel: "Transport public", documentId: "doc-1",
  title: "New trolleybus schedule", url: "https://www.chisinau.md/", source: "RTEC", district: "Centru",
  category: "Transport", publishedDate: "2026-09-24", excerpt: "Buses run every 8 minutes.", score: 0.7,
  createdAt: "2026-09-26T10:00:00Z", readAt: null, ...overrides,
});

const topicView = (overrides: Partial<AlertTopicView> = {}): AlertTopicView => ({
  id: 7, label: "Transport public", query: "transport public", source: "AUTO", minScore: null, ...overrides,
});

const settingsView = (overrides: Partial<AlertSettingsView> = {}): AlertSettingsView => ({
  projectId: "p1", enabled: false, prompted: false, topics: [], lastScanAt: null, ...overrides,
});

describe("alert mappers", () => {
  it("maps an alert and derives its read state", () => {
    expect(toAlert(alertView())).toEqual({
      id: 1, projectId: "p1", topicId: 7, topicLabel: "Transport public", documentId: "doc-1",
      title: "New trolleybus schedule", url: "https://www.chisinau.md/", source: "RTEC", district: "Centru",
      category: "Transport", publishedDate: "2026-09-24", excerpt: "Buses run every 8 minutes.", score: 0.7,
      createdAt: Date.parse("2026-09-26T10:00:00Z"), isRead: false,
    });
    expect(toAlert(alertView({ readAt: "2026-09-26T11:00:00Z" })).isRead).toBe(true);
  });
  it("maps settings with their topics", () => {
    const settings = toAlertSettings(settingsView({
      enabled: true, prompted: true, lastScanAt: "2026-09-26T12:00:00Z",
      topics: [topicView(), topicView({ id: 8, label: "Parks", source: "USER", minScore: 0.8 })],
    }));
    expect(settings).toEqual({
      projectId: "p1", enabled: true, prompted: true, lastScanAt: Date.parse("2026-09-26T12:00:00Z"),
      topics: [
        { id: 7, label: "Transport public", query: "transport public", isAuto: true, minScore: null },
        { id: 8, label: "Parks", query: "transport public", isAuto: false, minScore: 0.8 },
      ],
    });
    expect(toAlertSettings(settingsView()).lastScanAt).toBeNull();
  });
  it("maps unread counts and adjusts them per project", () => {
    const counts = toUnreadAlertCounts({ total: 3, byProject: { p1: 2, p2: 1 } });
    expect(adjustUnread(counts, "p1", -1)).toEqual({ total: 2, byProject: { p1: 1, p2: 1 } });
    expect(adjustUnread(counts, "p2", -5)).toEqual({ total: 2, byProject: { p1: 2 } });
    expect(adjustUnread(counts, "p3", 1)).toEqual({ total: 4, byProject: { p1: 2, p2: 1, p3: 1 } });
  });
});

describe("AlertOptInDialog", () => {
  const setup = (topics: string[]) => {
    const calls = { enabled: 0, declined: 0 };
    render(<AlertOptInDialog projectName="Education" topics={topics}
      onEnable={() => { calls.enabled += 1; }} onDecline={() => { calls.declined += 1; }} />);
    return calls;
  };

  it("lists the extracted topics and turns alerts on", () => {
    const calls = setup(["Școli și grădinițe", "Transport public"]);
    const dialog = screen.getByRole("dialog", { name: en.alerts.optIn.title });
    expect(within(dialog).getByText(en.alerts.optIn.body("Education"))).toBeTruthy();
    expect(within(dialog).getAllByRole("listitem").map(item => item.textContent))
      .toEqual(["Școli și grădinițe", "Transport public"]);
    fireEvent.click(within(dialog).getByRole("button", { name: en.alerts.optIn.enable }));
    expect(calls).toEqual({ enabled: 1, declined: 0 });
  });
  it("shows a generic line without topics, and Not now or Escape declines", () => {
    const calls = setup([]);
    expect(screen.getByText(en.alerts.optIn.noTopics("Education"))).toBeTruthy();
    expect(screen.queryByRole("list")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: en.alerts.optIn.notNow }));
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(calls).toEqual({ enabled: 0, declined: 2 });
  });
});

// Hand-written stand-in for the opt-in endpoints.
class FakeOptInClient implements AlertOptInClient {
  calls: string[] = [];
  // The backend saves the answer, then answers 503 when the Python service is down.
  unavailable = false;
  constructor(public prompted: boolean, public topics: AlertTopicView[] = []) {}
  getAlertSettings = async (projectId: string) => {
    this.calls.push(`get ${projectId}`);
    return settingsView({ projectId, prompted: this.prompted });
  };
  refreshAlertTopics = async (projectId: string) => {
    this.calls.push(`refresh ${projectId}`);
    if (this.unavailable) throw new ApiError("Alerts unavailable", 503);
    return settingsView({ projectId, prompted: this.prompted, topics: this.topics });
  };
  updateAlertSettings = async (projectId: string, enabled: boolean) => {
    this.calls.push(`put ${projectId} ${enabled}`);
    this.prompted = true;
    if (this.unavailable) throw new ApiError("Alerts unavailable", 503);
    return settingsView({ projectId, enabled, prompted: true, topics: this.topics });
  };
}

function OptInHarness({ client, projectId, onEnabled }: { client: AlertOptInClient; projectId: string; onEnabled?: () => void }) {
  const optIn = useAlertOptIn(client, { onEnabled });
  return (
    <>
      {optIn.notice && <p role="status">{en.errors[optIn.notice]}</p>}
      <button type="button" onClick={() => void optIn.consider(projectId)}>reply arrived</button>
      {optIn.offer && (
        <AlertOptInDialog projectName="Education" topics={optIn.offer.topics.map(topic => topic.label)}
          onEnable={optIn.enable} onDecline={optIn.decline} />
      )}
    </>
  );
}

describe("alert opt-in trigger", () => {
  it("refreshes topics, offers alerts once, and saves the answer", async () => {
    const client = new FakeOptInClient(false, [topicView()]);
    let enabled = 0;
    render(<OptInHarness client={client} projectId="p1" onEnabled={() => { enabled += 1; }} />);
    fireEvent.click(screen.getByRole("button", { name: "reply arrived" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Transport public")).toBeTruthy();

    fireEvent.click(within(dialog).getByRole("button", { name: en.alerts.optIn.enable }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(enabled).toBe(1);

    // Later replies in the same project never ask again.
    fireEvent.click(screen.getByRole("button", { name: "reply arrived" }));
    await act(async () => {});
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(client.calls).toEqual(["get p1", "refresh p1", "put p1 true"]);
  });
  it("does not ask when the project was already prompted", async () => {
    const client = new FakeOptInClient(true);
    render(<OptInHarness client={client} projectId="p1" />);
    fireEvent.click(screen.getByRole("button", { name: "reply arrived" }));
    await act(async () => {});
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(client.calls).toEqual(["get p1"]);
  });
  it("asks with the generic line and closes after a saved answer when matching is unavailable", async () => {
    const client = new FakeOptInClient(false);
    client.unavailable = true;
    let enabled = 0;
    render(<OptInHarness client={client} projectId="p1" onEnabled={() => { enabled += 1; }} />);
    fireEvent.click(screen.getByRole("button", { name: "reply arrived" }));
    expect(await screen.findByText(en.alerts.optIn.noTopics("Education"))).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: en.alerts.optIn.enable }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByRole("status").textContent).toBe(en.errors.alertsUnavailable);
    expect(enabled).toBe(0);
    fireEvent.click(screen.getByRole("button", { name: "reply arrived" }));
    await act(async () => {});
    expect(screen.queryByRole("dialog")).toBeNull();
  });
  it("saves Not now as disabled", async () => {
    const client = new FakeOptInClient(false);
    render(<OptInHarness client={client} projectId="p1" />);
    fireEvent.click(screen.getByRole("button", { name: "reply arrived" }));
    fireEvent.click(await screen.findByRole("button", { name: en.alerts.optIn.notNow }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(client.calls.at(-1)).toBe("put p1 false");
  });
});

const projects: ProjectSummary[] = [
  { id: "p1", name: "Transport", updatedAt: 2 },
  { id: "p2", name: "Education", updatedAt: 1 },
];

describe("AlertBell", () => {
  const alerts: Alert[] = [
    toAlert(alertView()),
    toAlert(alertView({ id: 2, projectId: "p2", topicLabel: "Școli", title: "Kindergarten enrolment",
      url: "javascript:alert(1)", readAt: "2026-09-26T11:00:00Z", createdAt: "2026-09-26T09:00:00Z" })),
  ];

  const setup = (overrides: Partial<React.ComponentProps<typeof AlertBell>> = {}) => {
    const calls = { opened: 0, read: [] as number[], allRead: 0, notRelevant: [] as number[], asked: [] as number[] };
    render(<AlertBell alerts={alerts} unreadTotal={1} projects={projects}
      onOpen={() => { calls.opened += 1; }}
      onMarkRead={id => calls.read.push(id)}
      onMarkAllRead={() => { calls.allRead += 1; }}
      onNotRelevant={id => calls.notRelevant.push(id)}
      onAsk={alert => calls.asked.push(alert.id)} {...overrides} />);
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
    expect(calls.asked).toEqual([1]);
    // Asking closes the panel.
    expect(screen.queryByRole("dialog")).toBeNull();
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
    for (const row of this.rows) if (!row.readAt) byProject[row.projectId] = (byProject[row.projectId] ?? 0) + 1;
    return { total: Object.values(byProject).reduce((a, b) => a + b, 0), byProject };
  }
  getAlerts = async () => [...this.rows];
  getAlertUnreadCount = async () => this.counts();
  markAlertRead = async (id: number) => {
    this.calls.push(`read ${id}`);
    const row = this.rows.find(candidate => candidate.id === id)!;
    row.readAt = "2026-09-26T12:00:00Z";
    return row;
  };
  markAllAlertsRead = async (projectId: string | null = null) => {
    this.calls.push(`read-all ${projectId}`);
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
    <AlertBell alerts={alerts.alerts} unreadTotal={alerts.unread.total} projects={projects}
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

// Hand-written stand-in for one project's settings endpoints.
class FakeSettingsClient implements AlertSettingsClient {
  calls: string[] = [];
  unavailable = false;
  nextId = 100;
  scanCreated = [2, 0];
  constructor(public settings: AlertSettingsView) {}
  getAlertSettings = async () => structuredClone(this.settings);
  updateAlertSettings = async (_projectId: string, enabled: boolean) => {
    this.calls.push(`enabled ${enabled}`);
    this.settings = { ...this.settings, enabled, prompted: true };
    if (this.unavailable) throw new ApiError("Alerts unavailable", 503);
    return structuredClone(this.settings);
  };
  createAlertTopic = async (_projectId: string, label: string) => {
    this.calls.push(`add ${label}`);
    const existing = this.settings.topics.find(topic => topic.label.toLowerCase() === label.toLowerCase());
    if (existing) return { ...existing };
    const topic = topicView({ id: this.nextId++, label, query: label, source: "USER" });
    this.settings.topics.push(topic);
    return topic;
  };
  updateAlertTopic = async (_projectId: string, topicId: number, label: string) => {
    this.calls.push(`rename ${topicId} ${label}`);
    const topic = this.settings.topics.find(candidate => candidate.id === topicId)!;
    Object.assign(topic, { label, query: label, source: "USER" });
    return { ...topic };
  };
  deleteAlertTopic = async (_projectId: string, topicId: number) => {
    this.calls.push(`remove ${topicId}`);
    this.settings.topics = this.settings.topics.filter(topic => topic.id !== topicId);
  };
  scanProjectAlerts = async (): Promise<AlertScanView> => {
    this.calls.push("scan");
    if (this.unavailable) throw new ApiError("Alerts unavailable", 503);
    this.settings.lastScanAt = "2026-09-26T12:30:00Z";
    return { created: this.scanCreated.shift() ?? 0, matcher: "lexical" };
  };
}

describe("ProjectAlertsDialog", () => {
  const setup = (unavailable = false) => {
    const client = new FakeSettingsClient(settingsView({ prompted: true, topics: [topicView()] }));
    client.unavailable = unavailable;
    const changes = { count: 0, closed: 0 };
    render(<ProjectAlertsDialog projectId="p1" projectName="Transport" client={client}
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

describe("Sidebar alerts", () => {
  const noop = () => {};
  it("shows a project's unread badge and opens its alert settings", () => {
    const opened: string[] = [];
    render(<Sidebar chats={[]} projects={projects} activeChatId={null} draftProjectId={null} isLoaded
      onNewChat={noop} onSelect={noop} onRename={noop} onDelete={noop} onMoveChat={noop}
      onCreateProject={async () => null} onRenameProject={noop} onDeleteProject={noop} onNewChatInProject={noop}
      unreadAlertsByProject={{ p1: 3 }} onOpenProjectAlerts={project => opened.push(project.id)}
      isOpen onClose={noop} />);
    // The badge doesn't change the row's name; it is announced as its description.
    const row = screen.getByRole("button", { name: "Transport" });
    expect(within(row).getByTestId("project-alert-badge").textContent).toBe("3");
    expect(document.getElementById(row.getAttribute("aria-describedby")!)!.textContent)
      .toBe(en.alerts.projectUnread(3));
    expect(within(screen.getByRole("button", { name: "Education" })).queryByTestId("project-alert-badge")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: en.alerts.settings.open("Education") }));
    expect(opened).toEqual(["p2"]);
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

    await mockClient.markAllAlertsRead(project.id);
    expect((await mockClient.getAlertUnreadCount()).total).toBe(0);
    // Dismissed documents are never alerted again.
    await mockClient.scanProjectAlerts(project.id);
    expect((await mockClient.getAlerts()).map(alert => alert.documentId)).not.toContain(alerts[0].documentId);
  });
});
