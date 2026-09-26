import type { ChatMessage } from "../types/chat";

export const DRAFT = "draft";

export const isUnsent = (message: ChatMessage) =>
  message.role === "user" && message.status !== "sent";

export function restoreCached(messages: ChatMessage[]) {
  return messages.map((message) =>
    message.role === "user" && message.status === "sending"
      ? { ...message, status: "error" as const }
      : message,
  );
}

// The request UUID identifies delivery, even when the HTTP reply was lost.
// Cached generation state must never replace a newer server generation.
export function mergeWithServer(server: ChatMessage[], local: ChatMessage[]) {
  const delivered = new Set(
    server.filter((message) => message.role === "user").map((message) => message.requestId),
  );
  const reconciled = server.map((message) => {
    const previous = local.find((candidate) => candidate.id === message.id);
    if ((previous?.generationVersion ?? 0) > (message.generationVersion ?? 0)) return previous!;
    const operation = previous?.retryOperation;
    if (operation && (message.generationVersion ?? 0) <= operation.expectedGenerationVersion) {
      return { ...message, retryOperation: operation };
    }
    return message;
  });
  return [
    ...reconciled,
    ...local.filter((message) => isUnsent(message) &&
      (!message.requestId || !delivered.has(message.requestId))),
  ];
}

export function settleTurn(thread: ChatMessage[], requestId: string, turn: ChatMessage[]) {
  const turnIds = new Set(turn.map((message) => message.id));
  const first = thread.findIndex((message) => message.requestId === requestId || turnIds.has(message.id));
  const others = thread.filter((message) => message.requestId !== requestId && !turnIds.has(message.id));
  const index = first === -1 ? others.length : Math.min(first, others.length);
  return [...others.slice(0, index), ...turn, ...others.slice(index)];
}

export const hasPendingGeneration = (messages: ChatMessage[]) =>
  messages.some((message) => message.role === "assistant" && message.generationStatus === "PENDING");
