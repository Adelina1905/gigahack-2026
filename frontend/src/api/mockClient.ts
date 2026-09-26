import { ApiError } from "./client";
import type { AlertListQuery } from "./client";
import type {
  AlertScanView,
  AlertSettingsView,
  AlertTopicView,
  AlertUnreadCountView,
  AlertView,
  ChatView,
  DocumentView,
  ProjectView,
  ResponseView,
  SourcePreviewView,
} from "./types";
import { DEFAULT_CHAT_NAME } from "../types/chat";

// In-memory stand-in for the Spring Boot API, persisted to localStorage so
// reloads behave like the real backend. Enabled with VITE_USE_MOCK=true.

const STORAGE_KEY = "smart-city-mock-api";

// Replies shaped like the real gateway output (see Manage Data/municipal_rag):
// grounded RAG answers are one claim per line ending in "[S1]" markers, with the
// cited corpus documents attached; LLM fallback answers carry no documents; a
// clarification lists its choices as "- " lines. Titles and links are real corpus sources.
type MockCitation = NonNullable<ResponseView["aiReply"]>["citations"][number];
type MockReply = { text: string; documents: DocumentView[]; citations?: MockCitation[] };

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
  citations: [{
    id: "S1",
    evidenceId: "events-calendar",
    versionId: "demo-2026-09",
    title: EVENTS_DOCUMENT.title,
    url: null,
    exactQuote: "Târgurile micilor antreprenori și ale producătorilor locali au loc în fiecare weekend din septembrie 2026.",
    documentId: "events-2026",
    sourceFile: "evenimente-municipale.txt",
    locator: { startLine: 12, endLine: 16 },
  }],
};

const SCHOOLS_REPLY: MockReply = {
  text: [
    "Pe parcursul a 3 zile (20, 21 și 22 august 2024), 5 echipe de verificare create prin ordinul DGETS s-au deplasat la instituțiile de învățământ primar și secundar, ciclul I și II, din municipiu. [S1]",
    "Scopul vizitelor a fost verificarea pregătirii instituțiilor către noul an școlar 2024-2025. [S1] [S2]",
  ].join("\n"),
  documents: [SCHOOL_EVALUATION_DOCUMENT, DGETS_SCAN_DOCUMENT],
  citations: [
    {
      id: "S1",
      evidenceId: "school-visits",
      versionId: "demo-2024-08",
      title: SCHOOL_EVALUATION_DOCUMENT.title,
      url: SCHOOL_EVALUATION_DOCUMENT.documentLink,
      exactQuote: "Pe parcursul a 3 zile, 20, 21 și 22 august 2024, cinci echipe de verificare s-au deplasat la instituțiile de învățământ.",
      documentId: "school-evaluation-2024",
      sourceFile: "evaluarea-institutiilor.html",
      locator: { startLine: 24, endLine: 27 },
    },
    {
      id: "S2",
      evidenceId: "school-readiness",
      versionId: "demo-2025-09",
      title: DGETS_SCAN_DOCUMENT.title,
      url: DGETS_SCAN_DOCUMENT.documentLink,
      exactQuote: "Scopul vizitelor a fost verificarea pregătirii instituțiilor către noul an școlar.",
      documentId: "dgets-scan-2025",
      sourceFile: "scan-dgets-2025-09-30.pdf",
      locator: { page: 2 },
    },
  ],
};

