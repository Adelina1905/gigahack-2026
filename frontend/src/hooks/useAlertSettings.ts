import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, api, type Api } from "../api";
import { toAlertSettings, toAlertTopic } from "../api/mappers";
import type { ErrorKey } from "../i18n/messages";
import { parseScopeKey, scopeKey, type AlertScope, type AlertSettings, type AlertTopic } from "../types/alerts";
import {
  createScopeTopic,
  deleteScopeTopic,
  getScopeSettings,
  scanScope,
  updateScopeSettings,
  updateScopeTopic,
} from "./alertScope";

export type AlertSettingsClient = Pick<
  Api,
  | "getAlertSettings"
  | "updateAlertSettings"
  | "createAlertTopic"
  | "updateAlertTopic"
  | "deleteAlertTopic"
  | "scanProjectAlerts"
  | "getChatAlertSettings"
  | "updateChatAlertSettings"
  | "createChatAlertTopic"
  | "updateChatAlertTopic"
  | "deleteChatAlertTopic"
  | "scanChatAlerts"
>;

// The backend saves the change first and answers 503 when the matching
// service is down, so the saved state has to be read back.
export const isAlertsUnavailable = (error: unknown) => error instanceof ApiError && error.status === 503;

interface UseAlertSettingsOptions {
  // Called after anything that can create alerts (turning on, Check now).
  onAlertsChanged?: () => void;
}

// One project's or chat's alert switch, followed topics and manual scan.
export function useAlertSettings(
  target: AlertScope,
  client: AlertSettingsClient = api,
  { onAlertsChanged }: UseAlertSettingsOptions = {},
) {
  // Callers usually pass a fresh object each render; only a new scope reloads.
  const key = scopeKey(target);
  const scope = useMemo(() => parseScopeKey(key), [key]);
  const [settings, setSettings] = useState<AlertSettings | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isScanning, setIsScanning] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  // Alerts created by the last "Check now"; null until one finishes.
  const [lastScanCreated, setLastScanCreated] = useState<number | null>(null);
  const [error, setError] = useState<ErrorKey | null>(null);
  const clientRef = useRef(client);
  const changedRef = useRef(onAlertsChanged);
  const settingsRef = useRef(settings);
  useEffect(() => {
    clientRef.current = client;
    changedRef.current = onAlertsChanged;
    settingsRef.current = settings;
  });

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const loaded = toAlertSettings(await getScopeSettings(clientRef.current, scope));
        if (!cancelled) setSettings(loaded);
      } catch (loadError) {
        console.error("Failed to load alert settings", loadError);
        if (!cancelled) setError("alertSettingsLoadFailed");
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [scope]);

  const setTopics = (update: (topics: AlertTopic[]) => AlertTopic[]) =>
    setSettings((current) => (current ? { ...current, topics: update(current.topics) } : current));

  // Reads back what the server saved; keeps the fallback if that fails too.
  const reload = useCallback(
    async (fallback: AlertSettings | null) => {
      try {
        setSettings(toAlertSettings(await getScopeSettings(clientRef.current, scope)));
      } catch (loadError) {
        console.error("Failed to reload alert settings", loadError);
        setSettings(fallback);
      }
    },
    [scope],
  );

  const setEnabled = useCallback(
    async (enabled: boolean) => {
      // The rendered settings, not settingsRef: the ref is only synced after
      // render, so a click right after the first load could see null.
      const previous = settings;
      if (!previous || previous.enabled === enabled) return;
      setSettings({ ...previous, enabled });
      setIsSaving(true);
      setError(null);
      try {
        setSettings(toAlertSettings(await updateScopeSettings(clientRef.current, scope, enabled)));
        if (enabled) changedRef.current?.();
      } catch (saveError) {
        console.error("Failed to update alert settings", saveError);
        if (isAlertsUnavailable(saveError)) {
          setError("alertsUnavailable");
          await reload(previous);
        } else {
          setSettings(previous);
          setError("alertSettingsSaveFailed");
        }
      } finally {
        setIsSaving(false);
      }
    },
    [scope, reload, settings],
  );

  const addTopic = useCallback(
    async (label: string): Promise<boolean> => {
      const trimmed = label.trim();
      if (!trimmed) return false;
      setError(null);
      try {
        const topic = toAlertTopic(await createScopeTopic(clientRef.current, scope, trimmed));
        // An existing label comes back as the existing topic.
        setTopics((topics) => [...topics.filter((candidate) => candidate.id !== topic.id), topic]);
        return true;
      } catch (addError) {
        console.error("Failed to add alert topic", addError);
        setError("alertSettingsSaveFailed");
        return false;
      }
    },
    [scope],
  );

  const renameTopic = useCallback(
    async (topicId: number, label: string) => {
      const trimmed = label.trim();
      const previous = settings?.topics.find((topic) => topic.id === topicId);
      if (!previous || !trimmed || trimmed === previous.label) return;
      setTopics((topics) => topics.map((topic) => (topic.id === topicId ? { ...topic, label: trimmed } : topic)));
      setError(null);
      try {
        const saved = toAlertTopic(await updateScopeTopic(clientRef.current, scope, topicId, trimmed));
        setTopics((topics) => topics.map((topic) => (topic.id === topicId ? saved : topic)));
      } catch (renameError) {
        console.error("Failed to rename alert topic", renameError);
        setTopics((topics) => topics.map((topic) => (topic.id === topicId ? previous : topic)));
        setError("alertSettingsSaveFailed");
      }
    },
    [scope, settings],
  );

  const removeTopic = useCallback(
    async (topicId: number) => {
      const previous = settings?.topics;
      if (!previous?.some((topic) => topic.id === topicId)) return;
      setTopics((topics) => topics.filter((topic) => topic.id !== topicId));
      setError(null);
      try {
        await deleteScopeTopic(clientRef.current, scope, topicId);
      } catch (removeError) {
        console.error("Failed to remove alert topic", removeError);
        setTopics(() => previous);
        setError("alertSettingsSaveFailed");
      }
    },
    [scope, settings],
  );

  const checkNow = useCallback(async () => {
    setIsScanning(true);
    setLastScanCreated(null);
    setError(null);
    try {
      const result = await scanScope(clientRef.current, scope);
      setLastScanCreated(result.created);
      // Picks up the new last-scan time.
      setSettings(toAlertSettings(await getScopeSettings(clientRef.current, scope)));
      if (result.created > 0) changedRef.current?.();
    } catch (scanError) {
      console.error("Failed to scan for alerts", scanError);
      setError(isAlertsUnavailable(scanError) ? "alertsUnavailable" : "alertScanFailed");
      await reload(settingsRef.current);
    } finally {
      setIsScanning(false);
    }
  }, [scope, reload]);

  const dismissError = useCallback(() => setError(null), []);

  return {
    settings, isLoading, isSaving, isScanning, lastScanCreated, error,
    setEnabled, addTopic, renameTopic, removeTopic, checkNow, dismissError,
  };
}
