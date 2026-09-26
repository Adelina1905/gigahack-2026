import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { I18nContext, LOCALE_STORAGE_KEY, detectLocale } from "./context";
import { MESSAGES, type Locale } from "./messages";

function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(detectLocale);

  useEffect(() => {
    document.documentElement.lang = locale;
    document.title = MESSAGES[locale].meta.title;
  }, [locale]);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    try {
      localStorage.setItem(LOCALE_STORAGE_KEY, next);
    } catch {
      // Not remembered across visits, but the switch still applies now.
    }
  }, []);

  const value = useMemo(() => ({ locale, setLocale, t: MESSAGES[locale] }), [locale, setLocale]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export default I18nProvider;