const SOURCE_PREVIEWS: Record<string, SourcePreviewView> = {
  "events-2026": {
    documentId: "events-2026",
    versionId: "demo-2026-09",
    title: EVENTS_DOCUMENT.title,
    sourceUrl: null,
    sourceFile: "evenimente-municipale.txt",
    sourceKind: "text",
    publishedDate: "2026-09-01",
    totalSections: 3,
    start: 0,
    focusIndex: 1,
    focusSectionId: "events-calendar",
    hasPrevious: false,
    hasNext: false,
    sections: [
      { id: "events-intro", order: 0, headingPath: ["Agenda municipală"], text: "Programul reunește activitățile publice anunțate pentru luna septembrie 2026.", locator: { startLine: 1, endLine: 3 } },
      { id: "events-calendar", order: 1, headingPath: ["Târguri locale"], text: "Târgurile micilor antreprenori și ale producătorilor locali au loc în fiecare weekend din septembrie 2026.", locator: { startLine: 12, endLine: 16 } },
      { id: "events-festival", order: 2, headingPath: ["Festivaluri"], text: "Festivalul etniilor este programat în Grădina Publică «Ștefan cel Mare și Sfânt».", locator: { startLine: 18, endLine: 20 } },
    ],
  },
  "school-evaluation-2024": {
    documentId: "school-evaluation-2024",
    versionId: "demo-2024-08",
    title: SCHOOL_EVALUATION_DOCUMENT.title,
    sourceUrl: SCHOOL_EVALUATION_DOCUMENT.documentLink,
    sourceFile: "evaluarea-institutiilor.html",
    sourceKind: "web",
    publishedDate: "2024-08-23",
    totalSections: 3,
    start: 0,
    focusIndex: 1,
    focusSectionId: "school-visits",
    hasPrevious: false,
    hasNext: false,
    sections: [
      { id: "school-purpose", order: 0, headingPath: ["Pregătirea noului an școlar"], text: "DGETS a organizat evaluarea instituțiilor înainte de debutul anului de studii 2024–2025.", locator: { startLine: 18, endLine: 21 } },
      { id: "school-visits", order: 1, headingPath: ["Vizite de verificare"], text: "Pe parcursul a 3 zile, 20, 21 și 22 august 2024, cinci echipe de verificare s-au deplasat la instituțiile de învățământ.", locator: { startLine: 24, endLine: 27 } },
      { id: "school-result", order: 2, headingPath: ["Concluzii"], text: "Observațiile colectate au fost comunicate administrațiilor instituțiilor pentru remediere.", locator: { startLine: 31, endLine: 33 } },
    ],
  },
  "dgets-scan-2025": {
    documentId: "dgets-scan-2025",
    versionId: "demo-2025-09",
    title: DGETS_SCAN_DOCUMENT.title,
    sourceUrl: DGETS_SCAN_DOCUMENT.documentLink,
    sourceFile: "scan-dgets-2025-09-30.pdf",
    sourceKind: "pdf",
    publishedDate: "2025-09-30",
    totalSections: 2,
    start: 0,
    focusIndex: 0,
    focusSectionId: "school-readiness",
    hasPrevious: false,
    hasNext: false,
    sections: [
      { id: "school-readiness", order: 0, headingPath: ["Raport de verificare"], text: "Scopul vizitelor a fost verificarea pregătirii instituțiilor către noul an școlar.", locator: { page: 2 } },
      { id: "school-actions", order: 1, headingPath: ["Măsuri recomandate"], text: "Instituțiile au primit recomandări privind siguranța, igiena și organizarea spațiilor educaționale.", locator: { page: 3 } },
    ],
  },
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
  if (/t[aâ]rg|fair|eveniment|festival|event/.test(text)) return EVENTS_REPLY;
  if (/[sș]coal|[sș]colar|educa|[iî]nv[aă][tț]|dgets|school/.test(text)) return SCHOOLS_REPLY;
  if (/document/.test(text)) return CLARIFICATION_REPLY;
  const pool = ALL_REPLIES.filter((reply) => reply.text !== exclude);
  return pool[Math.floor(Math.random() * pool.length)];
}

type StoredProject = Omit<ProjectView, "chats">;

interface StoredAlertSettings {
  enabled: boolean;
  prompted: boolean;
  topicsRefreshedAt: string | null;
  lastScanAt: string | null;
}

interface StoredAlertTopic extends AlertTopicView {
  projectId: string;
  // Removed AUTO topics are kept so a refresh never brings them back.
  removed: boolean;
}

interface StoredAlert extends AlertView {
  dismissed: boolean;
}

interface MockStore {
  // Missing in stores saved before projects existed.
  projects?: StoredProject[];
  chats: ChatView[];
  responses: ResponseView[];
  nextResponseId: number;
  // Missing in stores saved before alerts existed.
  alertSettings?: Record<string, StoredAlertSettings>;
  alertTopics?: StoredAlertTopic[];
  alerts?: StoredAlert[];
  nextAlertId?: number;
}

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const now = () => new Date().toISOString();
const notFound = (what: string) => new ApiError(`${what} not found`, 404);
const aiReplyFor = (reply: MockReply): ResponseView["aiReply"] => reply.citations ? {
  mode: "rag",
  status: "SUPPORTED",
  answer: reply.text,
  citations: reply.citations,
  clarificationChoices: null,
} : null;

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
  return { projects: [], chats: [], responses: [], nextResponseId: 1 };
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

