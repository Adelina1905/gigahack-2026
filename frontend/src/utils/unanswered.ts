import { NOT_FOUND_REASONS, type ChatMessage, type NotFoundReason } from "../types/chat";

// Heuristic for LLM fallback and older replies, which don't say whether they answered
// the question: we look for the phrases the assistant uses when it can't (RO, RU and EN).
const PHRASES = [
  // Romanian
  "nu a fost gasit",
  "nu am gasit",
  "nu am informatii",
  "nu dispun de informatii",
  "nu detin informatii",
  "nu am acces la informatii",
  "nu am date",
  "nu pot raspunde",
  "nu pot oferi informatii",
  "nu pot furniza informatii",
  "nu sunt sigur",
  // Russian
  "не найден",
  "нет информации",
  "нет данных",
  "нет официальной информации",
  "не располагаю",
  "не могу ответить",
  "не могу предоставить",
  "не уверен",
  // English
  "i don't have",
  "i do not have",
  "i can't answer",
  "i cannot answer",
  "unable to answer",
  "i'm not sure",
  "i am not sure",
  "no official information",
  "not found in",
].map(normalize);

// Lowercase, drop diacritics (ș/ş, ț/ţ, ă, î…) and unify apostrophes so wording variants match.
function normalize(text: string) {
  return text
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[‘’]/g, "'");
}

export function isUnanswered(text: string) {
  const normalized = normalize(text);
  return PHRASES.some((phrase) => normalized.includes(phrase));
}

// Replies the backend flags as NOT_FOUND carry no answer whatever their wording.
// Returns the reason to explain, defaulting to "nothing relevant found".
export function notFoundReason(message: Pick<ChatMessage, "replyStatus" | "reason">): NotFoundReason | null {
  const reason = message.reason && (NOT_FOUND_REASONS as readonly string[]).includes(message.reason)
    ? message.reason as NotFoundReason : null;
  if (reason) return reason;
  return message.replyStatus === "NOT_FOUND" ? "NO_RELEVANT_EVIDENCE" : null;
}
