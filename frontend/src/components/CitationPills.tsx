import { useI18n } from "../i18n/context";
import type { SourceDocument } from "../types/chat";
import { safeHttpUrl } from "./sources/safeLink";

interface CitationPillsProps {
  sources: SourceDocument[];
}

const getHostname = (link: string) => {
  if (!link) return "";
  try {
    return new URL(link).hostname.replace(/^www\./, "");
  } catch {
    return link;
  }
};

// Compact references under the answer text, numbered like the Sources list below it.
// Hovering or focusing a pill opens a small card linking to the document.
function CitationPills({ sources }: CitationPillsProps) {
  const { t } = useI18n();
  if (sources.length === 0) return null;

  return (
    <ul aria-label={t.message.citedIn} className="mt-2 flex flex-wrap gap-1.5 whitespace-normal">
      {sources.map((source, i) => {
        const link = safeHttpUrl(source.link);
        const hostname = link ? getHostname(link) : "";
        return (
          <li key={`${source.link}-${i}`} className="group/pill relative">
            <span
              tabIndex={0}
              className="inline-flex max-w-[12rem] cursor-default items-center gap-1 rounded-full border border-primary-100 bg-primary-50/70 px-2 py-0.5 text-xs text-primary-700 transition-colors group-hover/pill:border-primary-200 group-hover/pill:bg-primary-100/70 focus-visible:border-primary-200 focus-visible:outline-none"
            >
              <span className="font-semibold">{i + 1}</span>
              <span className="truncate">{hostname || source.title}</span>
            </span>

            {/* pb-2 bridges the gap so the pointer can move from the pill onto the card. */}
            <div className="invisible absolute bottom-full left-0 z-20 pb-2 opacity-0 transition-opacity duration-150 group-focus-within/pill:visible group-focus-within/pill:opacity-100 group-hover/pill:visible group-hover/pill:opacity-100">
              <div className="w-72 max-w-[calc(100vw-2rem)] rounded-xl border border-border bg-background p-3 shadow-lg">
                <p className="line-clamp-2 text-sm font-medium text-text">{source.title}</p>
                {link ? (
                  <a
                    href={link}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-1.5 flex items-center gap-1.5 text-xs font-medium text-primary hover:underline"
                  >
                    <span className="truncate">{link}</span>
                    <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 shrink-0" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                      <path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
                    </svg>
                  </a>
                ) : (
                  <p className="mt-1.5 text-xs text-text-subtle">{t.message.noLink}</p>
                )}
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export default CitationPills;
