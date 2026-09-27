import React from "react";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render as renderRaw, screen } from "@testing-library/react";
import ConfirmDialog from "../src/components/ConfirmDialog";
import ChatItem from "../src/components/sidebar/ChatItem";
import ProjectItem from "../src/components/sidebar/ProjectItem";
import { I18nContext } from "../src/i18n/context";
import { MESSAGES } from "../src/i18n/messages";
import type { ChatSummary, ProjectSummary } from "../src/types/chat";

afterEach(cleanup);
const en = MESSAGES.en;
const render = (ui: React.ReactElement) =>
  renderRaw(<I18nContext.Provider value={{ locale: "en", setLocale: () => {}, t: en }}>{ui}</I18nContext.Provider>);

describe("ConfirmDialog", () => {
  const setup = () => {
    const calls = { confirmed: 0, cancelled: 0 };
    render(<ConfirmDialog title="Delete chat?" message="Schools will be deleted."
      onConfirm={() => { calls.confirmed += 1; }} onCancel={() => { calls.cancelled += 1; }} />);
    return calls;
  };

  it("is an accessible alert dialog with Cancel focused", () => {
    setup();
    const dialog = screen.getByRole("alertdialog", { name: "Delete chat?" });
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    const description = document.getElementById(dialog.getAttribute("aria-describedby")!);
    expect(description?.textContent).toBe("Schools will be deleted.");
    expect(document.activeElement).toBe(screen.getByRole("button", { name: en.confirm.cancel }));
  });
  it("cancels on Escape, on the backdrop and on Cancel", () => {
    const calls = setup();
    fireEvent.keyDown(document.activeElement!, { key: "Escape" });
    fireEvent.click(screen.getByTestId("confirm-dialog-backdrop"));
    fireEvent.click(screen.getByRole("button", { name: en.confirm.cancel }));
    expect(calls).toEqual({ confirmed: 0, cancelled: 3 });
  });
  it("confirms on Delete", () => {
    const calls = setup();
    fireEvent.click(screen.getByRole("button", { name: en.confirm.delete }));
    expect(calls).toEqual({ confirmed: 1, cancelled: 0 });
  });
});

describe("sidebar delete confirmation", () => {
  const noop = () => {};
  const chat: ChatSummary = { id: "c1", name: "Schools", projectId: null, updatedAt: Date.now() };
  const project: ProjectSummary = { id: "p1", name: "Education", updatedAt: Date.now() };

  it("deletes a chat only after it is confirmed, and returns focus when cancelled", () => {
    const deleted: string[] = [];
    render(<ul><ChatItem chat={chat} isActive projects={[]} onSelect={noop}
      onDelete={id => deleted.push(id)} onMove={noop} /></ul>);
    const trigger = screen.getByRole("button", { name: en.sidebar.remove("Schools") });

    trigger.focus();
    fireEvent.click(trigger);
    screen.getByRole("alertdialog", { name: en.sidebar.confirmRemoveTitle });
    fireEvent.click(screen.getByRole("button", { name: en.confirm.cancel }));
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
    expect(deleted).toEqual([]);

    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("button", { name: en.confirm.delete }));
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(deleted).toEqual(["c1"]);
  });
  it("deletes a project only after it is confirmed", () => {
    const deleted: string[] = [];
    render(<ul><ProjectItem project={project} chats={[]} projects={[project]} activeChatId={null}
      isDraftTarget={false} isExpanded={false} onToggle={noop} onNewChat={noop} onRename={noop}
      onDelete={id => deleted.push(id)} onSelectChat={noop} onDeleteChat={noop}
      onMoveChat={noop} /></ul>);

    fireEvent.click(screen.getByRole("button", { name: en.projects.remove("Education") }));
    expect(screen.getByRole("alertdialog", { name: en.projects.confirmRemoveTitle })).toBeTruthy();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(deleted).toEqual([]);

    fireEvent.click(screen.getByRole("button", { name: en.projects.remove("Education") }));
    fireEvent.click(screen.getByRole("button", { name: en.confirm.delete }));
    expect(deleted).toEqual(["p1"]);
  });
});
