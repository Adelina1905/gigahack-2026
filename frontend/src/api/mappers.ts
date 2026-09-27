import { NOT_FOUND_REASONS, type ChatMessage, type ChatSummary, type ProjectSummary,
  type ReplyReason, type SourceDocument } from "../types/chat";
import type { Alert, AlertSettings, AlertTopic, UnreadAlertCounts } from "../types/alerts";
import type {
  AlertSettingsView,
  AlertTopicView,
  AlertUnreadCountView,
  AlertView,
  ChatView,
  DocumentView,
  ProjectView,
  ResponseView,
} from "./types";

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
    projectId: chat.projectId ?? null,
    updatedAt: toTimestamp(chat.updatedAt ?? chat.createdAt),
  };
}

export function toProjectSummary(project: ProjectView): ProjectSummary {
  return {
    id: project.id,
    name: project.name,
    updatedAt: toTimestamp(project.updatedAt ?? project.createdAt),
  };
}

export function toSourceDocument(document: DocumentView): SourceDocument {
  return {
    title: document.title,
    link: document.documentLink,
    added_date: document.addedAt,
  };
}

const REPLY_REASONS: readonly string[] = [...NOT_FOUND_REASONS, "CONFLICTING_DOCUMENTS"];
const toReason = (reason: string | null | undefined) =>
  reason && REPLY_REASONS.includes(reason) ? reason as ReplyReason : undefined;

export function toAssistantMessage(response: ResponseView): ChatMessage {
  const flags = (response.aiReply?.flags ?? []).filter(flag => typeof flag === "string");
  const citations = response.aiReply?.citations ?? [];
  // Replies that only carry the flag mark every source; per-citation marks are exact.
  const allOutdated = flags.includes("OUTDATED_SOURCES") && citations.every(citation => citation.outdated == null);
  return {
    id: String(response.id),
    role: "assistant",
    content: response.text ?? "",
    createdAt: toTimestamp(response.createdAt),
    sources: response.aiReply
      ? citations.map((citation) => ({
          id: citation.id,
          evidenceId: citation.evidenceId,
          versionId: citation.versionId,
          title: citation.title || citation.documentId || "Source",
          link: citation.url ?? "",
          added_date: "",
          exactQuote: citation.exactQuote,
          documentId: citation.documentId,
          sourceFile: citation.sourceFile,
          locator: citation.locator,
          publisher: citation.publisher ?? null,
          publishedDate: citation.publishedDate ?? null,
          outdated: citation.outdated === true || allOutdated,
        }))
      : (response.documents ?? []).map(toSourceDocument),
    requestId: response.requestId ?? undefined,
    generationStatus: response.generationStatus ?? "COMPLETED",
    generationVersion: response.generationVersion ?? 0,
    errorCode: response.errorCode,
    mode: response.aiReply?.mode,
    replyStatus: response.aiReply?.status,
    reason: toReason(response.aiReply?.reason),
    flags: flags.length > 0 ? flags : undefined,
    clarificationChoices: (response.aiReply?.clarificationChoices ?? []).map(choice => choice.label),
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
      requestId: response.requestId ?? undefined,
    },
    assistant,
  ];
}

export function toAlert(alert: AlertView): Alert {
  return {
    id: alert.id,
    projectId: alert.projectId ?? null,
    chatId: alert.chatId ?? null,
    topicId: alert.topicId ?? null,
    topicLabel: alert.topicLabel,
    documentId: alert.documentId,
    title: alert.title,
    url: alert.url ?? null,
    source: alert.source ?? null,
    district: alert.district ?? null,
    category: alert.category ?? null,
    publishedDate: alert.publishedDate ?? null,
    excerpt: alert.excerpt ?? "",
    score: alert.score,
    createdAt: toTimestamp(alert.createdAt),
    isRead: Boolean(alert.readAt),
  };
}

export function toUnreadAlertCounts(counts: AlertUnreadCountView): UnreadAlertCounts {
  return {
    total: counts.total ?? 0,
    byProject: { ...(counts.byProject ?? {}) },
    byChat: { ...(counts.byChat ?? {}) },
  };
}

export function toAlertTopic(topic: AlertTopicView): AlertTopic {
  return {
    id: topic.id,
    label: topic.label,
    query: topic.query,
    isAuto: topic.source === "AUTO",
    minScore: topic.minScore ?? null,
  };
}

export function toAlertSettings(settings: AlertSettingsView): AlertSettings {
  return {
    projectId: settings.projectId ?? null,
    chatId: settings.chatId ?? null,
    enabled: settings.enabled,
    prompted: settings.prompted,
    topics: (settings.topics ?? []).map(toAlertTopic),
    lastScanAt: settings.lastScanAt ? toTimestamp(settings.lastScanAt) : null,
  };
}
