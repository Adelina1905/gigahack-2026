import type { ChatMessage, SourceDocument } from "../types/chat";
import type { DocumentView, ResponseView } from "./types";

// The only place backend field names are translated into UI types.

export function toSourceDocument(document: DocumentView): SourceDocument {
  return {
    title: document.title,
    link: document.documentLink,
    added_date: document.addedAt,
  };
}

export function toAssistantMessage(response: ResponseView): ChatMessage {
  const createdAt = new Date(response.createdAt).getTime();

  return {
    id: String(response.id),
    role: "assistant",
    content: response.text,
    createdAt: Number.isNaN(createdAt) ? Date.now() : createdAt,
    sources: (response.documents ?? []).map(toSourceDocument),
  };
}
