import React from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render as renderRaw, screen, within } from "@testing-library/react";
import * as mockClient from "../src/api/mockClient";
import AssistantMessage from "../src/components/AssistantMessage";
import ChatWindow from "../src/components/ChatWindow";
import SourceList from "../src/components/sources/SourceList";
import { toAssistantMessage, toMessages } from "../src/api/mappers";
import { I18nContext } from "../src/i18n/context";
import { MESSAGES } from "../src/i18n/messages";
import type { ResponseView } from "../src/api/types";
import { NOT_FOUND_REASONS, type ChatMessage } from "../src/types/chat";

const en = MESSAGES.en;
const render = (ui: React.ReactElement) =>
  renderRaw(<I18nContext.Provider value={{ locale: "en", setLocale: () => {}, t: en }}>{ui}</I18nContext.Provider>);

type AiReply = NonNullable<ResponseView["aiReply"]>;
const citation = (overrides: Partial<AiReply["citations"][number]> = {}): AiReply["citations"][number] => ({
  id: "S1", title: "Council decision", url: "https://example.com/decision", exactQuote: "Exact wording.",
  documentId: "decision-1", ...overrides,
});
const row = (aiReply: ResponseView["aiReply"], text = aiReply?.answer ?? ""): ResponseView => ({
  id: 7, chatId: "chat", prompt: "Question?", text, createdAt: "2026-09-26T10:00:00Z",
  requestId: "request", generationStatus: "COMPLETED", generationVersion: 0, aiReply,
});
const reply = (overrides: Partial<AiReply>): AiReply => ({
  mode: "rag", status: "SUPPORTED", answer: "Answer [S1].", citations: [citation()], clarificationChoices: null,
  ...overrides,
});

beforeEach(() => {
  Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: () => {} });
});
afterEach(cleanup);

describe("strict reply mapping", () => {
  it("keeps rows stored before the strict contract unchanged", () => {
    const legacy = toAssistantMessage(row({ mode: "llm", status: "LLM", answer: "Plain answer", citations: [],
      clarificationChoices: null }));
    expect(legacy.replyStatus).toBe("LLM");
    expect(legacy.reason).toBeUndefined();
    expect(legacy.flags).toBeUndefined();
    expect(legacy.clarificationChoices).toEqual([]);

    const oldRag = toAssistantMessage(row(reply({})));
    expect(oldRag.sources?.[0]).toMatchObject({ title: "Council decision", publisher: null, publishedDate: null, outdated: false });

    const noReply = toAssistantMessage({ ...row(null, "Stored text"),
      documents: [{ id: 1, title: "Doc", documentLink: "https://example.com", addedAt: "2026-01-01T00:00:00Z" }] });
    expect(noReply.content).toBe("Stored text");
    expect(noReply.replyStatus).toBeUndefined();
    expect(noReply.sources).toEqual([{ title: "Doc", link: "https://example.com", added_date: "2026-01-01T00:00:00Z" }]);
  });

  it("maps status, reason, flags, choices and citation dates", () => {
    const message = toAssistantMessage(row(reply({
      status: "CONTRADICTION", reason: "CONFLICTING_DOCUMENTS", flags: ["OUTDATED_SOURCES", "DUPLICATES_MERGED:2"],
      citations: [citation({ publisher: "City Hall", publishedDate: "2021-03-04", outdated: true }),
        citation({ id: "S2", documentId: "decision-2", publishedDate: "2025-01-01", outdated: false })],
    })));
    expect(message).toMatchObject({ replyStatus: "CONTRADICTION", reason: "CONFLICTING_DOCUMENTS",
      flags: ["OUTDATED_SOURCES", "DUPLICATES_MERGED:2"] });
    expect(message.sources?.map(source => [source.publisher ?? null, source.publishedDate, source.outdated]))
      .toEqual([["City Hall", "2021-03-04", true], [null, "2025-01-01", false]]);

    const clarification = toAssistantMessage(row(reply({ status: "NEEDS_CLARIFICATION", answer: "Which one?",
      clarificationChoices: [{ documentId: "a", label: "First plan" }] }), "Which one?\n- First plan"));
    expect(clarification.clarificationChoices).toEqual(["First plan"]);
  });

  it("ignores unknown reasons and marks every source when only the flag is present", () => {
    const message = toAssistantMessage(row(reply({ reason: "SOMETHING_NEW", flags: ["OUTDATED_SOURCES"],
      citations: [citation(), citation({ id: "S2" })] })));
    expect(message.reason).toBeUndefined();
    expect(message.sources?.every(source => source.outdated)).toBe(true);
  });
});

