import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import ChatWindow from "../src/components/ChatWindow";
import { HAS_CHATTED_STORAGE_KEY } from "../src/hooks/useFirstRun";
import { I18nContext } from "../src/i18n/context";
import { MESSAGES } from "../src/i18n/messages";

const en = MESSAGES.en;
const firstSuggestion = en.welcome.suggestions[0].question;

const app = (hasChats: boolean | null, onSend: (text: string) => string | null = () => "request-1") => (
  <I18nContext.Provider value={{ locale: "en", setLocale: () => {}, t: en }}>
    <ChatWindow chatId={null} messages={[]} isTyping={false} onSend={onSend} hasChats={hasChats} />
  </I18nContext.Provider>
);

beforeEach(() => {
  localStorage.clear();
  Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: () => {} });
});

afterEach(() => {
  cleanup();
  localStorage.clear();
});

describe("first-run welcome", () => {
  it("shows the sample questions to a browser with no chats yet", () => {
    render(app(false));
    expect(screen.getByText(firstSuggestion)).toBeTruthy();
    expect(screen.getByText(en.welcome.body)).toBeTruthy();
  });

  it("stays blank while the chat list is loading instead of flashing the welcome", () => {
    render(app(null));
    expect(screen.queryByText(firstSuggestion)).toBeNull();
    expect(screen.queryByRole("heading", { name: en.welcome.title })).toBeNull();
  });

  it("shows only a compact greeting once the browser has chats", () => {
    render(app(true));
    expect(screen.queryByText(firstSuggestion)).toBeNull();
    expect(screen.getByRole("heading", { name: en.welcome.title })).toBeTruthy();
    expect(localStorage.getItem(HAS_CHATTED_STORAGE_KEY)).toBe("1");
  });

  it("remembers the first message so later empty chats skip the welcome", () => {
    const view = render(app(false));
    fireEvent.click(screen.getByText(firstSuggestion));
    expect(localStorage.getItem(HAS_CHATTED_STORAGE_KEY)).toBe("1");
    expect(screen.queryByText(firstSuggestion)).toBeNull();

    view.unmount();
    // Even before the chat list loads, the flag alone rules out the welcome.
    render(app(null));
    expect(screen.queryByText(firstSuggestion)).toBeNull();
    expect(screen.getByRole("heading", { name: en.welcome.title })).toBeTruthy();
  });

  it("keeps the welcome when a send is rejected", () => {
    render(app(false, () => null));
    fireEvent.click(screen.getByText(firstSuggestion));
    expect(localStorage.getItem(HAS_CHATTED_STORAGE_KEY)).toBeNull();
    expect(screen.getByText(firstSuggestion)).toBeTruthy();
  });
});
