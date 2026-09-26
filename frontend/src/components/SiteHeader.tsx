import { CityEmblem } from "./brand/Landmarks";

interface SiteHeaderProps {
  // Opens the chat-history drawer; the button only shows below md.
  onOpenMenu: () => void;
}

// The utility strip and white masthead follow the chisinau.md header.
function SiteHeader({ onOpenMenu }: SiteHeaderProps) {
  return (
    <header className="shrink-0">
      <div className="hidden bg-primary-dark text-xs text-white/85 md:block">
        <div className="flex h-8 items-center justify-between px-6">
          <span>Municipal Q&amp;A assistant · answers cite official documents of Chișinău</span>
          <a
            href="https://www.chisinau.md/"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 underline-offset-2 hover:text-white hover:underline"
          >
            Official site: chisinau.md
            <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
            </svg>
          </a>
        </div>
      </div>

      <div className="flex h-16 items-center gap-3 border-b border-border bg-background px-3 md:px-6">
        <button
          type="button"
          onClick={onOpenMenu}
          aria-label="Open chat history"
          className="rounded-sm p-2 text-text-muted hover:bg-background-secondary md:hidden"
        >
          <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
            <path d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>

        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-sm bg-primary text-white">
            <CityEmblem className="h-8 w-8" />
          </span>
          <span className="font-serif text-[15px] font-semibold uppercase leading-[1.15] tracking-[0.06em] text-[#333] md:text-base">
            <span className="block">Asistent Municipal</span>
            <span className="block">Chișinău</span>
          </span>
        </div>
      </div>
    </header>
  );
}

export default SiteHeader;