describe("strict reply rendering", () => {
  it.each(NOT_FOUND_REASONS)("shows a distinct notice without citations for %s", reason => {
    const [, message] = toMessages(row(reply({ status: "NOT_FOUND", reason, answer: "Nothing in the corpus [S1]." })));
    render(<AssistantMessage message={message} onSelectSource={() => {}} />);
    const notice = screen.getByRole("note");
    expect(within(notice).getByText(en.message.notFound[reason])).toBeTruthy();
    expect(within(notice).getByText("Nothing in the corpus.")).toBeTruthy();
    expect(within(notice).getByText(reason === "OUT_OF_SCOPE" ? en.message.outOfScopeHint : en.message.notFoundHint)).toBeTruthy();
    expect(screen.queryByRole("list", { name: en.message.citedIn })).toBeNull();
    expect(screen.queryByRole("button", { name: /Source 1/ })).toBeNull();
  });

  it("treats a NOT_FOUND status without a reason as nothing relevant found", () => {
    const message = toAssistantMessage(row(reply({ status: "NOT_FOUND", citations: [], answer: "No data." })));
    render(<AssistantMessage message={message} />);
    expect(screen.getByText(en.message.notFound.NO_RELEVANT_EVIDENCE)).toBeTruthy();
  });

  it("warns about contradicting documents and keeps their citations", () => {
    const message = toAssistantMessage(row(reply({ status: "CONTRADICTION", reason: "CONFLICTING_DOCUMENTS",
      answer: "One says 6 [S1]. Another says 8 [S2].",
      citations: [citation(), citation({ id: "S2", documentId: "decision-2", url: "https://example.org/other" })] })));
    render(<AssistantMessage message={message} onSelectSource={() => {}} />);
    expect(screen.getByRole("note").textContent).toBe(en.message.contradiction);
    expect(within(screen.getByRole("list", { name: en.message.citedIn })).getAllByRole("button")).toHaveLength(2);
  });

  it("labels older sources with their year in the pills and the source list", () => {
    const message = toAssistantMessage(row(reply({ flags: ["OUTDATED_SOURCES"], citations: [
      citation({ publishedDate: "2019-05-01", outdated: true }),
      citation({ id: "S2", documentId: "decision-2", publishedDate: "2025-05-01", outdated: false }),
    ] })));
    render(<AssistantMessage message={message} onSelectSource={() => {}} />);
    expect(screen.getAllByText("Older document · 2019")).toHaveLength(1);
    cleanup();
    render(<SourceList sources={message.sources!} />);
    expect(screen.getAllByText("Older document · 2019")).toHaveLength(1);
    expect(screen.queryByText(/2025/)).toBeNull();
  });

  it("renders legacy replies without notices or choice buttons", () => {
    const message = toAssistantMessage(row({ mode: "llm", status: "LLM", answer: "Answer\n- a point", citations: [],
      clarificationChoices: [{ documentId: "a", label: "a point" }] }));
    render(<AssistantMessage message={message} onChoose={() => {}} />);
    expect(screen.queryByRole("note")).toBeNull();
    expect(screen.queryByRole("group")).toBeNull();
    expect(screen.getByText("a point")).toBeTruthy();
  });
});

describe("clarification choices", () => {
  const clarification = (id: number) => toMessages({
    ...row(reply({ status: "NEEDS_CLARIFICATION", answer: "Which plan do you mean?", citations: [],
      clarificationChoices: [{ documentId: "a", label: "Botanica roads" }, { documentId: "b", label: "Ciocana parks" }] }),
    "Which plan do you mean?\n- Botanica roads\n- Ciocana parks"), id,
  });
  const chat = (messages: ChatMessage[], sent: string[], isTyping = false) => (
    <ChatWindow chatId="chat" messages={messages} isTyping={isTyping}
      onSend={text => { sent.push(text); return "request"; }} />
  );

  it("shows the choices as buttons and sends the chosen label", () => {
    const sent: string[] = [];
    render(chat(clarification(1), sent));
    expect(screen.getByText("Which plan do you mean?")).toBeTruthy();
    expect(screen.queryByText(/- Botanica roads/)).toBeNull();
    const group = screen.getByRole("group", { name: en.message.clarificationChoices });
    fireEvent.click(within(group).getByRole("button", { name: "Ciocana parks" }));
    expect(sent).toEqual(["Ciocana parks"]);
  });

  it("disables choices while a turn is pending and on older turns", () => {
    const sent: string[] = [];
    const { unmount } = render(chat(clarification(1), sent, true));
    expect(within(screen.getByRole("group")).getAllByRole("button").every(button => (button as HTMLButtonElement).disabled)).toBe(true);
    unmount();

    const later = toMessages(row(reply({}), "Later answer"));
    render(chat([...clarification(1), ...later.map(item => ({ ...item, id: `${item.id}-later` }))], sent));
    const button = within(screen.getByRole("group")).getByRole("button", { name: "Botanica roads" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    fireEvent.click(button);
    expect(sent).toEqual([]);
  });
});

describe("mock replies", () => {
  beforeEach(() => localStorage.clear());

  // Each mock reply waits up to 1.5 s, like a real generation.
  it("offers an example of each strict state", async () => {
    const chatView = await mockClient.createChat("States");
    const ask = async (prompt: string) => (await mockClient.createResponse(chatView.id, prompt)).aiReply;

    expect(await ask("Care este tariful la troleibuz?")).toMatchObject({ status: "CONTRADICTION", reason: "CONFLICTING_DOCUMENTS" });
    expect(await ask("Unde găsesc parcare?")).toMatchObject({ status: "NOT_FOUND", reason: "EVIDENCE_LACKS_VALUE" });
    expect(await ask("Care e bugetul?")).toMatchObject({ status: "NOT_FOUND", reason: "CLAIMS_UNVERIFIED" });
    expect(await ask("Cum e vremea?")).toMatchObject({ status: "NOT_FOUND", reason: "OUT_OF_SCOPE" });
    expect(await ask("Program cimitir")).toMatchObject({ status: "NOT_FOUND", reason: "NO_RELEVANT_EVIDENCE" });
    const clarification = await mockClient.createResponse(chatView.id, "Ce document?");
    expect(clarification.aiReply?.status).toBe("NEEDS_CLARIFICATION");
    expect(toAssistantMessage(clarification).clarificationChoices).toHaveLength(2);
    const schools = await ask("Cum au fost evaluate instituțiile de educație?");
    expect(schools?.flags).toContain("OUTDATED_SOURCES");
    expect(schools?.citations.some(item => item.outdated)).toBe(true);
  }, 20000);
});