const byUpdatedDesc = (a: { updatedAt: string }, b: { updatedAt: string }) =>
  b.updatedAt.localeCompare(a.updatedAt);

const projectsOf = (store: MockStore) => (store.projects ??= []);

function findProject(store: MockStore, projectId: string) {
  const project = projectsOf(store).find((candidate) => candidate.id === projectId);
  if (!project) throw notFound("Project");
  return project;
}

const withChats = (store: MockStore, project: StoredProject): ProjectView => ({
  ...project,
  chats: store.chats
    .filter((chat) => chat.projectId === project.id)
    .map((chat) => ({ ...chat, projectId: chat.projectId ?? null }))
    .sort(byUpdatedDesc),
});

function validName(name: string) {
  const trimmed = name.trim();
  if (!trimmed || trimmed.length > 255) throw new ApiError("Invalid project name", 400);
  return trimmed;
}

export async function getProjects(): Promise<ProjectView[]> {
  await wait(150);
  const store = load();
  return [...projectsOf(store)].sort(byUpdatedDesc).map((project) => withChats(store, project));
}

export async function createProject(name: string): Promise<ProjectView> {
  await wait(100);
  const store = load();
  const timestamp = now();
  const project: StoredProject = {
    id: crypto.randomUUID(),
    name: validName(name),
    createdAt: timestamp,
    updatedAt: timestamp,
  };
  projectsOf(store).push(project);
  save(store);
  return withChats(store, project);
}

export async function updateProject(projectId: string, name: string): Promise<ProjectView> {
  await wait(100);
  const store = load();
  const project = findProject(store, projectId);
  project.name = validName(name);
  project.updatedAt = now();
  save(store);
  return withChats(store, project);
}

// Like ON DELETE SET NULL: the chats stay and lose their project.
export async function deleteProject(projectId: string): Promise<void> {
  await wait(100);
  const store = load();
  findProject(store, projectId);
  store.projects = projectsOf(store).filter((project) => project.id !== projectId);
  // Like ON DELETE CASCADE on the alert tables.
  if (store.alertSettings) delete store.alertSettings[projectId];
  store.alertTopics = alertTopicsOf(store).filter((topic) => topic.projectId !== projectId);
  store.alerts = alertsOf(store).filter((alert) => alert.projectId !== projectId);
  for (const chat of store.chats) {
    if (chat.projectId === projectId) chat.projectId = null;
  }
  save(store);
}

export async function setChatProject(chatId: string, projectId: string | null): Promise<ChatView> {
  await wait(100);
  const store = load();
  const chat = findChat(store, chatId);
  if (projectId) findProject(store, projectId).updatedAt = now();
  chat.projectId = projectId;
  save(store);
  return chat;
}

export async function getChats(): Promise<ChatView[]> {
  await wait(150);
  return load().chats
    .map((chat) => ({ ...chat, projectId: chat.projectId ?? null }))
    .sort(byUpdatedDesc);
}

export async function getChat(chatId: string): Promise<ChatView> {
  await wait(100);
  const chat = findChat(load(), chatId);
  return { ...chat, projectId: chat.projectId ?? null };
}

