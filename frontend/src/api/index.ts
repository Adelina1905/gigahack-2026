import * as realClient from "./client";
import * as mockClient from "./mockClient";

export { ApiError } from "./client";

// Set VITE_USE_MOCK=true to work on the UI without the backend running.
export const api = {
  getChats: realClient.getChats,
  getChat: realClient.getChat,
  createChat: realClient.createChat,
  updateChat: realClient.updateChat,
  deleteChat: realClient.deleteChat,
  setChatProject: realClient.setChatProject,
  getProjects: realClient.getProjects,
  createProject: realClient.createProject,
  updateProject: realClient.updateProject,
  deleteProject: realClient.deleteProject,
  getResponses: realClient.getResponses,
  getResponse: realClient.getResponse,
  createResponse: realClient.createResponse,
  regenerateResponse: realClient.regenerateResponse,
  transcribeAudio: realClient.transcribeAudio,
  getResponseSpeech: realClient.getResponseSpeech,
  getSourcePreview: realClient.getSourcePreview,
  getAlerts: realClient.getAlerts,
  getAlertUnreadCount: realClient.getAlertUnreadCount,
  markAlertRead: realClient.markAlertRead,
  markAllAlertsRead: realClient.markAllAlertsRead,
  markAlertNotRelevant: realClient.markAlertNotRelevant,
  getAlertSettings: realClient.getAlertSettings,
  updateAlertSettings: realClient.updateAlertSettings,
  refreshAlertTopics: realClient.refreshAlertTopics,
  createAlertTopic: realClient.createAlertTopic,
  updateAlertTopic: realClient.updateAlertTopic,
  deleteAlertTopic: realClient.deleteAlertTopic,
  scanProjectAlerts: realClient.scanProjectAlerts,
  ...(import.meta.env.VITE_USE_MOCK === "true" ? mockClient : {}),
};

export type Api = typeof api;
