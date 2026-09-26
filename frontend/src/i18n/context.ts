import { createContext, useContext } from "react";
import { DEFAULT_LOCALE, LOCALES, type Locale, type Messages } from "./messages";

export const LOCALE_STORAGE_KEY = "smart-city-locale";

export interface I18nValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: Messages;
}

export const I18nContext = createContext<I18nValue | null>(null);

export function useI18n(): I18nValue {
  const value = useContext(I18nContext);
  if (!value) throw new Error("useI18n must be used inside <I18nProvider>");
  return value;
}

const isLocale = (value: unknown): value is Locale => LOCALES.includes(value as Locale);

// A language the visitor picked wins. Otherwise use the browser's preference list,
// which is what it sends as Accept-Language, and fall back to Romanian.
export function detectLocale(): Locale {
  try {
    const saved = localStorage.getItem(LOCALE_STORAGE_KEY);
    if (isLocale(saved)) return saved;
  } catch {
    // Storage can be blocked; detection still works without it.
  }

  for (const tag of navigator.languages ?? [navigator.language]) {
    const base = tag.toLowerCase().split("-")[0];
    // "mo" is the retired code for Moldovan, i.e. Romanian.
    if (base === "mo") return "ro";
    if (isLocale(base)) return base;
  }
  return DEFAULT_LOCALE;
}
