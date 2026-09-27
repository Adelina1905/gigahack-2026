import type { Api } from "../api";
import type { AlertScope } from "../types/alerts";

// A project's and a chat's alert subscriptions have the same endpoints under
// different paths; these pick the right client function for a scope.

export const getScopeSettings = (client: Pick<Api, "getAlertSettings" | "getChatAlertSettings">, scope: AlertScope) =>
  scope.kind === "project" ? client.getAlertSettings(scope.id) : client.getChatAlertSettings(scope.id);

export const updateScopeSettings = (
  client: Pick<Api, "updateAlertSettings" | "updateChatAlertSettings">,
  scope: AlertScope,
  enabled: boolean,
) =>
  scope.kind === "project"
    ? client.updateAlertSettings(scope.id, enabled)
    : client.updateChatAlertSettings(scope.id, enabled);

export const refreshScopeTopics = (
  client: Pick<Api, "refreshAlertTopics" | "refreshChatAlertTopics">,
  scope: AlertScope,
) => (scope.kind === "project" ? client.refreshAlertTopics(scope.id) : client.refreshChatAlertTopics(scope.id));

export const createScopeTopic = (
  client: Pick<Api, "createAlertTopic" | "createChatAlertTopic">,
  scope: AlertScope,
  label: string,
) => (scope.kind === "project" ? client.createAlertTopic(scope.id, label) : client.createChatAlertTopic(scope.id, label));

export const updateScopeTopic = (
  client: Pick<Api, "updateAlertTopic" | "updateChatAlertTopic">,
  scope: AlertScope,
  topicId: number,
  label: string,
) =>
  scope.kind === "project"
    ? client.updateAlertTopic(scope.id, topicId, label)
    : client.updateChatAlertTopic(scope.id, topicId, label);

export const deleteScopeTopic = (
  client: Pick<Api, "deleteAlertTopic" | "deleteChatAlertTopic">,
  scope: AlertScope,
  topicId: number,
) => (scope.kind === "project" ? client.deleteAlertTopic(scope.id, topicId) : client.deleteChatAlertTopic(scope.id, topicId));

export const scanScope = (client: Pick<Api, "scanProjectAlerts" | "scanChatAlerts">, scope: AlertScope) =>
  scope.kind === "project" ? client.scanProjectAlerts(scope.id) : client.scanChatAlerts(scope.id);
