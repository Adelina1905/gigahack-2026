import { ApiError } from "./client";
import type { ChatView, DocumentView, ResponseView } from "./types";
import { DEFAULT_CHAT_NAME } from "../types/chat";

// In-memory stand-in for the Spring Boot API, persisted to localStorage so
// reloads behave like the real backend. Enabled with VITE_USE_MOCK=true.

const STORAGE_KEY = "smart-city-mock-api";

const CANNED_REPLIES = [
  "Sure! Here's a quick overview of how that works.",
  "Good question. Let me break it down step by step:\n1. First, upload your file.\n2. Then I'll extract the text.\n3. Finally, you can ask me anything about it.",
  "I'm a mock assistant for now, but the real answer will appear right here.",
];

const MOCK_DOCUMENTS: DocumentView[] = [
  {
    id: 1,
    title: "Urban Mobility Plan 2030 — Public Transport Strategy",
    documentLink: "https://en.wikipedia.org/wiki/Public_transport",
    addedAt: "2026-08-14T09:30:00Z",
  },
  {
    id: 2,
    title: "Smart City Open Data Portal: Air Quality Measurements",
    documentLink: "https://www.who.int/health-topics/air-pollution",
    addedAt: "2026-09-02T14:10:00Z",
  },
  {
    id: 3,
    title: "Municipal Waste Management Annual Report",
    documentLink: "https://www.eea.europa.eu/en/topics/in-depth/waste-and-recycling",
    addedAt: "2026-07-21T08:00:00Z",
  },
  {
    id: 4,
    title: "Guidelines for Citizen Service Requests",
    documentLink: "https://developer.mozilla.org/en-US/docs/Web/HTTP",
    addedAt: "2026-09-20T17:45:00Z",
  },
];

interface MockStore {
  chats: ChatView[];
  responses: ResponseView[];
  nextResponseId: number;
}

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const now = () => new Date().toISOString();
const notFound = (what: string) => new ApiError(`${what} not found`, 404);

// Picks 0–4 random sources so both the empty and populated states show up.
const pickDocuments = () =>
  [...MOCK_DOCUMENTS]
    .sort(() => Math.random() - 0.5)
    .slice(0, Math.floor(Math.random() * 5));

const pickReply = (exclude?: string) => {
  const pool = CANNED_REPLIES.filter((reply) => reply !== exclude);
  return pool[Math.floor(Math.random() * pool.length)];
};

const titleFrom = (text: string) => {
  const singleLine = text.replace(/\s+/g, " ").trim();
  return singleLine.length <= 50 ? singleLine : `${singleLine.slice(0, 49).trim()}…`;
};

function load(): MockStore {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw) as MockStore;
  } catch {
    // Storage unavailable or corrupt: start empty.
  }
  return { chats: [], responses: [], nextResponseId: 1 };
}

function save(store: MockStore) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  } catch {
    // Mock data just won't survive a reload.
  }
}

function findChat(store: MockStore, chatId: string) {
  const chat = store.chats.find((candidate) => candidate.id === chatId);
  if (!chat) throw notFound("Chat");
  return chat;
}

const byUpdatedDesc = (a: ChatView, b: ChatView) =>
  b.updatedAt.localeCompare(a.updatedAt);

export async function getChats(): Promise<ChatView[]> {
  await wait(150);
  return [...load().chats].sort(byUpdatedDesc);
}

export async function getChat(chatId: string): Promise<ChatView> {
  await wait(100);
  return findChat(load(), chatId);
}

export async function createChat(name = DEFAULT_CHAT_NAME): Promise<ChatView> {
  await wait(100);
  const store = load();
  const timestamp = now();
  const chat: ChatView = {
    id: crypto.randomUUID(),
    name,
    createdAt: timestamp,
    updatedAt: timestamp,
  };
  store.chats.push(chat);
  save(store);
  return chat;
}

export async function updateChat(chatId: string, name: string): Promise<ChatView> {
  await wait(100);
  const store = load();
  const chat = findChat(store, chatId);
  chat.name = name.trim();
  save(store);
  return chat;
}

export async function deleteChat(chatId: string): Promise<void> {
  await wait(100);
  const store = load();
  findChat(store, chatId);
  store.chats = store.chats.filter((chat) => chat.id !== chatId);
  store.responses = store.responses.filter((response) => response.chatId !== chatId);
  save(store);
}

export async function getResponses(chatId: string): Promise<ResponseView[]> {
  await wait(200);
  const store = load();
  findChat(store, chatId);
  return store.responses.filter((response) => response.chatId === chatId);
}

export async function createResponse(chatId: string, text: string): Promise<ResponseView> {
  await wait(800 + Math.random() * 700);
  // Type a message containing "fail" to preview the error state.
  if (text.toLowerCase().includes("fail")) {
    throw new ApiError("Mock failure", 500);
  }

  const store = load();
  const chat = findChat(store, chatId);
  const response: ResponseView = {
    id: store.nextResponseId++,
    chatId,
    prompt: text.trim(),
    text: pickReply(),
    createdAt: now(),
    documents: pickDocuments(),
  };

  store.responses.push(response);
  if (chat.name === DEFAULT_CHAT_NAME) chat.name = titleFrom(text);
  chat.updatedAt = response.createdAt;
  save(store);
  return response;
}

export async function regenerateResponse(
  chatId: string,
  responseId: number,
): Promise<ResponseView> {
  await wait(800 + Math.random() * 700);
  const store = load();
  const chat = findChat(store, chatId);
  const response = store.responses.find(
    (candidate) => candidate.id === responseId && candidate.chatId === chatId,
  );
  if (!response) throw notFound("Response");

  response.text = pickReply(response.text);
  response.documents = pickDocuments();
  chat.updatedAt = now();
  save(store);
  return response;
}
