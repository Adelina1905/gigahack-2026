import type { ChatMessage } from "../types/chat";

// A first guess at the plan wizard's answers, read from the chat without any
// server call. Every field can be empty; the wizard asks for what is missing.
export interface PlanDraft {
  plan: string;
  location: string;
  topics: string[];
}

export const PLAN_MAX_LENGTH = 300;

const collapse = (text: string) => text.replace(/\s+/g, " ").trim();

// Caps text on a word boundary, adding an ellipsis when it was cut.
export function truncateWords(text: string, max: number): string {
  const clean = collapse(text);
  if (clean.length <= max) return clean;
  const cut = clean.slice(0, max - 1);
  const lastSpace = cut.lastIndexOf(" ");
  const head = lastSpace > max / 2 ? cut.slice(0, lastSpace) : cut;
  return `${head.replace(/[\s,.;:!?-]+$/, "")}…`;
}

// Lowercase without diacritics, so ș/ş, ț/ţ, ă, â, î and ё all match their
// plain letters.
export const foldText = (text: string) => text.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();

// Letters that users type interchangeably: comma and cedilla forms, and the
// Romanian letters written without diacritics.
const VARIANTS = ["sșş", "tțţ", "aăâ", "iî"];

// Builds a case-insensitive pattern for a literal word without the `i` flag,
// because `i` together with `u` would make \p{Lu} match lowercase letters.
// Diacritic variants of s, t, a and i match each other.
const spell = (word: string) =>
  [...word].map((char) => {
    const lower = char.toLowerCase();
    const group = VARIANTS.find((letters) => letters.includes(lower)) ?? lower;
    const letters = [...group].flatMap((letter) => [letter, letter.toUpperCase()]);
    if (letters.length === 2 && letters[0] === letters[1]) return char === "." ? "\\." : char;
    return `[${letters.join("")}]`;
  }).join("");

const STREET_PREFIXES = [
  // Romanian
  "strada", "str", "bulevardul", "bd", "bld", "șoseaua", "șos", "prospectul", "pr-t", "piața",
  // Russian
  "улица", "ул", "бульвар", "бул", "проспект", "пр-т", "шоссе", "площадь",
].map(spell);
// "pr." and "пл." are only prefixes with the dot; bare "pr" is too ambiguous.
const DOTTED_PREFIXES = ["pr", "пр", "пл"].map(spell);

const LETTER = "\\p{L}";
const NOT_WORD_BEFORE = `(?<![${LETTER}\\d])`;
const PREFIX = `(?:(?:${STREET_PREFIXES.join("|")})(?:\\.\\s*|\\s+)|(?:${DOTTED_PREFIXES.join("|")})\\.\\s*)`;
// Street names are capitalised words ("Ștefan cel Mare și Sfânt", "31 August
// 1989", "Штефан чел Маре"), joined by the usual lowercase connectors.
const NAME_WORD = `[\\p{Lu}\\d][${LETTER}\\d'’/-]*`;
const CONNECTOR = "(?:cel|și|şi|si|lui|de|din|al|a|чел|и|луй)";
const CAPITALISED_NAME = `${NAME_WORD}(?:\\s+(?:${CONNECTOR}\\s+)*${NAME_WORD}){0,4}`;
// A lowercase name only counts when a house number follows ("str. dacia 5").
const HOUSE_NUMBER = `(?:${spell("nr")}\\.?\\s*|${spell("д")}\\.\\s*)?\\d+${LETTER}?(?:\\/\\d+)?`;
const LOWERCASE_NAME = `[${LETTER}][${LETTER}'’-]+\\s+${HOUSE_NUMBER}`;
const TRAILING_NUMBER = `(?:,?\\s*(?:${spell("nr")}|${spell("д")})\\.?\\s*\\d+${LETTER}?(?:\\/\\d+)?|,\\s*\\d+${LETTER}?(?:\\/\\d+)?(?=\\s*(?:$|[,.;:!?)])))?`;
const STREET_PATTERN = new RegExp(
  `${NOT_WORD_BEFORE}${PREFIX}(?:${CAPITALISED_NAME}|${LOWERCASE_NAME})${TRAILING_NUMBER}`,
  "u",
);

const SECTOR_NAMES = [
  ...["Botanica", "Buiucani", "Centru", "Ciocana", "Râșcani", "Rîșcani"].map(spell),
  // Russian names, with their usual case endings.
  "[Бб]отаник[аеиу]", "[Бб]уюкан[ьиы]", "[Цц]ентр[аеу]?", "[Чч]екан(?:ы|ах|ам)", "[Рр]ышкановк[аеиу]",
];
const SECTOR_PATTERN = new RegExp(
  `${NOT_WORD_BEFORE}(?:${spell("sectorul")}|${spell("sector")}|${spell("сектор")}[аеу]?)\\s+(?:${SECTOR_NAMES.join("|")})(?![${LETTER}])`,
  "u",
);

