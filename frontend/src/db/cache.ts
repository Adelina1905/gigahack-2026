import Dexie, { type EntityTable } from "dexie";
import type { ChatMessage, ChatSummary, ProjectSummary } from "../types/chat";

// IndexedDB copy of the sidebar and chat histories. It lets a reload paint
// instantly before the server answers, and keeps unsent messages around.
// The server stays the source of truth; every read here is best-effort.

interface CachedMessage extends ChatMessage {
  chatId: string;
  // Keeps messages in conversation order, independent of their timestamps.
  position: number;
}

const db = new Dexie("smart-city-chat") as Dexie & {
  chats: EntityTable<ChatSummary, "id">;
  messages: EntityTable<CachedMessage, "id">;
  projects: EntityTable<ProjectSummary, "id">;
};

db.version(1).stores({
  chats: "id, updatedAt",
  messages: "id, chatId, [chatId+position]",
});
// Chats cached by version 1 have no projectId; readers treat it as null.
db.version(2).stores({
  projects: "id, updatedAt",
});

async function safely<T>(action: () => Promise<T>, fallback: T): Promise<T> {
  try {
    return await action();
  } catch (error) {
    // Private mode, blocked storage, quota: the app works without the cache.
    console.warn("Chat cache unavailable", error);
    return fallback;
  }
}

export function loadChats(): Promise<ChatSummary[]> {
  return safely(async () => {
    const chats = await db.chats.orderBy("updatedAt").reverse().toArray();
    return chats.map((chat) => ({ ...chat, projectId: chat.projectId ?? null }));
  }, []);
}

export function saveChats(chats: ChatSummary[]): Promise<void> {
  return safely(
    () =>
      db.transaction("rw", db.chats, async () => {
        await db.chats.clear();
        await db.chats.bulkPut(chats);
      }),
    undefined,
  );
}

export function loadProjects(): Promise<ProjectSummary[]> {
  return safely(() => db.projects.orderBy("updatedAt").reverse().toArray(), []);
}

export function saveProjects(projects: ProjectSummary[]): Promise<void> {
  return safely(
    () =>
      db.transaction("rw", db.projects, async () => {
        await db.projects.clear();
        await db.projects.bulkPut(projects);
      }),
    undefined,
  );
}

export function loadMessages(chatId: string): Promise<ChatMessage[] | null> {
  return safely(async () => {
    const rows = await db.messages
      .where("[chatId+position]")
      .between([chatId, Dexie.minKey], [chatId, Dexie.maxKey])
      .toArray();
    if (rows.length === 0) return null;
    return rows.map(({ chatId: _chatId, position: _position, ...message }) => message);
  }, null);
}

export function saveMessages(chatId: string, messages: ChatMessage[]): Promise<void> {
  return safely(
    () =>
      db.transaction("rw", db.messages, async () => {
        await db.messages.where("chatId").equals(chatId).delete();
        await db.messages.bulkPut(
          messages.map((message, position) => ({ ...message, chatId, position })),
        );
      }),
    undefined,
  );
}

export function removeChat(chatId: string): Promise<void> {
  return safely(
    () =>
      db.transaction("rw", db.chats, db.messages, async () => {
        await db.chats.delete(chatId);
        await db.messages.where("chatId").equals(chatId).delete();
      }),
    undefined,
  );
}

// Move the first-message outbox only after Java has acknowledged the chat.
export function moveDraft(chatId: string, messages: ChatMessage[]): Promise<void> {
  return safely(
    () => db.transaction("rw", db.messages, async () => {
      await db.messages.where("chatId").equals("draft").delete();
      await db.messages.where("chatId").equals(chatId).delete();
      await db.messages.bulkPut(messages.map((message, position) => ({ ...message, chatId, position })));
    }),
    undefined,
  );
}
