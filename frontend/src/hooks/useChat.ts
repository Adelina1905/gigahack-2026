import { useCallback, useRef, useState } from "react";
import { ApiError, createChat, createResponse } from "../api/client";
import { toAssistantMessage } from "../api/mappers";
import type { ChatMessage, MessageStatus } from "../types/chat";

const makeId = () => crypto.randomUUID();

const describeError = (error: unknown) => {
  if (error instanceof ApiError && error.status === 0) {
    return "Can't reach the server. Check your connection and try again.";
  }
  return "Something went wrong. Please try again.";
};

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const [error, setError] = useState<string | null>(null);
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

  // Posts the user's text and returns the assistant reply. If the chat no
  // longer exists server-side (deleted, or the client cookie changed), start
  // a fresh chat once and resend.
  const requestReply = useCallback(
    async (userInput: string) => {
      const chatId = await getOrCreateChatId();

      try {
        return toAssistantMessage(await createResponse(chatId, userInput));
      } catch (error) {
        if (!(error instanceof ApiError) || error.status !== 404) throw error;

        chatIdRef.current = null;
        chatCreationRef.current = null;
        const freshChatId = await getOrCreateChatId();
        return toAssistantMessage(await createResponse(freshChatId, userInput));
      }
    },
    [getOrCreateChatId],
  );

  const deliver = useCallback(
    async (messageId: string, userInput: string) => {
      setIsTyping(true);
      setError(null);

      try {
        const reply = await requestReply(userInput);

        setStatus(messageId, "sent");
        setMessages((current) => [...current, reply]);
      } catch (error) {
        console.error("Failed to send chat message", error);
        setStatus(messageId, "error");
        setError(describeError(error));
      } finally {
        setIsTyping(false);
      }
    },
    [requestReply, setStatus],
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

  const replaceReply = useCallback(
    async (assistantId: string, userInput: string) => {
      setIsTyping(true);
      setError(null);

      try {
        const reply = await requestReply(userInput);

        setMessages((current) =>
          current.map((message) =>
            message.id === assistantId ? reply : message,
          ),
        );
      } catch (error) {
        console.error("Failed to regenerate chat message", error);
        setError(describeError(error));
      } finally {
        setIsTyping(false);
      }
    },
    [requestReply],
  );

  // Re-asks the user message that preceded this assistant reply and swaps the
  // reply in place. The backend has no regenerate endpoint, so this stores an
  // extra response row for the chat.
  const regenerate = useCallback(
    (assistantId: string) => {
      if (isTyping) return;

      const index = messages.findIndex(
        (candidate) =>
          candidate.id === assistantId && candidate.role === "assistant",
      );
      const prompt = messages
        .slice(0, index)
        .reverse()
        .find((candidate) => candidate.role === "user");

      if (index === -1 || !prompt) return;

      void replaceReply(assistantId, prompt.content);
    },
    [isTyping, messages, replaceReply],
  );

  const dismissError = useCallback(() => setError(null), []);

  return { messages, isTyping, error, send, retry, regenerate, dismissError };
}
