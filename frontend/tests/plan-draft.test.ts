import { describe, expect, it } from "vitest";
import { MESSAGES } from "../src/i18n/messages";
import { draftPlanFromChat, PLAN_MAX_LENGTH, truncateWords } from "../src/trackers/planDraft";
import type { ChatMessage } from "../src/types/chat";

const ro = MESSAGES.ro.trackers.suggestedTopics;
const ru = MESSAGES.ru.trackers.suggestedTopics;
const en = MESSAGES.en.trackers.suggestedTopics;

const user = (content: string): Pick<ChatMessage, "role" | "content"> => ({ role: "user", content });
const assistant = (content: string): Pick<ChatMessage, "role" | "content"> => ({ role: "assistant", content });

describe("draftPlanFromChat", () => {
  it("keeps the topic lists parallel across locales", () => {
    expect(ru).toHaveLength(ro.length);
    expect(en).toHaveLength(ro.length);
    expect(ro).toHaveLength(6);
  });

  it("drafts a Romanian plan with street, number and topics", () => {
    const draft = draftPlanFromChat([
      user("  Vreau să deschid o cafenea   pe strada Ștefan cel Mare și Sfânt 12. Ce autorizații îmi trebuie?  "),
      assistant("Aveți nevoie de o autorizație de funcționare. Verificați și locurile de parcare din zonă."),
      user("Și dacă pun o terasă?"),
    ], ro);

    expect(draft.plan).toBe("Vreau să deschid o cafenea pe strada Ștefan cel Mare și Sfânt 12. Ce autorizații îmi trebuie?");
    expect(draft.location).toBe("strada Ștefan cel Mare și Sfânt 12");
    expect(draft.topics).toEqual(["Autorizații comerciale", "Parcare"]);
  });

  it("accepts cedilla and missing diacritics and adds the sector", () => {
    expect(draftPlanFromChat([user("Deschid un magazin pe şos. Hânceşti 45, sectorul Botanica")], ro).location)
      .toBe("şos. Hânceşti 45, sectorul Botanica");
    expect(draftPlanFromChat([user("magazin pe sos. Hincesti nr. 45")], ro).location)
      .toBe("sos. Hincesti nr. 45");
    expect(draftPlanFromChat([user("Organizez un concert in Piata Marii Adunari Nationale")], ro).location)
      .toBe("Piata Marii Adunari Nationale");
    expect(draftPlanFromChat([user("o brutărie în sectorul Rîșcani")], ro).location).toBe("sectorul Rîșcani");
    expect(draftPlanFromChat([user("o brutărie în sectorul Rascani")], ro).location).toBe("sectorul Rascani");
    expect(draftPlanFromChat([user("pe bd. Dacia 20/1 vreau o cafenea")], ro).location).toBe("bd. Dacia 20/1");
    expect(draftPlanFromChat([user("pe str. dacia 5 vreau o cafenea")], ro).location).toBe("str. dacia 5");
  });

  it("drafts a Russian plan and returns topics in the current locale", () => {
    const messages = [
      user("Хочу открыть кофейню на ул. Штефан чел Маре 64, будет ли отключение воды?"),
      assistant("Проверьте график отключений и остановки троллейбусов рядом."),
    ];

    const draft = draftPlanFromChat(messages, ru);
    expect(draft.location).toBe("ул. Штефан чел Маре 64");
    expect(draft.topics).toEqual(["Коммерческие разрешения", "Общественный транспорт", "Отключения коммунальных услуг"]);
    expect(draftPlanFromChat(messages, en).topics).toEqual(["Commercial permits", "Public transport", "Utility interruptions"]);
  });

  it("finds Russian sectors and boulevards", () => {
    expect(draftPlanFromChat([user("Ремонт дороги в секторе Буюкань")], ru)).toMatchObject({
      location: "секторе Буюкань",
      topics: ["Работы и доступ"],
    });
    expect(draftPlanFromChat([user("Парковка на бул. Дачия, д. 3")], ru)).toMatchObject({
      location: "бул. Дачия, д. 3",
      topics: ["Парковка"],
    });
  });

  it("falls back to the assistant's text for the location", () => {
    const draft = draftPlanFromChat([
      user("Unde pot organiza un festival?"),
      assistant("Evenimentele publice se aprobă pentru Piața Marii Adunări Naționale."),
    ], ro);
    expect(draft.location).toBe("Piața Marii Adunări Naționale");
    expect(draft.topics).toEqual(["Evenimente publice"]);
  });

  it("returns empty fields when nothing matches", () => {
    expect(draftPlanFromChat([user("Salut, ce mai faci?"), assistant("Bine, cu ce vă pot ajuta?")], ro))
      .toEqual({ plan: "Salut, ce mai faci?", location: "", topics: [] });
    expect(draftPlanFromChat([], ro)).toEqual({ plan: "", location: "", topics: [] });
    // Words that only contain a keyword, or "pr" without a dot, do not count.
    expect(draftPlanFromChat([user("Am un program pr Dacia și accesez site-ul")], ro))
      .toMatchObject({ location: "", topics: [] });
  });

  it("caps a long first message on a word boundary", () => {
    const long = `${"Deschid o cafenea mare ".repeat(30)}final`;
    const { plan } = draftPlanFromChat([user(long)], ro);
    expect(plan.length).toBeLessThanOrEqual(PLAN_MAX_LENGTH);
    expect(plan.endsWith("…")).toBe(true);
    expect(long.startsWith(plan.slice(0, -1))).toBe(true);
    expect(truncateWords("scurt", 10)).toBe("scurt");
  });
});
