import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "../api";
import { toAssistantMessage, toChatSummary, toMessages } from "../api/mappers";
import * as cache from "../db/cache";
import type { ErrorKey } from "../i18n/messages";
import type { ChatMessage, ChatSummary } from "../types/chat";

// Messages typed before the backend chat exists live under this key.
const DRAFT = "draft";
const EMPTY: ChatMessage[] = [];
// A cached unsent message is considered delivered if the server holds the
// same prompt stored no earlier than this before the message was sent.
const DELIVERY_MATCH_WINDOW_MS = 60_000;

const makeId = () => crypto.randomUUID();

const isMissingChat = (error: unknown) =>
  error instanceof ApiError && (error.status === 404 || error.status === 400);

const describeError = (error: unknown): ErrorKey => {
  if (error instanceof ApiError && error.status === 0) return "offline";
  if (isMissingChat(error)) return "chatMissing";
  return "generic";
};

const isUnsent = (message: ChatMessage) =>
  message.role === "user" &&
  (message.status === "sending" || message.status === "error");

// After a reload nothing is in flight anymore, so pending sends become retryable.
const restoreCached = (messages: ChatMessage[]) =>
  messages.map((message) =>
    message.status === "sending" ? { ...message, status: "error" as const } : message,
  );

// The server's history wins; local messages it doesn't know about yet
// (in flight or failed) are kept at the end.
function mergeWithServer(server: ChatMessage[], local: ChatMessage[]) {
  const delivered = server.filter((message) => message.role === "user");
  const unsent = local.filter(
    (message) =>
      isUnsent(message) &&
      !delivered.some(
        (prompt) =>
          prompt.content === message.content &&
          prompt.createdAt >= message.createdAt - DELIVERY_MATCH_WINDOW_MS,
      ),
  );
  return [...server, ...unsent];
}

// Swaps the optimistic user message for the stored turn. If a server refetch
// already brought the turn in, leave the thread as it is.
function settleTurn(thread: ChatMessage[], messageId: string, turn: ChatMessage[]) {
  const index = thread.findIndex((message) => message.id === messageId);

  // A response without a stored prompt (older backend) only carries the
  // answer; keep the user's own message instead of dropping it.
  if (index !== -1 && !turn.some((message) => message.role === "user")) {
    turn = [{ ...thread[index], status: "sent" }, ...turn];
  }

  const turnIds = new Set(turn.map((message) => message.id));
  const others = thread.filter(
    (message) => message.id !== messageId && !turnIds.has(message.id),
  );

  if (index === -1) {
    return thread.some((message) => turnIds.has(message.id))
      ? thread
      : [...thread, ...turn];
  }
  return [...others.slice(0, index), ...turn, ...others.slice(index)];
}

interface UseChatOptions {
  // A first message created the backend chat; isActive is false if the user
  // navigated elsewhere while it was being created.
  onChatCreated?: (chat: ChatSummary, isActive: boolean) => void;
  // A reply was stored, so the chat's title or activity time may have changed.
  onReply?: (chatId: string) => void;
  // The chat in the URL doesn't exist for this browser (deleted, or the
  // client cookie was cleared).
  onChatMissing?: (chatId: string) => void;
}

