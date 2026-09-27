import { useEffect } from "react";

export function isDemoNotificationShortcut(event: KeyboardEvent) {
  const target = event.target;
  const isTyping = target instanceof HTMLElement && (
    target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)
  );
  return !isTyping
    && !event.ctrlKey
    && !event.metaKey
    && !event.altKey
    && !event.shiftKey
    && event.key === "9";
}

export function useDemoNotificationShortcut(enabled: boolean, onTrigger: () => void) {
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (!enabled || !isDemoNotificationShortcut(event)) return;
      event.preventDefault();
      onTrigger();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [enabled, onTrigger]);
}
