import type { ReactNode } from "react";
import { useI18n } from "../i18n/context";
import { CityEmblem } from "./brand/Landmarks";
import LanguageSwitcher from "./LanguageSwitcher";

interface SiteHeaderProps {
  // Opens the chat-history drawer; the button only shows below md.
  onOpenMenu: () => void;
  // Controls at the right end of the masthead, such as the alerts bell.
  actions?: ReactNode;
}

// The utility strip and white masthead follow the chisinau.md header; the strip also shows
// on phones so the language picker has a quiet home there too.
function SiteHeader({ onOpenMenu, actions }: SiteHeaderProps) {
  const { t } = useI18n();

  return (
    <header className="shrink-0">
      <div className="bg-primary-dark text-xs text-white/75">
        <div className="flex h-8 items-center gap-4 px-3 md:px-6">
          <span className="hidden min-w-0 truncate text-white/85 md:block">{t.header.tagline}</span>
          <div className="ml-auto flex shrink-0 items-center gap-2">
            <a
              href={t.meta.officialSiteUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 underline-offset-2 transition-colors hover:text-white hover:underline"
            >
              <span className="hidden sm:inline">{t.header.officialSite}</span>
              <span className="sm:hidden">chisinau.md</span>
              <svg viewBox="0 0 24 24" className="h-3 w-3 opacity-70" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
              </svg>
            </a>
            <span aria-hidden="true" className="h-3.5 w-px bg-white/20" />
            <LanguageSwitcher />
          </div>
        </div>
      </div>

      <div className="flex h-16 items-center gap-3 border-b border-border bg-background px-3 md:px-6">
        <button
          type="button"
          onClick={onOpenMenu}
          aria-label={t.header.openMenu}
          className="rounded-sm p-2 text-text-muted hover:bg-background-secondary md:hidden"
        >
          <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
            <path d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>

        <div className="flex min-w-0 items-center gap-2.5 sm:gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-sm bg-primary text-white">
            <CityEmblem className="h-8 w-8" />
          </span>
          <span className="font-serif text-[13px] font-semibold uppercase leading-[1.15] tracking-[0.05em] text-[#333] sm:text-[15px] md:text-base">
            {t.header.wordmark.map((line) => (
              <span key={line} className="block">
                {line}
              </span>
            ))}
          </span>
        </div>

        {actions && <div className="ml-auto flex shrink-0 items-center gap-1">{actions}</div>}
      </div>
    </header>
  );
}

export default SiteHeader;