// Messages for every opened chat, keyed by chat id, so a reply that arrives
// after switching chats lands in the right one.
export function useChat(chatId: string | null, options: UseChatOptions = {}) {
  const key = chatId ?? DRAFT;

  const [threads, setThreads] = useState<Record<string, ChatMessage[]>>({});
  const [typing, setTyping] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<ErrorKey | null>(null);

  const keyRef = useRef(key);
  const threadsRef = useRef(threads);
  const optionsRef = useRef(options);
  const savedRef = useRef<Record<string, ChatMessage[]>>({});

  useEffect(() => {
    keyRef.current = key;
    threadsRef.current = threads;
    optionsRef.current = options;
  });

  const updateThread = useCallback(
    (threadKey: string, update: (thread: ChatMessage[]) => ChatMessage[]) =>
      setThreads((current) => ({
        ...current,
        [threadKey]: update(current[threadKey] ?? EMPTY),
      })),
    [],
  );

  const setFlag = (
    setter: typeof setTyping,
    threadKey: string,
    value: boolean,
  ) => setter((current) => ({ ...current, [threadKey]: value }));

  // Write every changed thread through to the cache.
  useEffect(() => {
    for (const [threadKey, thread] of Object.entries(threads)) {
      if (threadKey === DRAFT || savedRef.current[threadKey] === thread) continue;
      savedRef.current[threadKey] = thread;
      void cache.saveMessages(threadKey, thread);
    }
  }, [threads]);

  // Opening a chat: paint from memory or cache, then revalidate from the server.
  useEffect(() => {
    setError(null);
    if (!chatId) return;

    void (async () => {
      if (!threadsRef.current[chatId]) {
        setFlag(setLoading, chatId, true);
        const cached = await cache.loadMessages(chatId);
        if (cached) {
          updateThread(chatId, (current) =>
            current.length > 0 ? current : restoreCached(cached),
          );
        }
      }

      try {
        const responses = await api.getResponses(chatId);
        updateThread(chatId, (current) =>
          mergeWithServer(responses.flatMap(toMessages), current),
        );
      } catch (loadError) {
        if (isMissingChat(loadError)) {
          optionsRef.current.onChatMissing?.(chatId);
        } else if (keyRef.current === chatId) {
          console.error("Failed to load chat history", loadError);
          setError(describeError(loadError));
        }
      } finally {
        setFlag(setLoading, chatId, false);
      }
    })();
  }, [chatId, updateThread]);

  const moveDraft = useCallback((targetChatId: string) => {
    setThreads(({ [DRAFT]: draft = EMPTY, ...rest }) => ({
      ...rest,
      [targetChatId]: [...(rest[targetChatId] ?? EMPTY), ...draft],
    }));
    setTyping(({ [DRAFT]: _draft, ...rest }) => ({ ...rest, [targetChatId]: true }));
  }, []);

  const deliver = useCallback(
    async (threadKey: string, messageId: string, userInput: string) => {
      let target = threadKey;
      setFlag(setTyping, threadKey, true);
      setError(null);

      try {
        if (target === DRAFT) {
          const chat = await api.createChat();
          target = chat.id;
          moveDraft(chat.id);
          optionsRef.current.onChatCreated?.(
            toChatSummary(chat),
            keyRef.current === DRAFT,
          );
        }

        const response = await api.createResponse(target, userInput);
        updateThread(target, (thread) =>
          settleTurn(thread, messageId, toMessages(response)),
        );
        optionsRef.current.onReply?.(target);
      } catch (sendError) {
        console.error("Failed to send chat message", sendError);
        updateThread(target, (thread) =>
          thread.map((message) =>
            message.id === messageId ? { ...message, status: "error" } : message,
          ),
        );
        if (keyRef.current === target || keyRef.current === threadKey) {
          setError(describeError(sendError));
        }
      } finally {
        setFlag(setTyping, target, false);
        if (target !== threadKey) setFlag(setTyping, threadKey, false);
      }
    },
    [moveDraft, updateThread],
  );

  const send = useCallback(
    (userInput: string) => {
      const messageId = makeId();

      updateThread(key, (thread) => [
        ...thread,
        {
          id: messageId,
          role: "user",
          content: userInput,
          createdAt: Date.now(),
          status: "sending",
        },
      ]);

      void deliver(key, messageId, userInput);
    },
    [deliver, key, updateThread],
  );

  const retry = useCallback(
    (messageId: string) => {
      const message = threads[key]?.find(
        (candidate) => candidate.id === messageId && candidate.role === "user",
      );
      if (!message || typing[key]) return;

      updateThread(key, (thread) =>
        thread.map((candidate) =>
          candidate.id === messageId ? { ...candidate, status: "sending" } : candidate,
        ),
      );
      void deliver(key, messageId, message.content);
    },
    [deliver, key, threads, typing, updateThread],
  );

  // Asks the backend to answer the same prompt again; it replaces the stored
  // reply, so the history keeps one answer per question.
  const regenerate = useCallback(
    async (assistantId: string) => {
      const responseId = Number(assistantId);
      if (!chatId || typing[chatId] || !Number.isInteger(responseId)) return;

      setFlag(setTyping, chatId, true);
      setError(null);

      try {
        const reply = toAssistantMessage(
          await api.regenerateResponse(chatId, responseId),
        );
        updateThread(chatId, (thread) =>
          thread.map((message) => (message.id === assistantId ? reply : message)),
        );
        optionsRef.current.onReply?.(chatId);
      } catch (regenerateError) {
        console.error("Failed to regenerate chat message", regenerateError);
        if (keyRef.current === chatId) setError(describeError(regenerateError));
      } finally {
        setFlag(setTyping, chatId, false);
      }
    },
    [chatId, typing, updateThread],
  );

  // Clears an unsent draft when starting a new chat.
  const resetDraft = useCallback(() => {
    if (typing[DRAFT]) return;
    setThreads(({ [DRAFT]: _draft, ...rest }) => rest);
    setError(null);
  }, [typing]);

  // Drops a deleted chat from memory.
  const discard = useCallback((targetChatId: string) => {
    delete savedRef.current[targetChatId];
    setThreads(({ [targetChatId]: _thread, ...rest }) => rest);
  }, []);

  const dismissError = useCallback(() => setError(null), []);

  const messages = threads[key] ?? EMPTY;

  return {
    messages,
    isTyping: Boolean(typing[key]),
    isLoading: Boolean(loading[key]) && messages.length === 0,
    error,
    send,
    retry,
    regenerate: (assistantId: string) => void regenerate(assistantId),
    resetDraft,
    discard,
    dismissError,
  };
}