export async function createChat(
  name = DEFAULT_CHAT_NAME,
  _requestId?: string,
  projectId?: string | null,
): Promise<ChatView> {
  await wait(100);
  const store = load();
  const timestamp = now();
  if (projectId) findProject(store, projectId).updatedAt = timestamp;
  const chat: ChatView = {
    id: crypto.randomUUID(),
    name,
    projectId: projectId ?? null,
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

export async function getSourcePreview(
  documentId: string,
  options: { versionId?: string | null; focusEvidenceId?: string | null; start?: number; limit?: number; signal?: AbortSignal } = {},
): Promise<SourcePreviewView> {
  await wait(250);
  if (options.signal?.aborted) throw new DOMException("The operation was aborted", "AbortError");
  const preview = SOURCE_PREVIEWS[documentId];
  if (!preview || (options.versionId && options.versionId !== preview.versionId)) throw notFound("Source preview");

  const start = Math.max(0, options.start ?? 0);
  const limit = Math.max(1, options.limit ?? 40);
  const sections = preview.sections.slice(start, start + limit);
  const focusSectionId = options.focusEvidenceId ?? preview.focusSectionId;
  const focusIndex = focusSectionId
    ? preview.sections.findIndex((section) => section.id === focusSectionId)
    : -1;
  return {
    ...preview,
    start,
    focusIndex: focusIndex >= 0 ? focusIndex : null,
    focusSectionId: focusIndex >= 0 ? focusSectionId : null,
    hasPrevious: start > 0,
    hasNext: start + sections.length < preview.sections.length,
    sections,
  };
}

export async function createResponse(
  chatId: string,
  text: string,
  requestId: string = crypto.randomUUID(),
): Promise<ResponseView> {
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
    requestId,
    generationStatus: "COMPLETED",
    generationVersion: 0,
    aiReply: aiReplyFor(reply),
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
  const reply = pickReply(response.prompt ?? "", response.text ?? undefined);
  response.text = reply.text;
  response.documents = reply.documents;
  response.aiReply = aiReplyFor(reply);
  response.generationVersion = (response.generationVersion ?? 0) + 1;
  chat.updatedAt = now();
  save(store);
  return response;
}

// ---- Project alerts -------------------------------------------------------
// A small demo feed stands in for the Python matcher: topics come from keyword
// rules over the project's prompts, and documents match topics by shared words.

interface FeedDocument {
  documentId: string;
  title: string;
  url: string | null;
  source: string | null;
  district: string | null;
  category: string | null;
  publishedDate: string | null;
  excerpt: string;
}

const DEMO_FEED: FeedDocument[] = [
  {
    documentId: "demo-roads-botanica-2026",
    title: "Programul de reparație a drumurilor pentru 2026: străzile incluse din sectorul Botanica",
    url: "https://www.chisinau.md/",
    source: "Primăria municipiului Chișinău",
    district: "Botanica",
    category: "Infrastructură",
    publishedDate: "2026-09-22",
    excerpt: "Lucrările de reparație capitală a drumurilor vor începe pe str. Independenței și bd. Dacia. Traficul va fi deviat pe durata lucrărilor.",
  },
  {
    documentId: "demo-trolleybus-schedule",
    title: "Orar nou pentru rutele de troleibuz nr. 22 și 24 din 1 octombrie",
    url: "https://www.chisinau.md/",
    source: "Regia Transport Electric",
    district: "Centru",
    category: "Transport public",
    publishedDate: "2026-09-24",
    excerpt: "Intervalul de circulație a troleibuzelor pe rutele 22 și 24 se reduce la 8 minute în orele de vârf. Transportul public circulă până la ora 23:00.",
  },
  {
    documentId: "demo-kindergarten-enrolment",
    title: "Calendarul înscrierii copiilor în grădinițe pentru anul de studii 2026–2027",
    url: "https://www.chisinau.md/",
    source: "DGETS",
    district: null,
    category: "Educație",
    publishedDate: "2026-09-20",
    excerpt: "Înscrierea în grădinițele și școlile municipale se face online. Părinții depun cererea până la 15 octombrie.",
  },
  {
    documentId: "demo-school-renovation-ciocana",
    title: "Lucrări de renovare a unui liceu din sectorul Ciocana",
    url: null,
    source: "Pretura sectorului Ciocana",
    district: "Ciocana",
    category: "Educație",
    publishedDate: "2026-09-18",
    excerpt: "Renovarea sălii de sport și a blocului alimentar al școlii se încheie până la sfârșitul lunii noiembrie. Elevii învață conform orarului obișnuit.",
  },
  {
    documentId: "demo-water-outage-buiucani",
    title: "Sistarea apei potabile pe str. Alba Iulia pe 29 septembrie",
    url: "https://www.chisinau.md/",
    source: "Apă-Canal Chișinău",
    district: "Buiucani",
    category: "Utilități",
    publishedDate: "2026-09-25",
    excerpt: "Din cauza lucrărilor la rețeaua de apă și canalizare, furnizarea apei va fi sistată între orele 09:00 și 17:00.",
  },
  {
    documentId: "demo-autumn-fair",
    title: "Târgul de toamnă al producătorilor autohtoni în Piața Marii Adunări Naționale",
    url: "https://www.chisinau.md/",
    source: "Primăria municipiului Chișinău",
    district: "Centru",
    category: "Evenimente",
    publishedDate: "2026-09-23",
    excerpt: "Târgul cu produse autohtone, eco și apicole are loc în weekend. Evenimentul include concerte și un festival gastronomic.",
  },
  {
    documentId: "demo-valea-morilor-park",
    title: "Amenajarea parcului „Valea Morilor”: începe etapa a doua",
    url: "https://www.chisinau.md/",
    source: "Primăria municipiului Chișinău",
    district: "Buiucani",
    category: "Spații verzi",
    publishedDate: "2026-09-19",
    excerpt: "În parc vor fi plantați 300 de copaci, iar aleile și terenurile de joacă vor fi renovate.",
  },
  {
    documentId: "demo-electric-buses-route-30",
    title: "Autobuze electrice noi pe ruta 30 spre Aeroport",
    url: "https://www.chisinau.md/",
    source: "Parcul Urban de Autobuze",
    district: null,
    category: "Transport public",
    publishedDate: "2026-09-26",
    excerpt: "Zece autobuze electrice noi circulă pe ruta 30. Stațiile de încărcare sunt instalate la capătul traseului.",
  },
];

// Keyword rules that stand in for LLM topic extraction; prompts may be RO, RU or EN.
const TOPIC_RULES: Array<{ pattern: RegExp; label: string; query: string }> = [
  { pattern: /[sș]coal|[sș]colar|liceu|gr[aă]dini|educa|dgets|school|kindergarten|школ|детск|образов/i,
    label: "Școli și grădinițe", query: "școli grădinițe educație înscriere" },
  { pattern: /transport|troleibuz|autobuz|rut[aăe]|traseu|bus|автобус|троллейбус|маршрут/i,
    label: "Transport public", query: "transport public troleibuz autobuz rute" },
  { pattern: /drum|strad|str[aă]zi|repara|asfalt|road|дорог|улиц|ремонт/i,
    label: "Reparații de drumuri", query: "reparație drumuri străzi lucrări" },
  { pattern: /t[aâ]rg|eveniment|festival|concert|fair|event|ярмарк|фестивал|мероприят/i,
    label: "Evenimente și târguri", query: "târg eveniment festival" },
  { pattern: /(?:^|\s)ap[aăe](?=$|[\s,.?!])|canaliz|water|вод[аы]|канализ/i,
    label: "Apă și canalizare", query: "apă canalizare sistare" },
  { pattern: /parc|spa[tț]ii verzi|copac|park|парк|сквер/i,
    label: "Parcuri și spații verzi", query: "parc spații verzi copaci amenajare" },
];

const DEFAULT_MIN_SCORE = 0.55;
const MANUAL_SCAN_LIMIT = 3;
const BACKGROUND_SCAN_LIMIT = 2;
// The real backend scans every 2 minutes; the mock does it when the counts are polled.
const BACKGROUND_SCAN_MS = 2 * 60 * 1000;

const alertTopicsOf = (store: MockStore) => (store.alertTopics ??= []);
// One sequence for alerts and topics is enough for the mock.
const nextAlertId = (store: MockStore) => (store.nextAlertId = (store.nextAlertId ?? 0) + 1);
const alertsOf = (store: MockStore) => (store.alerts ??= []);

function settingsOf(store: MockStore, projectId: string): StoredAlertSettings {
  store.alertSettings ??= {};
  return (store.alertSettings[projectId] ??= {
    enabled: false, prompted: false, topicsRefreshedAt: null, lastScanAt: null,
  });
}

const liveTopics = (store: MockStore, projectId: string) =>
  alertTopicsOf(store).filter((topic) => topic.projectId === projectId && !topic.removed);

const topicView = ({ id, label, query, source, minScore }: StoredAlertTopic): AlertTopicView =>
  ({ id, label, query, source, minScore });

function settingsView(store: MockStore, projectId: string): AlertSettingsView {
  const settings = settingsOf(store, projectId);
  return {
    projectId,
    enabled: settings.enabled,
    prompted: settings.prompted,
    topics: liveTopics(store, projectId).map(topicView),
    lastScanAt: settings.lastScanAt,
  };
}

const alertView = (alert: StoredAlert): AlertView => {
  const { dismissed: _dismissed, ...view } = alert;
  return view;
};

function findAlert(store: MockStore, alertId: number) {
  const alert = alertsOf(store).find((candidate) => candidate.id === alertId && !candidate.dismissed);
  if (!alert) throw notFound("Alert");
  return alert;
}

function validTopicLabel(label: string) {
  const trimmed = label.trim();
  if (!trimmed || trimmed.length > 80) throw new ApiError("Invalid topic label", 400);
  return trimmed;
}

// Lowercase without diacritics, so "școli" and "scoli" share a stem.
const normalize = (text: string) =>
  text.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

const stems = (text: string) =>
  new Set(normalize(text).split(/[^a-z0-9а-яё]+/).filter((word) => word.length >= 4).map((word) => word.slice(0, 5)));

function scoreDocument(query: string, document: FeedDocument) {
  const wanted = stems(query);
  if (wanted.size === 0) return 0;
  const found = stems(`${document.title} ${document.excerpt} ${document.category ?? ""}`);
  const hits = [...wanted].filter((stem) => found.has(stem)).length;
  return hits === 0 ? 0 : Math.min(0.95, 0.5 + 0.1 * hits);
}

function refreshTopics(store: MockStore, projectId: string) {
  const chatIds = new Set(store.chats.filter((chat) => chat.projectId === projectId).map((chat) => chat.id));
  const prompts = store.responses
    .filter((response) => chatIds.has(response.chatId) && response.prompt)
    .map((response) => response.prompt!);
  // Removed topics count as existing, so they are not re-created.
  const existing = new Set(
    alertTopicsOf(store).filter((topic) => topic.projectId === projectId).map((topic) => topic.label.toLowerCase()),
  );
  let added = 0;
  for (const rule of TOPIC_RULES) {
    if (added >= 4 || existing.has(rule.label.toLowerCase())) continue;
    if (!prompts.some((prompt) => rule.pattern.test(prompt))) continue;
    alertTopicsOf(store).push({
      id: nextAlertId(store),
      projectId, label: rule.label, query: rule.query, source: "AUTO", minScore: null, removed: false,
    });
    added += 1;
  }
  settingsOf(store, projectId).topicsRefreshedAt = now();
}

// Adds up to `limit` alerts for documents the project was never alerted about.
function scan(store: MockStore, projectId: string, limit: number) {
  const topics = liveTopics(store, projectId);
  settingsOf(store, projectId).lastScanAt = now();
  if (topics.length === 0) return 0;

  const seen = new Set(alertsOf(store).filter((alert) => alert.projectId === projectId).map((alert) => alert.documentId));
  const matches = DEMO_FEED.filter((document) => !seen.has(document.documentId))
    .map((document) => {
      const best = topics
        .map((topic) => ({ topic, score: scoreDocument(topic.query, document) }))
        .filter(({ topic, score }) => score > 0 && score >= (topic.minScore ?? DEFAULT_MIN_SCORE))
        .sort((a, b) => b.score - a.score)[0];
      return best ? { document, ...best } : null;
    })
    .filter((match) => match !== null)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);

  for (const { document, topic, score } of matches) {
    alertsOf(store).push({
      ...document,
      id: nextAlertId(store),
      projectId,
      topicId: topic.id,
      topicLabel: topic.label,
      score,
      createdAt: now(),
      readAt: null,
      dismissed: false,
    });
  }
  return matches.length;
}

// Stands in for the scheduled task: enabled projects get new alerts over time.
function backgroundScan(store: MockStore) {
  let changed = false;
  for (const project of projectsOf(store)) {
    const settings = store.alertSettings?.[project.id];
    if (!settings?.enabled) continue;
    const last = settings.lastScanAt ? Date.parse(settings.lastScanAt) : 0;
    if (Date.now() - last < BACKGROUND_SCAN_MS) continue;
    scan(store, project.id, BACKGROUND_SCAN_LIMIT);
    changed = true;
  }
  return changed;
}

const visibleAlerts = (store: MockStore) => alertsOf(store).filter((alert) => !alert.dismissed);

export async function getAlerts(query: AlertListQuery = {}): Promise<AlertView[]> {
  await wait(150);
  return visibleAlerts(load())
    .filter((alert) => !query.projectId || alert.projectId === query.projectId)
    .filter((alert) => !query.unreadOnly || !alert.readAt)
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt) || b.id - a.id)
    .slice(0, query.limit ?? 50)
    .map(alertView);
}

