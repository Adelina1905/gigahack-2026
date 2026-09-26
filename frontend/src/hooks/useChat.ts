import { useCallback, useRef, useState } from "react";
import { createChat, createResponse } from "../api/client";
import type { ChatMessage, MessageStatus } from "../types/chat";

const makeId = () => crypto.randomUUID();

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const chatIdRef = useRef<string | null>(null);
  const chatCreationRef = useRef<Promise<string> | null>(null);

  const setStatus = useCallback((id: string, status: MessageStatus) => {
    setMessages((current) =>
      current.map((message) =>
        message.id === id ? { ...message, status } : message,
      ),
    );
  }, []);

  const getOrCreateChatId = useCallback(async () => {
    if (chatIdRef.current) return chatIdRef.current;

    if (!chatCreationRef.current) {
      chatCreationRef.current = createChat().then((chat) => {
        chatIdRef.current = chat.id;
        return chat.id;
      });
    }

    try {
      return await chatCreationRef.current;
    } catch (error) {
      chatCreationRef.current = null;
      throw error;
    }
  }, []);

  const deliver = useCallback(
    async (messageId: string, userInput: string) => {
      setIsTyping(true);

      try {
        const chatId = await getOrCreateChatId();
        const assistantResponse = await createResponse(chatId, userInput);

        setStatus(messageId, "sent");
        setMessages((current) => [
          ...current,
          {
            id: String(assistantResponse.id),
            role: "assistant",
            content: assistantResponse.text,
            createdAt: new Date(assistantResponse.createdAt).getTime(),
            sources: [],
          },
        ]);
      } catch (error) {
        console.error("Failed to send chat message", error);
        setStatus(messageId, "error");
      } finally {
        setIsTyping(false);
      }
    },
    [getOrCreateChatId, setStatus],
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
