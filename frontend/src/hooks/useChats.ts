import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "../api";
import { toChatSummary } from "../api/mappers";
import * as cache from "../db/cache";
import type { ErrorKey } from "../i18n/messages";
import type { ChatSummary } from "../types/chat";

const sortChats = (chats: ChatSummary[]) =>
  [...chats].sort((a, b) => b.updatedAt - a.updatedAt);

// The sidebar's chat list: painted from the cache, then replaced by the
// server's list, which is scoped to this browser's anonymous client cookie.
export function useChats() {
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [isLoaded, setIsLoaded] = useState(false);
  const [error, setError] = useState<ErrorKey | null>(null);
  // Chats created while the initial fetch was in flight must survive it.
  const createdLocallyRef = useRef(new Set<string>());

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      const cached = await cache.loadChats();
      if (!cancelled && cached.length > 0) {
        setChats((current) => (current.length > 0 ? current : cached));
      }

      try {
        const fresh = (await api.getChats()).map(toChatSummary);
        if (cancelled) return;

        const freshIds = new Set(fresh.map((chat) => chat.id));
        setChats((current) =>
          sortChats([
            ...fresh,
            ...current.filter(
              (chat) =>
                !freshIds.has(chat.id) && createdLocallyRef.current.has(chat.id),
            ),
          ]),
        );
      } catch (loadError) {
        console.error("Failed to load chats", loadError);
        if (!cancelled) setError("chatsLoadFailed");
      } finally {
        if (!cancelled) setIsLoaded(true);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  // Mirror to the cache only after the first load, so an empty initial state
  // never wipes the cached list.
  useEffect(() => {
    if (isLoaded) void cache.saveChats(chats);
  }, [chats, isLoaded]);

  const upsert = useCallback((chat: ChatSummary) => {
    createdLocallyRef.current.add(chat.id);
    setChats((current) =>
      sortChats([chat, ...current.filter((candidate) => candidate.id !== chat.id)]),
    );
  }, []);

  // Picks up the server-side title and activity time after a reply.
  const refresh = useCallback(
    async (chatId: string) => {
      try {
        upsert(toChatSummary(await api.getChat(chatId)));
      } catch (refreshError) {
        console.error("Failed to refresh chat", refreshError);
      }
    },
    [upsert],
  );

  const rename = useCallback(
    async (chatId: string, name: string) => {
      const trimmed = name.trim();
      const previous = chats.find((chat) => chat.id === chatId);
      if (!previous || !trimmed || trimmed === previous.name) return;

      setChats((current) =>
        current.map((chat) => (chat.id === chatId ? { ...chat, name: trimmed } : chat)),
      );

      try {
        await api.updateChat(chatId, trimmed);
      } catch (renameError) {
        console.error("Failed to rename chat", renameError);
        setChats((current) =>
          current.map((chat) => (chat.id === chatId ? previous : chat)),
        );
        setError("renameFailed");
      }
    },
    [chats],
  );

  // Drops a chat locally without calling the API (e.g. it's already gone).
  const forget = useCallback((chatId: string) => {
    createdLocallyRef.current.delete(chatId);
    setChats((current) => current.filter((chat) => chat.id !== chatId));
    void cache.removeChat(chatId);
  }, []);

  const remove = useCallback(
    async (chatId: string) => {
      const previous = chats;
      forget(chatId);

      try {
        await api.deleteChat(chatId);
      } catch (deleteError) {
        if (deleteError instanceof ApiError && deleteError.status === 404) return;
        console.error("Failed to delete chat", deleteError);
        setChats(previous);
        setError("deleteFailed");
      }
    },
    [chats, forget],
  );

  const dismissError = useCallback(() => setError(null), []);

  return { chats, isLoaded, error, upsert, refresh, rename, remove, forget, dismissError };
}
