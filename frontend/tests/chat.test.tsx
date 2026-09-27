import React from "react";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render as renderRaw, screen } from "@testing-library/react";
import AssistantMessage from "../src/components/AssistantMessage";
import UserMessage from "../src/components/UserMessage";
import { toMessages } from "../src/api/mappers";
import { hasPendingGeneration, mergeWithServer, restoreCached } from "../src/hooks/chatState";
import { safeHttpUrl } from "../src/components/sources/safeLink";
import { I18nContext } from "../src/i18n/context";
import { MESSAGES } from "../src/i18n/messages";
import type { ResponseView } from "../src/api/types";
import type { ChatMessage } from "../src/types/chat";

afterEach(cleanup);
const en = MESSAGES.en;
const render = (ui: React.ReactElement) =>
  renderRaw(<I18nContext.Provider value={{ locale: "en", setLocale: () => {}, t: en }}>{ui}</I18nContext.Provider>);
const row: ResponseView = { id: 1, chatId: "chat", prompt: "Hello", text: null,
  requestId: "request", generationVersion: 1, generationStatus: "PENDING", createdAt: "2026-09-26T10:00:00Z" };

describe("durable chat rendering", () => {
  it("keeps saved pending prompts distinct from unsent messages", () => {
    const [user, assistant] = toMessages(row);
    expect(user.status).toBe("sent");
    expect(hasPendingGeneration([user, assistant])).toBe(true);
    render(<AssistantMessage message={assistant} />);
    expect(screen.getByRole("status").textContent).toContain("Waiting for response");
  });
  it("shows a retry and preserves an answer after regeneration fails", () => {
    const [, assistant] = toMessages({ ...row, text: "Previous answer", generationStatus: "FAILED" });
    render(<AssistantMessage message={assistant} onRegenerate={() => {}} />);
    expect(screen.getByText("Previous answer")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
    expect(screen.getByText(/Previous answer kept/)).toBeTruthy();
  });
  it("labels unsaved outbox messages", () => {
    render(<UserMessage message={{ id: "draft", role: "user", content: "Offline draft", createdAt: 1, status: "error" }} />);
    expect(screen.getByText(en.message.failed)).toBeTruthy();
  });
  it("retains demo labels and ordered citation quotes from persisted metadata", () => {
    const [, assistant] = toMessages({ ...row, text: "Read [S1].", generationStatus: "COMPLETED", aiReply: {
      mode: "demo", status: "DEMO", answer: "Read [S1].", clarificationChoices: null,
      citations: [{ title: "Second document ID", url: "https://example.com/two", documentId: "2", exactQuote: "Exact second quote" },
        { title: "First document ID", url: "https://example.org/one", documentId: "1", exactQuote: "Exact first quote" }],
    } });
    render(<AssistantMessage message={assistant} onSelectSource={() => {}} />);
    expect(screen.getByText("Demo response")).toBeTruthy();
    // Citation markers remain as accessible inline controls; pills open the same preview.
    expect(screen.getByRole("button", { name: /Source 1 of 2: Second document ID/i })).toBeTruthy();
    expect(screen.getAllByRole("button").some(button => button.textContent?.includes("example.com"))).toBe(true);
    expect(assistant.sources?.map(source => source.documentId)).toEqual(["2", "1"]);
  });
  it("links plain URLs and Markdown without enabling unsafe protocols or raw HTML", () => {
    render(<AssistantMessage message={{ id: "1", role: "assistant", createdAt: 1,
      content: "https://example.com [Website](https://example.org/path) [Unsafe](javascript:alert) <script>bad()</script>",
      sources: [{ title: "Invalid source", link: "javascript:alert(1)", added_date: "" }] }} />);
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(2);
    for (const link of links) { expect(link.getAttribute("target")).toBe("_blank"); expect(link.getAttribute("rel")).toBe("noopener noreferrer"); }
    expect(document.querySelector("script")).toBeNull();
    expect(safeHttpUrl("data:text/html,test")).toBeUndefined();
    expect(safeHttpUrl("file:///secret")).toBeUndefined();
  });
});

describe("request reconciliation", () => {
  it("uses UUIDs instead of matching prompt text", () => {
    const local: ChatMessage[] = [
      { id: "request", requestId: "request", role: "user", content: "Hello", createdAt: 1, status: "error" },
      { id: "other", requestId: "other", role: "user", content: "Hello", createdAt: 1, status: "error" },
    ];
    const merged = mergeWithServer(toMessages(row), local);
    expect(merged.filter(message => message.role === "user")).toHaveLength(2);
    expect(merged.some(message => message.id === "other")).toBe(true);
  });
  it("never replaces a newer generation with a stale poll", () => {
    const current = toMessages({ ...row, generationVersion: 3, text: "New answer", generationStatus: "COMPLETED" });
    expect(mergeWithServer(toMessages(row), current)[1].content).toBe("New answer");
  });
  it("restores outbox entries without changing server pending generations", () => {
    const saved = toMessages(row);
    expect(restoreCached(saved)[1].generationStatus).toBe("PENDING");
  });
});
