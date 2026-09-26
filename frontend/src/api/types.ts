import type { SourceDocument } from "../types/chat";

// Assistant reply as returned by the backend.
export interface AssistantResponse {
  id: string;
  content: string;
  created_at: string; // ISO 8601
  sources: SourceDocument[];
}

export interface DatasetService {
  createResponse(chatId: string): Promise<AssistantResponse>;
}