export async function getAlertUnreadCount(): Promise<AlertUnreadCountView> {
  await wait(80);
  const store = load();
  if (backgroundScan(store)) save(store);
  const byProject: Record<string, number> = {};
  for (const alert of visibleAlerts(store)) {
    if (!alert.readAt) byProject[alert.projectId] = (byProject[alert.projectId] ?? 0) + 1;
  }
  return { total: Object.values(byProject).reduce((sum, count) => sum + count, 0), byProject };
}

export async function markAlertRead(alertId: number): Promise<AlertView> {
  await wait(80);
  const store = load();
  const alert = findAlert(store, alertId);
  alert.readAt ??= now();
  save(store);
  return alertView(alert);
}

export async function markAllAlertsRead(projectId: string | null = null): Promise<{ updated: number }> {
  await wait(80);
  const store = load();
  let updated = 0;
  for (const alert of visibleAlerts(store)) {
    if (alert.readAt || (projectId && alert.projectId !== projectId)) continue;
    alert.readAt = now();
    updated += 1;
  }
  save(store);
  return { updated };
}

export async function markAlertNotRelevant(alertId: number): Promise<void> {
  await wait(80);
  const store = load();
  const alert = findAlert(store, alertId);
  alert.dismissed = true;
  alert.readAt ??= now();
  const topic = alertTopicsOf(store).find((candidate) => candidate.id === alert.topicId);
  if (topic) topic.minScore = Math.max(topic.minScore ?? 0, alert.score + 0.01);
  save(store);
}

