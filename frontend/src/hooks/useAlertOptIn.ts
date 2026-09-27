import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Api } from "../api";
import { toAlertSettings } from "../api/mappers";
import { isAlertsUnavailable } from "./useAlertSettings";
import { getScopeSettings, refreshScopeTopics, updateScopeSettings } from "./alertScope";
import type { ErrorKey } from "../i18n/messages";
import { scopeKey, type AlertScope, type AlertTopic } from "../types/alerts";

export type AlertOptInClient = Pick<
  Api,
  | "getAlertSettings"
  | "refreshAlertTopics"
  | "updateAlertSettings"
  | "getChatAlertSettings"
  | "refreshChatAlertTopics"
  | "updateChatAlertSettings"
>;

export interface AlertOptInOffer {
  scope: AlertScope;
  // The conversation the question is shown in.
  chatId: string;
  topics: AlertTopic[];
}

// A short line shown where the question was, after it is answered.
export interface AlertOptInNotice {
  kind: "enabled" | "unavailable";
  chatId: string;
}

interface UseAlertOptInOptions {
  // The per-browser "Offer alerts in conversations" switch; off never asks.
  enabled?: boolean;
  // Turning alerts on backfills a few alerts right away.
  onEnabled?: () => void;
  noticeMs?: number;
}

const NOTICE_MS = 6000;

// A chat in a project offers the project's alerts; any other chat its own.
export const alertScopeForChat = (chat: { id: string; projectId: string | null }): AlertScope =>
  chat.projectId ? { kind: "project", id: chat.projectId } : { kind: "chat", id: chat.id };

// The one-time "get notified about these topics?" question shown in a chat.
// The scope's prompted flag on the server decides whether it is asked; a scope
// is also checked at most once per session, so polling replies never re-ask.
export function useAlertOptIn(
  client: AlertOptInClient = api,
  { enabled = true, onEnabled, noticeMs = NOTICE_MS }: UseAlertOptInOptions = {},
) {
  const [offer, setOffer] = useState<AlertOptInOffer | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<ErrorKey | null>(null);
  const [notice, setNotice] = useState<AlertOptInNotice | null>(null);
  const handled = useRef(new Set<string>());
  const offerRef = useRef(offer);
  const savingRef = useRef(false);
  const enabledRef = useRef(enabled);
  const clientRef = useRef(client);
  const onEnabledRef = useRef(onEnabled);
  const noticeTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => {
    offerRef.current = offer;
    enabledRef.current = enabled;
    clientRef.current = client;
    onEnabledRef.current = onEnabled;
  });
  useEffect(() => () => clearTimeout(noticeTimer.current), []);

  const showOffer = useCallback((next: AlertOptInOffer | null) => {
    offerRef.current = next;
    setOffer(next);
  }, []);

  const showNotice = useCallback((next: AlertOptInNotice) => {
    clearTimeout(noticeTimer.current);
    setNotice(next);
    noticeTimer.current = setTimeout(() => setNotice(null), noticeMs);
  }, [noticeMs]);

  // Called once the open chat has an answer; scope is its project's or its own.
  const consider = useCallback(async (scope: AlertScope, chatId: string) => {
    if (!enabledRef.current || savingRef.current) return;
    const key = scopeKey(scope);
    const current = offerRef.current;
    if (current && scopeKey(current.scope) === key) {
      // Another chat of the same project: the question follows the user there.
      if (current.chatId !== chatId) showOffer({ ...current, chatId });
      return;
    }
    if (handled.current.has(key)) return;
    handled.current.add(key);
    if (current) {
      // The unanswered question of a chat left behind is asked there again later.
      handled.current.delete(scopeKey(current.scope));
      showOffer(null);
    }
    try {
      const settings = await getScopeSettings(clientRef.current, scope);
      if (settings.prompted) return;
      // Without the topic service the question is still asked, with the generic line.
      const refreshed = toAlertSettings(
        await refreshScopeTopics(clientRef.current, scope).catch((refreshError: unknown) => {
          if (isAlertsUnavailable(refreshError)) return settings;
          throw refreshError;
        }),
      );
      if (refreshed.prompted) return;
      if (offerRef.current || !enabledRef.current) {
        handled.current.delete(key);
        return;
      }
      setError(null);
      showOffer({ scope, chatId, topics: refreshed.topics });
    } catch (checkError) {
      console.error("Failed to check alert opt-in", checkError);
      // Try again after the next reply.
      handled.current.delete(key);
    }
  }, [showOffer]);

  const answer = useCallback(async (turnOn: boolean) => {
    const current = offerRef.current;
    if (!current || savingRef.current) return;
    savingRef.current = true;
    setIsSaving(true);
    setError(null);
    try {
      await updateScopeSettings(clientRef.current, current.scope, turnOn);
      showOffer(null);
      if (turnOn) {
        showNotice({ kind: "enabled", chatId: current.chatId });
        onEnabledRef.current?.();
      }
    } catch (saveError) {
      console.error("Failed to save alert opt-in", saveError);
      if (isAlertsUnavailable(saveError)) {
        // The answer was saved; only the first check for updates failed.
        showOffer(null);
        if (turnOn) showNotice({ kind: "unavailable", chatId: current.chatId });
      } else if (turnOn) {
        setError("alertSettingsSaveFailed");
      } else {
        // "Not now" still closes; this session won't ask again.
        showOffer(null);
      }
    } finally {
      savingRef.current = false;
      setIsSaving(false);
    }
  }, [showNotice, showOffer]);

  return {
    // Hidden while the switch is off; it shows again if it is turned back on.
    offer: enabled ? offer : null,
    isSaving,
    error,
    notice,
    consider,
    dismissNotice: useCallback(() => setNotice(null), []),
    enable: useCallback(() => void answer(true), [answer]),
    decline: useCallback(() => void answer(false), [answer]),
  };
}
