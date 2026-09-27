export type ChatRole = "user" | "assistant";
export type MessageStatus = "sending" | "sent" | "error";

// A document the model's answer was grounded on, as sent by the backend.
export interface SourceDocument {
  id?: string | null;
  evidenceId?: string | null;
  versionId?: string | null;
  title: string;
  link: string;
  added_date: string; // ISO 8601
  exactQuote?: string | null;
  documentId?: string | null;
  sourceFile?: string | null;
  locator?: Record<string, unknown> | null;
  publisher?: string | null;
  publishedDate?: string | null; // YYYY-MM-DD
  // An older document than the newest one found on the topic.
  outdated?: boolean;
}

export const NOT_FOUND_REASONS = ["NO_RELEVANT_EVIDENCE", "EVIDENCE_LACKS_VALUE", "CLAIMS_UNVERIFIED", "OUT_OF_SCOPE"] as const;
export type NotFoundReason = (typeof NOT_FOUND_REASONS)[number];
export type ReplyReason = NotFoundReason | "CONFLICTING_DOCUMENTS";

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
  // SUPPORTED, PARTIAL, CONTRADICTION, NEEDS_CLARIFICATION, NOT_FOUND, or a legacy value.
  replyStatus?: string;
  reason?: ReplyReason;
  flags?: string[];
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
  // The project the chat is filed under; null keeps it in the date-grouped list.
  projectId: string | null;
  updatedAt: number;
}

// A project as listed in the sidebar. Its chats come from the chat list.
export interface ProjectSummary {
  id: string;
  name: string;
  updatedAt: number;
}
