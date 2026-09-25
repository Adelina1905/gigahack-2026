import { useCallback, useState } from "react";
import type { ChatMessage, MessageStatus, SourceDocument } from "../types/chat";

const CANNED_REPLIES = [
  "Sure! Here's a quick overview of how that works.",
  "Good question. Let me break it down step by step:\n1. First, upload your file.\n2. Then I'll extract the text.\n3. Finally, you can ask me anything about it.",
  "I'm a mock assistant for now, but the real answer will appear right here.",
];

const MOCK_SOURCES: SourceDocument[] = [
  {
    title: "Urban Mobility Plan 2030 — Public Transport Strategy",
    link: "https://en.wikipedia.org/wiki/Public_transport",
    added_date: "2026-08-14T09:30:00Z",
  },
  {
    title: "Smart City Open Data Portal: Air Quality Measurements",
    link: "https://www.who.int/health-topics/air-pollution",
    added_date: "2026-09-02T14:10:00Z",
  },
  {
    title: "Municipal Waste Management Annual Report",
    link: "https://www.eea.europa.eu/en/topics/in-depth/waste-and-recycling",
    added_date: "2026-07-21T08:00:00Z",
  },
  {
    title: "Guidelines for Citizen Service Requests",
    link: "https://developer.mozilla.org/en-US/docs/Web/HTTP",
    added_date: "2026-09-20T17:45:00Z",
  },
];

// Picks 0–4 random sources so both the empty and populated states show up.
const pickSources = () =>
  [...MOCK_SOURCES].sort(() => Math.random() - 0.5).slice(0, Math.floor(Math.random() * 5));

const makeId = () => crypto.randomUUID();
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
const pickReply = (exclude?: string) => {
  const pool = CANNED_REPLIES.filter((r) => r !== exclude);
  return pool[Math.floor(Math.random() * pool.length)];
};

export function useMockChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isTyping, setIsTyping] = useState(false);

  const setStatus = (id: string, status: MessageStatus) =>
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, status } : m)));

  // Simulates the network round-trip for an existing user message.
  const deliver = useCallback(async (id: string, text: string) => {
    await wait(300);
    // Type a message containing "fail" to preview the error state.
    if (text.toLowerCase().includes("fail")) {
      setStatus(id, "error");
      return;
    }
    setStatus(id, "sent");
    setIsTyping(true);
    await wait(800 + Math.random() * 700);
    setMessages((prev) => [
      ...prev,
      { id: makeId(), role: "assistant", content: pickReply(), createdAt: Date.now(), sources: pickSources() },
    ]);
    setIsTyping(false);
  }, []);

  const send = useCallback(
    (text: string) => {
      const id = makeId();
      setMessages((prev) => [
        ...prev,
        { id, role: "user", content: text, createdAt: Date.now(), status: "sending" },
      ]);
      void deliver(id, text);
    },
    [deliver],
  );

  const retry = useCallback(
    (id: string) => {
      const msg = messages.find((m) => m.id === id);
      if (!msg) return;
      setStatus(id, "sending");
      // Strip the trigger word so the retry succeeds in the mock.
      void deliver(id, msg.content.replace(/fail/gi, ""));
    },
    [messages, deliver],
  );

  const regenerate = useCallback((id: string) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, content: pickReply(m.content), createdAt: Date.now(), sources: pickSources() } : m)),
    );
  }, []);

  return { messages, isTyping, send, retry, regenerate };
}
