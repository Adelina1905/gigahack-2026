import { useCallback, useEffect, useState } from "react";

// The open chat lives in the URL (?chat=<uuid>) so a reload, a bookmark or
// the back button all land on the same conversation.

const PARAM = "chat";

const readChatId = () => new URLSearchParams(window.location.search).get(PARAM);

export function useActiveChatId() {
  const [chatId, setChatId] = useState<string | null>(readChatId);

  useEffect(() => {
    const sync = () => setChatId(readChatId());
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);

  const navigate = useCallback(
    (nextChatId: string | null, { replace = false } = {}) => {
      const url = new URL(window.location.href);
      if (nextChatId) url.searchParams.set(PARAM, nextChatId);
      else url.searchParams.delete(PARAM);

      if (url.href !== window.location.href) {
        window.history[replace ? "replaceState" : "pushState"](null, "", url);
      }
      setChatId(nextChatId);
    },
    [],
  );

  return [chatId, navigate] as const;
}
