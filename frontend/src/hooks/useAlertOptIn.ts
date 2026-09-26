import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Api } from "../api";
import { toAlertSettings } from "../api/mappers";
import { isAlertsUnavailable } from "./useAlertSettings";
import type { ErrorKey } from "../i18n/messages";
import type { AlertTopic } from "../types/alerts";

export type AlertOptInClient = Pick<Api, "getAlertSettings" | "refreshAlertTopics" | "updateAlertSettings">;

export interface AlertOptInOffer {
  projectId: string;
  topics: AlertTopic[];
}

interface UseAlertOptInOptions {
  // Turning alerts on backfills a few alerts right away.
  onEnabled?: () => void;
}

// The one-time "get alerts for this project?" question. The server's prompted
// flag decides whether it is asked; a project is also checked at most once per
// session, so polling replies never re-open it.
export function useAlertOptIn(client: AlertOptInClient = api, { onEnabled }: UseAlertOptInOptions = {}) {
  const [offer, setOffer] = useState<AlertOptInOffer | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<ErrorKey | null>(null);
  // Shown outside the dialog once it has closed (alerts on, but no first check).
  const [notice, setNotice] = useState<ErrorKey | null>(null);
  const handled = useRef(new Set<string>());
  const offerRef = useRef(offer);
  const clientRef = useRef(client);
  const enabledRef = useRef(onEnabled);
  useEffect(() => {
    offerRef.current = offer;
    clientRef.current = client;
    enabledRef.current = onEnabled;
  });

  const consider = useCallback(async (projectId: string) => {
    // One question at a time; another project is asked on a later reply.
    if (handled.current.has(projectId) || offerRef.current) return;
    handled.current.add(projectId);
    try {
      const settings = await clientRef.current.getAlertSettings(projectId);
      if (settings.prompted) return;
      // Without the topic service the question is still asked, with the generic line.
      const refreshed = toAlertSettings(
        await clientRef.current.refreshAlertTopics(projectId).catch((refreshError: unknown) => {
          if (isAlertsUnavailable(refreshError)) return settings;
          throw refreshError;
        }),
      );
      if (refreshed.prompted || offerRef.current) return;
      const next = { projectId, topics: refreshed.topics };
      offerRef.current = next;
      setError(null);
      setOffer(next);
    } catch (checkError) {
      console.error("Failed to check alert opt-in", checkError);
      // Try again after the next reply.
      handled.current.delete(projectId);
    }
  }, []);

  const answer = useCallback(async (enabled: boolean) => {
    const current = offerRef.current;
    if (!current) return;
    setIsSaving(true);
    setError(null);
    try {
      await clientRef.current.updateAlertSettings(current.projectId, enabled);
      setOffer(null);
      if (enabled) enabledRef.current?.();
    } catch (saveError) {
      console.error("Failed to save alert opt-in", saveError);
      if (isAlertsUnavailable(saveError)) {
        // The answer was saved; only the first check for updates failed.
        setOffer(null);
        if (enabled) setNotice("alertsUnavailable");
      } else if (enabled) {
        setError("alertSettingsSaveFailed");
      } else {
        // "Not now" still closes; this session won't ask again.
        setOffer(null);
      }
    } finally {
      setIsSaving(false);
    }
  }, []);

  return {
    offer, isSaving, error, notice, consider,
    dismissNotice: () => setNotice(null),
    enable: () => void answer(true),
    decline: () => void answer(false),
  };
}