function locationIn(text: string): string {
  const street = STREET_PATTERN.exec(text)?.[0].trim().replace(/[\s,]+$/, "") ?? "";
  const sector = SECTOR_PATTERN.exec(text)?.[0].trim() ?? "";
  if (street && sector && !street.includes(sector)) return `${street}, ${sector}`;
  return street || sector;
}

// Keyword lists per suggested topic, in the order of `t.trackers.suggestedTopics`
// (the same in every locale). Keywords are folded like the text; `*` is any
// word ending, and a keyword must start and end on a word boundary.
const TOPIC_KEYWORDS: readonly (readonly string[])[] = [
  // Commercial permits
  [
    "autorizati*", "autorizare*", "licent*", "aviz*", "patent*", "afacer*", "comert*", "comercial*",
    "cafenea*", "cafenele*", "restaurant*", "magazin*", "terasa", "terase*", "antreprenor*",
    "разрешени*", "лицензи*", "патент*", "бизнес*", "торгов*", "коммерческ*", "кафе", "кофейн*",
    "ресторан*", "магазин*", "террас*", "предприним*",
    "permit*", "licen*", "business*", "commercial", "cafe*", "coffee shop*", "restaurant*", "shop*",
    "store*", "terrace*",
  ],
  // Works and access
  [
    "lucrari*", "lucrarile*", "reparati*", "reparatie*", "santier*", "reabilitar*", "asfalt*",
    "inchider*", "blocat*", "acces", "accesul", "trotuar*", "constructi*", "ocolire*",
    "ремонт*", "дорожн* работ*", "строительн* работ*", "строительств*", "перекрыт*", "реконструкц*",
    "доступ*", "объезд*", "тротуар*", "асфальт*",
    "road work*", "roadwork*", "construction", "repair*", "closure*", "access", "detour*",
    "sidewalk*", "pavement*",
  ],
  // Public transport
  [
    "transport* public*", "transport* in comun", "troleibuz*", "autobuz*", "microbuz*", "rutiera",
    "rutiere", "maxi-taxi", "statie", "statia", "statii", "statiei", "statiile",
    "общественн* транспорт*", "транспорт*", "троллейбус*", "автобус*", "маршрутк*", "остановк*",
    "public transport*", "transit", "bus", "buses", "bus stop*", "trolleybus*", "minibus*",
  ],
  // Parking
  [
    "parcar*", "parcat*", "parcheaz*", "parchez*",
    "парковк*", "парковочн*", "стоянк*", "припарков*",
    "parking", "car park*",
  ],
  // Utility interruptions
  [
    "intrerup*", "deconect*", "apa", "apei", "apa calda", "gaz", "gazul", "gaze", "gazului",
    "energi* electric*", "electricitat*", "curentul electric", "canalizar*", "termoficar*",
    "incalzir*", "utilitat*",
    "отключени*", "отключ*", "электричеств*", "электроэнерги*", "газ", "газа", "газоснабжени*",
    "водоснабжени*", "горяч* вод*", "вода", "воды", "отоплени*", "канализац*", "коммунальн*",
    "outage*", "power cut*", "water supply", "gas", "electricity", "heating", "interruption*",
    "utilit*",
  ],
  // Public events
  [
    "eveniment*", "festival*", "concert*", "targ*", "manifestar*", "sarbator*", "hram*",
    "мероприяти*", "фестивал*", "концерт*", "ярмарк*", "праздник*",
    "event", "events", "festival*", "concert*", "fairs", "street fair*", "celebration*",
  ],
];

const keywordPattern = (keyword: string) => {
  const body = foldText(keyword)
    .split(/\s+/)
    .map((word) => word.replace(/[.*+?^${}()|[\]\\]/g, (char) => char === "*" ? `[${LETTER}]*` : `\\${char}`))
    .join("\\s+");
  return new RegExp(`${NOT_WORD_BEFORE}${body}(?![${LETTER}\\d])`, "u");
};

const TOPIC_PATTERNS = TOPIC_KEYWORDS.map((keywords) => keywords.map(keywordPattern));

type DraftMessage = Pick<ChatMessage, "role" | "content">;

// `topicLabels` is `t.trackers.suggestedTopics` for the current locale, so the
// topics come back as the labels the wizard shows.
export function draftPlanFromChat(messages: readonly DraftMessage[], topicLabels: readonly string[]): PlanDraft {
  const userTexts = messages.filter((message) => message.role === "user").map((message) => message.content);
  const assistantTexts = messages.filter((message) => message.role === "assistant").map((message) => message.content);

  const firstPrompt = userTexts.find((text) => text.trim()) ?? "";
  const plan = truncateWords(firstPrompt, PLAN_MAX_LENGTH);

  let location = "";
  for (const text of [...userTexts, ...assistantTexts]) {
    location = locationIn(text);
    if (location) break;
  }

  const conversation = foldText([...userTexts, ...assistantTexts].join("\n"));
  const topics = topicLabels.filter((_, index) =>
    TOPIC_PATTERNS[index]?.some((pattern) => pattern.test(conversation)));

  return { plan, location, topics };
}
