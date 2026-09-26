import { ApiError } from "./client";
import type { ChatView, DocumentView, ResponseView } from "./types";
import { DEFAULT_CHAT_NAME } from "../types/chat";

// In-memory stand-in for the Spring Boot API, persisted to localStorage so
// reloads behave like the real backend. Enabled with VITE_USE_MOCK=true.

const STORAGE_KEY = "smart-city-mock-api";

// Replies shaped like the real gateway output (see Manage Data/municipal_rag):
// grounded RAG answers are one claim per line ending in "[S1]" markers, with the
// cited corpus documents attached; LLM fallback answers carry no documents; a
// clarification lists its choices as "- " lines. Titles and links are real corpus sources.
type MockReply = { text: string; documents: DocumentView[] };

const EVENTS_DOCUMENT: DocumentView = {
  id: 1,
  title: "Evenimente municipale",
  // This corpus source has no URL, so the backend stores an empty link.
  documentLink: "",
  addedAt: "2026-09-25T19:27:11Z",
};

const SCHOOL_EVALUATION_DOCUMENT: DocumentView = {
  id: 2,
  title:
    "Evaluarea instituțiilor de învățământ primar și secundar, ciclul I și II către debutul anului de studii 2024-2025",
  documentLink:
    "https://detsciocana.educ.md/evaluarea-institutiilor-de-invatamant-primar-si-secundar-ciclul-i-si-ii-catre-debutul-anului-de-studii-2024-2025/",
  addedAt: "2026-09-25T19:26:50Z",
};

const DGETS_SCAN_DOCUMENT: DocumentView = {
  id: 3,
  title: "Scan DGETS 2025-09-30",
  documentLink: "https://chisinauedu.dgets.md/storage/attestations/1775034260_scan-2025-09-30-10-13-39-485.pdf",
  addedAt: "2026-09-25T19:27:30Z",
};

const EVENTS_REPLY: MockReply = {
  text: [
    "Târgurile micilor antreprenori și ale producătorilor locali cu produse autohtone eco și apicole au loc pe teritoriul sectoarelor în perioadele 04-06.09, 11-13.09, 18-20.09 și 25-27.09.2026. [S1]",
    "Târgul mămicilor „Mami&Co Fair” are loc în Scuarul „Mezon” din bd. Moscova pe 13.09 și 27.09.2026. [S1]",
    "Festivalul etniilor „Unitate prin diversitate” are loc în Grădina Publică „Ștefan cel Mare și Sfânt” pe 20.09.2026. [S1]",
  ].join("\n"),
  documents: [EVENTS_DOCUMENT],
};

const SCHOOLS_REPLY: MockReply = {
  text: [
    "Pe parcursul a 3 zile (20, 21 și 22 august 2024), 5 echipe de verificare create prin ordinul DGETS s-au deplasat la instituțiile de învățământ primar și secundar, ciclul I și II, din municipiu. [S1]",
    "Scopul vizitelor a fost verificarea pregătirii instituțiilor către noul an școlar 2024-2025. [S1] [S2]",
  ].join("\n"),
  documents: [SCHOOL_EVALUATION_DOCUMENT, DGETS_SCAN_DOCUMENT],
};

const CLARIFICATION_REPLY: MockReply = {
  text: "La care document vă referiți?\n- Evenimente municipale\n- Evaluarea instituțiilor de învățământ primar și secundar, ciclul I și II către debutul anului de studii 2024-2025",
  documents: [],
};

// Plain LLM fallback, used when the corpus has no answer.
const LLM_REPLIES: MockReply[] = [
  {
    text: "Nu dispun de informații oficiale despre acest subiect. Vă recomand să verificați pe **chisinau.md** sau să contactați Primăria municipiului Chișinău.",
    documents: [],
  },
  {
    text: "Pentru majoritatea serviciilor municipale puteți depune o cerere la **Centrul de Servicii Publice** sau online, pe portalul primăriei. Nu am însă detalii oficiale despre termenele exacte.",
    documents: [],
  },
];

const LLM_REPLY_RU: MockReply = {
  text: "У меня нет официальной информации по этому вопросу. Рекомендую уточнить на сайте **chisinau.md** или обратиться в Примэрию муниципия Кишинэу.",
  documents: [],
};

const ALL_REPLIES = [EVENTS_REPLY, SCHOOLS_REPLY, CLARIFICATION_REPLY, ...LLM_REPLIES];

// Keywords steer the reply like retrieval would; anything else gets a random one.
function pickReply(prompt: string, exclude?: string): MockReply {
  const text = prompt.toLowerCase();
  if (/[а-яё]/.test(text)) return LLM_REPLY_RU;
  if (/t[aâ]rg|eveniment|festival|event/.test(text)) return EVENTS_REPLY;
  if (/[sș]coal|[sș]colar|educa|[iî]nv[aă][tț]|dgets|school/.test(text)) return SCHOOLS_REPLY;
  if (/document/.test(text)) return CLARIFICATION_REPLY;
  const pool = ALL_REPLIES.filter((reply) => reply.text !== exclude);
  return pool[Math.floor(Math.random() * pool.length)];
}

interface MockStore {
  chats: ChatView[];
  responses: ResponseView[];
  nextResponseId: number;
}

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const now = () => new Date().toISOString();
const notFound = (what: string) => new ApiError(`${what} not found`, 404);

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
  const reply = pickReply(text);
  const response: ResponseView = {
    id: store.nextResponseId++,
    chatId,
    prompt: text.trim(),
    text: reply.text,
    createdAt: now(),
    documents: reply.documents,
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

  // The real backend reruns the same prompt, which usually retrieves the same sources.
  const reply = pickReply(response.prompt ?? "", response.text);
  response.text = reply.text;
  response.documents = reply.documents;
  chat.updatedAt = now();
  save(store);
  return response;
}
