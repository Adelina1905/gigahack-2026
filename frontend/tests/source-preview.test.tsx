import React from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import ChatWindow from "../src/components/ChatWindow";
import { I18nContext } from "../src/i18n/context";
import { MESSAGES } from "../src/i18n/messages";
import type { ChatMessage } from "../src/types/chat";

const en = MESSAGES.en;
const message: ChatMessage = {
  id: "answer-1",
  role: "assistant",
  content: "The supported answer [S1] [S2].",
  createdAt: 1,
  sources: [
    {
      title: "A very detailed municipal PDF",
      link: "https://example.com/report.pdf?download=1#page=4",
      added_date: "not-a-date",
      exactQuote: "The exact supporting sentence from the first document.",
      documentId: "document-1",
    },
    {
      title: "Unavailable municipal notice",
      link: "javascript:alert(1)",
      added_date: "2026-09-27T00:00:00Z",
      exactQuote: null,
      documentId: null,
    },
  ],
};

const app = (chatId = "chat-1", messages = [message]) => (
  <I18nContext.Provider value={{ locale: "en", setLocale: () => {}, t: en }}>
    <ChatWindow chatId={chatId} messages={messages} isTyping={false} onSend={() => null} />
  </I18nContext.Provider>
);

beforeEach(() => {
  Object.defineProperty(window, "innerWidth", { configurable: true, writable: true, value: 1024 });
  Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
    configurable: true,
    value: () => {},
  });
});

afterEach(() => {
  cleanup();
  document.body.style.overflow = "";
});

describe("source preview", () => {
  it("opens from a citation pill with safe metadata and external-link attributes", () => {
    render(app());
    const trigger = screen.getByRole("button", { name: /1\s*example\.com/i });
    fireEvent.click(trigger);

    const panel = screen.getByRole("dialog", { name: "A very detailed municipal PDF" });
    expect(panel.getAttribute("aria-modal")).toBeNull();
    expect(screen.getByText("Source 1 of 2")).toBeTruthy();
    expect(screen.getByText("The exact supporting sentence from the first document.")).toBeTruthy();
    expect(screen.getByText("document-1")).toBeTruthy();
    expect(screen.queryByText("Invalid Date")).toBeNull();

    const link = screen.getByRole("link", { name: en.message.openSource });
    expect(link.getAttribute("href")).toBe("https://example.com/report.pdf?download=1#page=4");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    expect(document.querySelector("iframe")).toBeNull();
  });

  it("navigates in order and never links an unsafe or unavailable URL", () => {
    render(app());
    fireEvent.click(screen.getByRole("button", { name: /1\s*example\.com/i }));
    fireEvent.click(screen.getByRole("button", { name: /Next source/i }));

    expect(screen.getByRole("dialog", { name: "Unavailable municipal notice" })).toBeTruthy();
    expect(screen.getByText("Source 2 of 2")).toBeTruthy();
    expect(screen.getByText(en.message.noLink)).toBeTruthy();
    expect(screen.queryByRole("link", { name: en.message.openSource })).toBeNull();
    expect(screen.getByRole("button", { name: /Next source/i }).hasAttribute("disabled")).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: /Previous source/i }));
    expect(screen.getByText("Source 1 of 2")).toBeTruthy();
  });

  it("closes with Escape, restores trigger focus, and closes when chats change", () => {
    const view = render(app());
    const trigger = screen.getByRole("button", { name: /1\s*example\.com/i });
    fireEvent.click(trigger);
    expect(document.activeElement?.getAttribute("aria-label")).toBe(en.message.closeSources);

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);

    fireEvent.click(trigger);
    view.rerender(app("chat-2", []));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("uses a modal 75%-height bottom sheet with focus containment and scroll locking on mobile", () => {
    window.innerWidth = 500;
    render(app());
    fireEvent.click(screen.getByRole("button", { name: /1\s*example\.com/i }));

    const panel = screen.getByRole("dialog");
    expect(panel.getAttribute("aria-modal")).toBe("true");
    expect(panel.className).toContain("max-h-[75dvh]");
    expect(document.body.style.overflow).toBe("hidden");

    const close = screen.getAllByRole("button", { name: en.message.closeSources })
      .find(button => button.getAttribute("data-testid") !== "source-preview-backdrop");
    expect(document.activeElement).toBe(close);
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(screen.getByRole("button", { name: /Next source/i }));

    fireEvent.click(screen.getByTestId("source-preview-backdrop"));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.body.style.overflow).toBe("");
  });
});
