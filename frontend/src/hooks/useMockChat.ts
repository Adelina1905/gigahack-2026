import { useCallback, useState } from "react";
import type { ChatMessage, MessageStatus } from "../types/chat";

const CANNED_REPLIES = [
  "Sure! Here's a quick overview of how that works.",
  "Good question. Let me break it down step by step:\n1. First, upload your file.\n2. Then I'll extract the text.\n3. Finally, you can ask me anything about it.",
  "I'm a mock assistant for now, but the real answer will appear right here.",
];

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
      { id: makeId(), role: "assistant", content: pickReply(), createdAt: Date.now() },
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
      prev.map((m) => (m.id === id ? { ...m, content: pickReply(m.content), createdAt: Date.now() } : m)),
    );
  }, []);

  return { messages, isTyping, send, retry, regenerate };
}
