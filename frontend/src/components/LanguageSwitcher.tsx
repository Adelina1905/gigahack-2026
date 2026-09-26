import { useEffect, useRef, useState } from "react";
import { useI18n } from "../i18n/context";
import { LOCALES, MESSAGES } from "../i18n/messages";

// The quiet "Română ⌄" picker in the dark top strip, as on chisinau.md.
// The menu stays mounted so it can fade in and out.
function LanguageSwitcher() {
  const { locale, setLocale, t } = useI18n();
  const [isOpen, setIsOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    const closeOutside = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setIsOpen(false);
    };
    const closeOnEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsOpen(false);
    };
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [isOpen]);

  const current = MESSAGES[locale].meta;

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setIsOpen((open) => !open)}
        aria-expanded={isOpen}
        aria-haspopup="true"
        aria-label={`${t.header.language}: ${current.name}`}
        className="flex items-center gap-1.5 rounded-sm px-1.5 py-1 text-white/75 transition-colors hover:text-white focus-visible:text-white focus-visible:outline-1 focus-visible:outline-white/40 aria-expanded:text-white"
      >
        <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 opacity-70" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="9" />
          <path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18" />
        </svg>
        {current.name}
        <svg viewBox="0 0 24 24" className={`h-3 w-3 opacity-70 transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`} fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round">
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>

      <ul
        className={`absolute top-full right-0 z-50 mt-1.5 min-w-40 rounded-sm border border-white/10 bg-primary-dark py-1 shadow-xl shadow-black/20 transition duration-200 ease-out ${
          isOpen ? "visible translate-y-0 opacity-100" : "invisible -translate-y-1 opacity-0"
        }`}
      >
        {LOCALES.map((code) => {
          const isCurrent = code === locale;
          return (
            <li key={code}>
              <button
                type="button"
                lang={code}
                aria-current={isCurrent ? "true" : undefined}
                onClick={() => {
                  setLocale(code);
                  setIsOpen(false);
                }}
                className={`flex w-full items-center justify-between gap-4 px-3 py-2 text-left text-[13px] transition-colors hover:bg-white/10 hover:text-white ${
                  isCurrent ? "font-semibold text-white" : "text-white/70"
                }`}
              >
                {MESSAGES[code].meta.name}
                {isCurrent && (
                  <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 text-accent" fill="none" stroke="currentColor" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round">
                    <path d="m5 12 5 5 9-10" />
                  </svg>
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export default LanguageSwitcher;
