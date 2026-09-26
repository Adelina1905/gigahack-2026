import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "../api";
import { toChatSummary, toMessages } from "../api/mappers";
import * as cache from "../db/cache";
import type { ErrorKey } from "../i18n/messages";
import { DEFAULT_CHAT_NAME, type ChatMessage, type ChatSummary } from "../types/chat";
import { DRAFT, hasPendingGeneration, mergeWithServer, restoreCached, settleTurn } from "./chatState";

const EMPTY: ChatMessage[] = [];
const makeId = () => crypto.randomUUID();
// A malformed chat id in the URL is rejected with 400, so it counts as missing too.
const isMissingChat = (error: unknown) =>
  error instanceof ApiError && (error.status === 404 || error.status === 400);
const describeError = (error: unknown): ErrorKey => {
  if (error instanceof ApiError && error.status === 0) return "offline";
  if (error instanceof ApiError && error.status === 404) return "chatMissing";
  return "generic";
};

interface UseChatOptions {
  onChatCreated?: (chat: ChatSummary, isActive: boolean) => void;
  onReply?: (chatId: string) => void;
  onChatMissing?: (chatId: string) => void;
}

export function useChat(chatId: string | null, options: UseChatOptions = {}) {
  const key = chatId ?? DRAFT;
  const [threads, setThreads] = useState<Record<string, ChatMessage[]>>({});
  const [inFlight, setInFlight] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<ErrorKey | null>(null);
  const threadsRef = useRef(threads);
  const activeRef = useRef(key);
  const optionsRef = useRef(options);
  const busy = useRef(new Set<string>());
  const discarded = useRef(new Set<string>());
  useEffect(() => { activeRef.current = key; optionsRef.current = options; });

  const updateThread = useCallback((target: string, update: (current: ChatMessage[]) => ChatMessage[]) => {
    if (discarded.current.has(target)) return;
    const next = update(threadsRef.current[target] ?? EMPTY);
    threadsRef.current = { ...threadsRef.current, [target]: next };
    setThreads(threadsRef.current);
    void cache.saveMessages(target, next);
  }, []);

  const setBusy = useCallback((target: string, value: boolean) => {
    if (value) busy.current.add(target); else busy.current.delete(target);
    setInFlight(current => ({ ...current, [target]: value }));
  }, []);

  const refresh = useCallback(async (target: string) => {
    const rows = await api.getResponses(target);
    updateThread(target, current => mergeWithServer(rows.flatMap(toMessages), current));
    optionsRef.current.onReply?.(target);
    return rows;
  }, [updateThread]);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    setLoading(current => ({ ...current, [key]: true }));
    void (async () => {
      if (!threadsRef.current[key]) {
        const saved = await cache.loadMessages(key);
        if (saved && !cancelled && !threadsRef.current[key]) updateThread(key, () => restoreCached(saved));
      }
      if (cancelled) return;
      try { if (chatId) await refresh(chatId); }
      catch (failure) {
        if (isMissingChat(failure) && chatId) optionsRef.current.onChatMissing?.(chatId);
        else if (!cancelled) setError(describeError(failure));
      } finally { if (!cancelled) setLoading(current => ({ ...current, [key]: false })); }
    })();
    return () => { cancelled = true; };
  }, [chatId, key, refresh, updateThread]);

  const messages = threads[key] ?? EMPTY;
  const pending = hasPendingGeneration(messages);
  useEffect(() => {
    if (!chatId || (!pending && !inFlight[key])) return;
    let stopped = false;
    let running = false;
    const interval = setInterval(() => {
      if (running || stopped) return;
      running = true;
      void refresh(chatId).catch(failure => {
        if (!stopped) setError(describeError(failure));
      }).finally(() => { running = false; });
    }, 2000);
    return () => { stopped = true; clearInterval(interval); };
  }, [chatId, key, pending, inFlight, refresh]);

  const deliver = useCallback(async (initialTarget: string, message: ChatMessage) => {
    let target = initialTarget;
    setBusy(target, true);
    setError(null);
    try {
      // The durable outbox is written before either chat creation or submission.
      await cache.saveMessages(target, threadsRef.current[target] ?? [message]);
      if (target === DRAFT) {
        const chat = await api.createChat(DEFAULT_CHAT_NAME, message.chatRequestId);
        target = chat.id;
        const draft = threadsRef.current[DRAFT] ?? [message];
        const next = { ...threadsRef.current, [target]: draft };
        delete next[DRAFT];
        threadsRef.current = next;
        setThreads(next);
        setBusy(target, true);
        await cache.moveDraft(target, draft);
        optionsRef.current.onChatCreated?.(toChatSummary(chat), activeRef.current === DRAFT);
      }
      const response = await api.createResponse(target, message.content, message.requestId);
      updateThread(target, thread => settleTurn(thread, message.requestId!, toMessages(response)));
      optionsRef.current.onReply?.(target);
    } catch (failure) {
      updateThread(target, thread => thread.map(item => item.id === message.id ? { ...item, status: "error" } : item));
      // The request may have committed even when its HTTP response was lost.
      const recovered = target !== DRAFT ? await refresh(target).catch(() => []) : [];
      if (!recovered.some(row => row.requestId === message.requestId) &&
          (activeRef.current === target || activeRef.current === initialTarget)) setError(describeError(failure));
    } finally {
      setBusy(target, false);
      if (target !== initialTarget) setBusy(initialTarget, false);
    }
  }, [refresh, setBusy, updateThread]);

  const send = useCallback((input: string) => {
    const text = input.trim();
    if (!text || busy.current.has(key) || hasPendingGeneration(threadsRef.current[key] ?? EMPTY)) return null;
    if (text.length > 8000) { setError("tooLong"); return null; }
    const requestId = makeId();
    const message: ChatMessage = {
      id: requestId, requestId, chatRequestId: key === DRAFT ? makeId() : undefined,
      role: "user", content: text, createdAt: Date.now(), status: "sending",
    };
    updateThread(key, thread => [...thread, message]);
    void deliver(key, message);
    return requestId;
  }, [deliver, key, updateThread]);

  const regenerate = useCallback(async (assistantId: string) => {
    if (!chatId || busy.current.has(chatId) || hasPendingGeneration(threadsRef.current[chatId] ?? EMPTY)) return;
    const message = threadsRef.current[chatId]?.find(item => item.id === assistantId && item.role === "assistant");
    if (!message || !Number.isInteger(Number(assistantId))) return;
    const operation = message.retryOperation ?? { requestId: makeId(), expectedGenerationVersion: message.generationVersion ?? 0 };
    setBusy(chatId, true);
    setError(null);
    updateThread(chatId, thread => thread.map(item => item.id === assistantId ? { ...item, retryOperation: operation } : item));
    await cache.saveMessages(chatId, threadsRef.current[chatId]);
    try {
      const response = await api.regenerateResponse(chatId, Number(assistantId), operation);
      updateThread(chatId, thread => settleTurn(thread, response.requestId ?? message.requestId!, toMessages(response)));
      optionsRef.current.onReply?.(chatId);
    } catch (failure) {
      const recovered = await refresh(chatId).catch(() => []);
      if (!recovered.some(row => String(row.id) === assistantId && (row.generationVersion ?? 0) > operation.expectedGenerationVersion)
          && activeRef.current === chatId) setError(describeError(failure));
    } finally { setBusy(chatId, false); }
  }, [chatId, refresh, setBusy, updateThread]);

  const retry = useCallback((messageId: string) => {
    const message = threadsRef.current[key]?.find(item => item.id === messageId && item.role === "user");
    if (!message || busy.current.has(key) || hasPendingGeneration(threadsRef.current[key] ?? EMPTY)) return;
    // Older cached drafts are upgraded with stable identities before their first retry.
    const upgraded = { ...message, requestId: message.requestId ?? makeId(),
      chatRequestId: message.chatRequestId ?? (key === DRAFT ? makeId() : undefined), status: "sending" as const };
    updateThread(key, thread => thread.map(item => item.id === messageId ? upgraded : item));
    void deliver(key, upgraded);
  }, [deliver, key, updateThread]);

  const resetDraft = useCallback(() => {
    if (!busy.current.has(DRAFT)) { updateThread(DRAFT, () => []); setError(null); }
  }, [updateThread]);
  const discard = useCallback((target: string) => {
    discarded.current.add(target);
    const next = { ...threadsRef.current }; delete next[target];
    threadsRef.current = next; setThreads(next);
    void cache.removeChat(target);
  }, []);

  return { messages, isTyping: Boolean(inFlight[key]) || pending,
    isLoading: Boolean(loading[key]) && messages.length === 0,
    error, send, retry, regenerate: (id: string) => void regenerate(id), resetDraft, discard,
    dismissError: () => setError(null) };
}