export async function getAlertSettings(projectId: string): Promise<AlertSettingsView> {
  await wait(80);
  const store = load();
  findProject(store, projectId);
  return settingsView(store, projectId);
}

export async function updateAlertSettings(projectId: string, enabled: boolean): Promise<AlertSettingsView> {
  await wait(150);
  const store = load();
  findProject(store, projectId);
  const settings = settingsOf(store, projectId);
  const turnedOn = enabled && !settings.enabled;
  settings.enabled = enabled;
  settings.prompted = true;
  if (turnedOn) {
    if (liveTopics(store, projectId).length === 0) refreshTopics(store, projectId);
    scan(store, projectId, MANUAL_SCAN_LIMIT);
  }
  save(store);
  return settingsView(store, projectId);
}

export async function refreshAlertTopics(projectId: string): Promise<AlertSettingsView> {
  await wait(300);
  const store = load();
  findProject(store, projectId);
  refreshTopics(store, projectId);
  save(store);
  return settingsView(store, projectId);
}

export async function createAlertTopic(projectId: string, label: string): Promise<AlertTopicView> {
  await wait(100);
  const store = load();
  findProject(store, projectId);
  const trimmed = validTopicLabel(label);
  // Like the backend: an existing label returns the existing topic.
  const existing = liveTopics(store, projectId).find((topic) => topic.label.toLowerCase() === trimmed.toLowerCase());
  if (existing) return topicView(existing);
  const topic: StoredAlertTopic = {
    id: nextAlertId(store),
    projectId, label: trimmed, query: trimmed, source: "USER", minScore: null, removed: false,
  };
  alertTopicsOf(store).push(topic);
  save(store);
  return topicView(topic);
}

