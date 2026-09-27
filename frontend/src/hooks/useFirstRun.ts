import { useCallback, useEffect, useState } from "react";

export const HAS_CHATTED_STORAGE_KEY = "smart-city-has-chatted";

function readHasChatted(): boolean {
  try {
    return localStorage.getItem(HAS_CHATTED_STORAGE_KEY) === "1";
  } catch {
    // Storage can be blocked; the server's chat list still tells returning visitors apart.
    return false;
  }
}

function saveHasChatted() {
  try {
    localStorage.setItem(HAS_CHATTED_STORAGE_KEY, "1");
  } catch {
    // Not remembered across visits; an existing chat list still hides the welcome.
  }
}

export type FirstRunState = "welcome" | "returning" | "unknown";

// The welcome banner with sample questions is only for a browser's very first
// chat. `hasChats` is null while the chat list is still loading, so a returning
// visitor never sees the banner flash before their chats arrive.
export function useFirstRun(hasChats: boolean | null) {
  const [hasChatted, setHasChatted] = useState(readHasChatted);

  const markChatted = useCallback(() => {
    saveHasChatted();
    setHasChatted(true);
  }, []);

  // Visitors who chatted before the flag existed, or whose storage was cleared.
  useEffect(() => {
    if (hasChats) markChatted();
  }, [hasChats, markChatted]);

  const state: FirstRunState = hasChatted || hasChats
    ? "returning"
    : hasChats === null ? "unknown" : "welcome";

  return { state, markChatted };
}
