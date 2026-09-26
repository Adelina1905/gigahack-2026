import type { ChatMessage, ChatSummary, SourceDocument } from "../types/chat";
import type { ChatView, DocumentView, ResponseView } from "./types";

// The only place backend field names are translated into UI types.

const toTimestamp = (iso: string) => {
  const time = new Date(iso).getTime();
  return Number.isNaN(time) ? Date.now() : time;
};

// Assistant message ids are the backend response id, so they can be sent back
// to the regenerate endpoint. The matching user message gets a derived id.
export const promptMessageId = (responseId: number) => `prompt-${responseId}`;

export function toChatSummary(chat: ChatView): ChatSummary {
  return {
    id: chat.id,
    name: chat.name,
    updatedAt: toTimestamp(chat.updatedAt ?? chat.createdAt),
  };
}

export function toSourceDocument(document: DocumentView): SourceDocument {
  return {
    title: document.title,
    link: document.documentLink,
    added_date: document.addedAt,
  };
}

export function toAssistantMessage(response: ResponseView): ChatMessage {
  return {
    id: String(response.id),
    role: "assistant",
    content: response.text,
    createdAt: toTimestamp(response.createdAt),
    sources: (response.documents ?? []).map(toSourceDocument),
  };
}

// One stored response is one turn: the user's prompt and the answer to it.
export function toMessages(response: ResponseView): ChatMessage[] {
  const assistant = toAssistantMessage(response);
  if (!response.prompt) return [assistant];

  return [
    {
      id: promptMessageId(response.id),
      role: "user",
      content: response.prompt,
      createdAt: assistant.createdAt,
      status: "sent",
    },
    assistant,
  ];
}
