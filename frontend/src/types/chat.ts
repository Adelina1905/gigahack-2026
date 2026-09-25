export type ChatRole = "user" | "assistant";
export type MessageStatus = "sending" | "sent" | "error";

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  createdAt: number;
  // Only used for user messages.
  status?: MessageStatus;
}
