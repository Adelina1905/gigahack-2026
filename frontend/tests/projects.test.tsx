import React from "react";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render as renderRaw, screen, within } from "@testing-library/react";
import ProjectDialog from "../src/components/ProjectDialog";
import Sidebar from "../src/components/Sidebar";
import { toChatSummary, toProjectSummary } from "../src/api/mappers";
import * as mockClient from "../src/api/mockClient";
import { I18nContext } from "../src/i18n/context";
import { MESSAGES } from "../src/i18n/messages";
import type { ChatView } from "../src/api/types";
import type { ChatSummary, ProjectSummary } from "../src/types/chat";

afterEach(cleanup);
const en = MESSAGES.en;
const render = (ui: React.ReactElement) =>
  renderRaw(<I18nContext.Provider value={{ locale: "en", setLocale: () => {}, t: en }}>{ui}</I18nContext.Provider>);

describe("project mappers", () => {
  const chat: ChatView = { id: "c1", name: "Schools", projectId: "p1",
    createdAt: "2026-09-26T10:00:00Z", updatedAt: "2026-09-26T11:00:00Z" };

  it("keeps the chat's project", () => {
    expect(toChatSummary(chat)).toEqual({ id: "c1", name: "Schools", projectId: "p1",
      updatedAt: Date.parse("2026-09-26T11:00:00Z") });
  });
  it("treats a missing projectId as ungrouped", () => {
    const legacy = { ...chat, projectId: undefined } as unknown as ChatView;
    expect(toChatSummary(legacy).projectId).toBeNull();
  });
  it("maps a project without its embedded chats", () => {
    expect(toProjectSummary({ id: "p1", name: "Education", createdAt: "2026-09-26T10:00:00Z",
      updatedAt: "2026-09-26T12:00:00Z", chats: [chat] }))
      .toEqual({ id: "p1", name: "Education", updatedAt: Date.parse("2026-09-26T12:00:00Z") });
  });
});

describe("ProjectDialog", () => {
  const setup = (initialName?: string) => {
    const calls = { submitted: [] as string[], cancelled: 0 };
    render(<ProjectDialog title="New project" submitLabel="Create" initialName={initialName}
      onSubmit={name => calls.submitted.push(name)} onCancel={() => { calls.cancelled += 1; }} />);
    return calls;
  };
  const input = () => screen.getByRole("textbox", { name: en.projects.name }) as HTMLInputElement;
  const create = () => screen.getByRole("button", { name: "Create" }) as HTMLButtonElement;

  it("is an accessible dialog with the name field focused", () => {
    setup();
    expect(screen.getByRole("dialog", { name: "New project" })).toBeTruthy();
    expect(document.activeElement).toBe(input());
    expect(input().maxLength).toBe(255);
  });
  it("disables Create while the name is blank", () => {
    const calls = setup();
    expect(create().disabled).toBe(true);
    fireEvent.change(input(), { target: { value: "   " } });
    expect(create().disabled).toBe(true);
    fireEvent.submit(input().form!);
    expect(calls.submitted).toEqual([]);
  });
  it("submits the trimmed name on Enter", () => {
    const calls = setup();
    fireEvent.change(input(), { target: { value: "  Education  " } });
    expect(create().disabled).toBe(false);
    // Enter in a text field submits its form.
    fireEvent.submit(input().form!);
    expect(calls.submitted).toEqual(["Education"]);
  });
  it("cancels on Escape, on the backdrop and on Cancel", () => {
    const calls = setup("Old name");
    expect(input().value).toBe("Old name");
    fireEvent.keyDown(input(), { key: "Escape" });
    fireEvent.click(screen.getByTestId("project-dialog-backdrop"));
    fireEvent.click(screen.getByRole("button", { name: en.projects.cancel }));
    expect(calls.cancelled).toBe(3);
    expect(calls.submitted).toEqual([]);
  });
});

