import { useCallback, useEffect, useRef, useState } from "react";
import { clearLlmChat, sendLlmMessage } from "../api/client";
import type { ChatMessage, MessageStatus } from "../types/chat";

const makeId = () => crypto.randomUUID();

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  // Chats are ephemeral: the id lives only as long as this hook instance and
  // the backend keeps the history in memory under it.
  const chatIdRef = useRef(crypto.randomUUID());

  useEffect(() => {
    const chatId = chatIdRef.current;
    const clear = () => {
      clearLlmChat(chatId, { keepalive: true }).catch(() => {});
    };

    window.addEventListener("pagehide", clear);
    return () => {
      window.removeEventListener("pagehide", clear);
      clear();
    };
  }, []);

  const setStatus = useCallback((id: string, status: MessageStatus) => {
    setMessages((current) =>
      current.map((message) =>
        message.id === id ? { ...message, status } : message,
      ),
    );
  }, []);

  const deliver = useCallback(
    async (messageId: string, userInput: string) => {
      setIsTyping(true);

      try {
        const assistantResponse = await sendLlmMessage(
          chatIdRef.current,
          userInput,
        );

        setStatus(messageId, "sent");
        setMessages((current) => [
          ...current,
          {
            id: makeId(),
            role: "assistant",
            content: assistantResponse.text,
            createdAt: new Date(assistantResponse.createdAt).getTime(),
            sources: assistantResponse.sources.map((source) => ({
              title: source.title,
              link: source.link ?? "",
              added_date: "",
            })),
          },
        ]);
      } catch (error) {
        console.error("Failed to send chat message", error);
        setStatus(messageId, "error");
      } finally {
        setIsTyping(false);
      }
    },
    [setStatus],
  );

  const send = useCallback(
    (userInput: string) => {
      const messageId = makeId();

      setMessages((current) => [
        ...current,
        {
          id: messageId,
          role: "user",
          content: userInput,
          createdAt: Date.now(),
          status: "sending",
        },
      ]);

      void deliver(messageId, userInput);
    },
    [deliver],
  );

  const retry = useCallback(
    (messageId: string) => {
      const message = messages.find(
        (candidate) =>
          candidate.id === messageId && candidate.role === "user",
      );

      if (!message) return;

      setStatus(messageId, "sending");
      void deliver(messageId, message.content);
    },
    [deliver, messages, setStatus],
  );

  return { messages, isTyping, send, retry };
}
