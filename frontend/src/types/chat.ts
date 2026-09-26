export type ChatRole = "user" | "assistant";
export type MessageStatus = "sending" | "sent" | "error";

// A document the model's answer was grounded on, as sent by the backend.
export interface SourceDocument {
  title: string;
  link: string;
  added_date: string; // ISO 8601
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
}

// A chat as listed in the sidebar.
export interface ChatSummary {
  id: string;
  name: string;
  updatedAt: number;
}
