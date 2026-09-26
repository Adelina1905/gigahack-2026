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
  getResponses: realClient.getResponses,
  getResponse: realClient.getResponse,
  createResponse: realClient.createResponse,
  regenerateResponse: realClient.regenerateResponse,
  transcribeAudio: realClient.transcribeAudio,
  getResponseSpeech: realClient.getResponseSpeech,
  ...(import.meta.env.VITE_USE_MOCK === "true" ? mockClient : {}),
};
