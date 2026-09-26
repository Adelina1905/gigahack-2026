export type ChatRole = "user" | "assistant";
export type MessageStatus = "sending" | "sent" | "error";

// A document the model's answer was grounded on, as sent by the backend.
export interface SourceDocument {
  title: string;
  link: string;
  added_date: string; // ISO 8601
  exactQuote?: string | null;
  documentId?: string | null;
}

export interface RetryOperation {
  requestId: string;
  expectedGenerationVersion: number;
}

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  createdAt: number;
  // Only used for user messages.
  status?: MessageStatus;
  // Only used for assistant messages.
  sources?: SourceDocument[];
  // Stable IDs survive network failures and page reloads.
  requestId?: string;
  chatRequestId?: string;
  generationStatus?: "PENDING" | "COMPLETED" | "FAILED";
  generationVersion?: number;
  errorCode?: string | null;
  mode?: "rag" | "llm" | "demo";
  clarificationChoices?: string[];
  // Retained until the result of a retry/regeneration is known.
  retryOperation?: RetryOperation;
}

// The backend renames a chat still called this after its first prompt, so it is
// stored as-is and only translated for display.
export const DEFAULT_CHAT_NAME = "New chat";

// A chat as listed in the sidebar.
export interface ChatSummary {
  id: string;
  name: string;
  updatedAt: number;
}
