import { useCallback, useState } from "react";

const STORAGE_KEY = "smart-city-offer-alerts";

function readPreference(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) !== "off";
  } catch {
    return true;
  }
}

// The per-browser "Offer alerts in conversations" switch, on by default.
// It only hides the question in chats; existing subscriptions keep working.
export function useAlertOfferPreference() {
  const [enabled, setEnabledState] = useState(readPreference);

  const setEnabled = useCallback((next: boolean) => {
    setEnabledState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next ? "on" : "off");
    } catch {
      // Private mode or blocked storage: the choice lasts for this visit only.
    }
  }, []);

  return [enabled, setEnabled] as const;
}
