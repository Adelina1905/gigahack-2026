// Heuristic: the backend doesn't say whether a reply actually answered the question,
// so we look for the phrases the assistant uses when it can't (RO, RU and EN).
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
