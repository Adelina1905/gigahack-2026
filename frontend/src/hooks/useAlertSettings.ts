import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api, type Api } from "../api";
import { toAlertSettings, toAlertTopic } from "../api/mappers";
import type { ErrorKey } from "../i18n/messages";
import type { AlertSettings, AlertTopic } from "../types/alerts";

export type AlertSettingsClient = Pick<
  Api,
  | "getAlertSettings"
  | "updateAlertSettings"
  | "createAlertTopic"
  | "updateAlertTopic"
  | "deleteAlertTopic"
  | "scanProjectAlerts"
>;

// The backend saves the change first and answers 503 when the matching
// service is down, so the saved state has to be read back.
export const isAlertsUnavailable = (error: unknown) => error instanceof ApiError && error.status === 503;

interface UseAlertSettingsOptions {
  // Called after anything that can create alerts (turning on, Check now).
  onAlertsChanged?: () => void;
}

// One project's alert switch, followed topics and manual scan.
export function useAlertSettings(
  projectId: string,
  client: AlertSettingsClient = api,
  { onAlertsChanged }: UseAlertSettingsOptions = {},
) {
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
        const loaded = toAlertSettings(await clientRef.current.getAlertSettings(projectId));
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
  }, [projectId]);

  const setTopics = (update: (topics: AlertTopic[]) => AlertTopic[]) =>
    setSettings((current) => (current ? { ...current, topics: update(current.topics) } : current));

  // Reads back what the server saved; keeps the fallback if that fails too.
  const reload = useCallback(
    async (fallback: AlertSettings | null) => {
      try {
        setSettings(toAlertSettings(await clientRef.current.getAlertSettings(projectId)));
      } catch (loadError) {
        console.error("Failed to reload alert settings", loadError);
        setSettings(fallback);
      }
    },
    [projectId],
  );

  const setEnabled = useCallback(
    async (enabled: boolean) => {
      const previous = settingsRef.current;
      if (!previous || previous.enabled === enabled) return;
      setSettings({ ...previous, enabled });
      setIsSaving(true);
      setError(null);
      try {
        setSettings(toAlertSettings(await clientRef.current.updateAlertSettings(projectId, enabled)));
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
    [projectId, reload],
  );

  const addTopic = useCallback(
    async (label: string): Promise<boolean> => {
      const trimmed = label.trim();
      if (!trimmed) return false;
      setError(null);
      try {
        const topic = toAlertTopic(await clientRef.current.createAlertTopic(projectId, trimmed));
        // An existing label comes back as the existing topic.
        setTopics((topics) => [...topics.filter((candidate) => candidate.id !== topic.id), topic]);
        return true;
      } catch (addError) {
        console.error("Failed to add alert topic", addError);
        setError("alertSettingsSaveFailed");
        return false;
      }
    },
    [projectId],
  );

  const renameTopic = useCallback(
    async (topicId: number, label: string) => {
      const trimmed = label.trim();
      const previous = settingsRef.current?.topics.find((topic) => topic.id === topicId);
      if (!previous || !trimmed || trimmed === previous.label) return;
      setTopics((topics) => topics.map((topic) => (topic.id === topicId ? { ...topic, label: trimmed } : topic)));
      setError(null);
      try {
        const saved = toAlertTopic(await clientRef.current.updateAlertTopic(projectId, topicId, trimmed));
        setTopics((topics) => topics.map((topic) => (topic.id === topicId ? saved : topic)));
      } catch (renameError) {
        console.error("Failed to rename alert topic", renameError);
        setTopics((topics) => topics.map((topic) => (topic.id === topicId ? previous : topic)));
        setError("alertSettingsSaveFailed");
      }
    },
    [projectId],
  );

  const removeTopic = useCallback(
    async (topicId: number) => {
      const previous = settingsRef.current?.topics;
      if (!previous?.some((topic) => topic.id === topicId)) return;
      setTopics((topics) => topics.filter((topic) => topic.id !== topicId));
      setError(null);
      try {
        await clientRef.current.deleteAlertTopic(projectId, topicId);
      } catch (removeError) {
        console.error("Failed to remove alert topic", removeError);
        setTopics(() => previous);
        setError("alertSettingsSaveFailed");
      }
    },
    [projectId],
  );

  const checkNow = useCallback(async () => {
    setIsScanning(true);
    setLastScanCreated(null);
    setError(null);
    try {
      const result = await clientRef.current.scanProjectAlerts(projectId);
      setLastScanCreated(result.created);
      // Picks up the new last-scan time.
      setSettings(toAlertSettings(await clientRef.current.getAlertSettings(projectId)));
      if (result.created > 0) changedRef.current?.();
    } catch (scanError) {
      console.error("Failed to scan for alerts", scanError);
      setError(isAlertsUnavailable(scanError) ? "alertsUnavailable" : "alertScanFailed");
      await reload(settingsRef.current);
    } finally {
      setIsScanning(false);
    }
  }, [projectId, reload]);

  const dismissError = useCallback(() => setError(null), []);

  return {
    settings, isLoading, isSaving, isScanning, lastScanCreated, error,
    setEnabled, addTopic, renameTopic, removeTopic, checkNow, dismissError,
  };
}