function findTopic(store: MockStore, projectId: string, topicId: number) {
  const topic = liveTopics(store, projectId).find((candidate) => candidate.id === topicId);
  if (!topic) throw notFound("Topic");
  return topic;
}

export async function updateAlertTopic(projectId: string, topicId: number, label: string): Promise<AlertTopicView> {
  await wait(100);
  const store = load();
  const topic = findTopic(store, projectId, topicId);
  topic.label = validTopicLabel(label);
  topic.query = topic.label;
  topic.source = "USER";
  save(store);
  return topicView(topic);
}

export async function deleteAlertTopic(projectId: string, topicId: number): Promise<void> {
  await wait(100);
  const store = load();
  const topic = findTopic(store, projectId, topicId);
  if (topic.source === "AUTO") topic.removed = true;
  else store.alertTopics = alertTopicsOf(store).filter((candidate) => candidate !== topic);
  save(store);
}

export async function scanProjectAlerts(projectId: string): Promise<AlertScanView> {
  await wait(400);
  const store = load();
  findProject(store, projectId);
  const hasTopics = liveTopics(store, projectId).length > 0;
  const created = scan(store, projectId, MANUAL_SCAN_LIMIT);
  save(store);
  return { created, matcher: hasTopics ? "lexical" : "none" };
}