describe("Sidebar projects", () => {
  const now = Date.now();
  const projects: ProjectSummary[] = [
    { id: "p1", name: "Education", updatedAt: now },
    { id: "p2", name: "Transport", updatedAt: now - 1 },
  ];
  const chats: ChatSummary[] = [
    { id: "c1", name: "Schools", projectId: "p1", updatedAt: now },
    { id: "c2", name: "Fairs", projectId: null, updatedAt: now },
    { id: "c3", name: "Orphan", projectId: "gone", updatedAt: now },
  ];
  const noop = () => {};

  const renderSidebar = (overrides: Partial<React.ComponentProps<typeof Sidebar>> = {}) => {
    const calls = { moved: [] as Array<[string, string | null]>, created: [] as string[], newChatIn: [] as string[] };
    render(<Sidebar chats={chats} projects={projects} activeChatId="c1" draftProjectId={null} isLoaded
      onNewChat={noop} onSelect={noop} onRename={noop} onDelete={noop}
      onMoveChat={(chatId, projectId) => calls.moved.push([chatId, projectId])}
      onCreateProject={async name => { calls.created.push(name); return null; }}
      onRenameProject={noop} onDeleteProject={noop}
      onNewChatInProject={projectId => calls.newChatIn.push(projectId)}
      isOpen onClose={noop} {...overrides} />);
    return calls;
  };

  it("lists project chats under their project and the rest by date", () => {
    renderSidebar();
    // The project of the open chat is expanded.
    expect(screen.getByRole("button", { name: "Education" }).getAttribute("aria-expanded")).toBe("true");
    const education = screen.getByRole("list", { name: "Education" });
    expect(within(education).getByText("Schools")).toBeTruthy();
    expect(within(education).queryByText("Fairs")).toBeNull();

    const today = screen.getByText(en.sidebar.groups.today).closest("section")!;
    expect(within(today).getByText("Fairs")).toBeTruthy();
    // A chat whose project is unknown stays visible in the date groups.
    expect(within(today).getByText("Orphan")).toBeTruthy();
    expect(within(today).queryByText("Schools")).toBeNull();
  });
  it("toggles a project and shows a hint when it is empty", () => {
    renderSidebar();
    const transport = screen.getByRole("button", { name: "Transport" });
    expect(transport.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(transport);
    expect(transport.getAttribute("aria-expanded")).toBe("true");
    expect(within(screen.getByRole("list", { name: "Transport" })).getByText(en.projects.empty)).toBeTruthy();
    fireEvent.click(transport);
    expect(screen.queryByRole("list", { name: "Transport" })).toBeNull();
  });
  it("starts a chat inside a project", () => {
    const calls = renderSidebar();
    fireEvent.click(screen.getByRole("button", { name: en.projects.newChatIn("Transport") }));
    expect(calls.newChatIn).toEqual(["p2"]);
  });
  it("offers a visible New chat button in an empty project", () => {
    const calls = renderSidebar();
    fireEvent.click(screen.getByRole("button", { name: "Transport" }));
    const transport = screen.getByRole("list", { name: "Transport" });
    fireEvent.click(within(transport).getByRole("button", { name: en.sidebar.newChat }));
    expect(calls.newChatIn).toEqual(["p2"]);
  });
  it("lists the first chat under a new project from the draft until it is saved", () => {
    const props = { chats, projects, isLoaded: true, onNewChat: noop, onSelect: noop, onRename: noop,
      onDelete: noop, onMoveChat: noop, onCreateProject: async () => null, onRenameProject: noop,
      onDeleteProject: noop, onNewChatInProject: noop, isOpen: true, onClose: noop };
    const { rerender } = render(<Sidebar {...props} activeChatId={null} draftProjectId="p2" />);
    // The draft target project opens and shows the chat being written.
    let transport = screen.getByRole("list", { name: "Transport" });
    const draft = within(transport).getByText(en.sidebar.newChat);
    expect(draft.getAttribute("aria-current")).toBe("page");
    expect(within(transport).queryByText(en.projects.empty)).toBeNull();

    // The first message created the chat on the server; it replaces the draft row.
    const saved: ChatSummary = { id: "c4", name: "Bus routes", projectId: "p2", updatedAt: now + 1 };
    rerender(<I18nContext.Provider value={{ locale: "en", setLocale: () => {}, t: en }}>
      <Sidebar {...props} chats={[saved, ...chats]} activeChatId="c4" draftProjectId={null} />
    </I18nContext.Provider>);
    transport = screen.getByRole("list", { name: "Transport" });
    expect(within(transport).getByRole("button", { name: "Bus routes" }).getAttribute("aria-current")).toBe("page");
    expect(within(transport).queryByText(en.sidebar.newChat)).toBeNull();
    expect(screen.getByText(en.sidebar.groups.today).closest("section")!.textContent).not.toContain("Bus routes");
  });
  it("moves a chat into a project or out of it", () => {
    const calls = renderSidebar();
    fireEvent.click(screen.getByRole("button", { name: en.projects.move("Fairs") }));
    fireEvent.click(within(screen.getByRole("menu")).getByRole("menuitemradio", { name: "Transport" }));
    expect(screen.queryByRole("menu")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: en.projects.move("Schools") }));
    const menu = screen.getByRole("menu");
    expect(within(menu).getByRole("menuitemradio", { name: "Education" }).getAttribute("aria-checked")).toBe("true");
    fireEvent.click(within(menu).getByRole("menuitemradio", { name: en.projects.noProject }));
    expect(calls.moved).toEqual([["c2", "p2"], ["c1", null]]);
  });
  it("creates a project from the dialog", async () => {
    const calls = renderSidebar();
    fireEvent.click(screen.getByRole("button", { name: en.projects.newProject }));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByRole("textbox"), { target: { value: "Parks" } });
    fireEvent.click(within(dialog).getByRole("button", { name: en.projects.create }));
    expect(calls.created).toEqual(["Parks"]);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("mock projects API", () => {
  it("keeps a deleted project's chats and ungroups them", async () => {
    localStorage.clear();
    const project = await mockClient.createProject("  Education ");
    expect(project).toMatchObject({ name: "Education", chats: [] });
    const inside = await mockClient.createChat("Schools", undefined, project.id);
    const moved = await mockClient.createChat("Fairs");
    await mockClient.setChatProject(moved.id, project.id);
    expect((await mockClient.getProjects())[0].chats.map(chat => chat.id).sort())
      .toEqual([inside.id, moved.id].sort());

    await mockClient.deleteProject(project.id);
    expect(await mockClient.getProjects()).toEqual([]);
    expect((await mockClient.getChats()).map(chat => chat.projectId)).toEqual([null, null]);
    await expect(mockClient.setChatProject(inside.id, project.id)).rejects.toMatchObject({ status: 404 });
  });
});
