import { useI18n } from "../i18n/context";
import type { SourceDocument } from "../types/chat";
import { safeHttpUrl } from "./sources/safeLink";

interface CitationPillsProps {
  sources: SourceDocument[];
  activeIndex?: number | null;
  controlsId: string;
  onSelect: (index: number, trigger: HTMLButtonElement) => void;
}

const getHostname = (link: string) => {
  if (!link) return "";
  try {
    return new URL(link).hostname.replace(/^www\./, "");
  } catch {
    return link;
  }
};

// Compact references under the answer text. Their details live in the shared
// source preview rather than being duplicated in hover cards and a full list.
function CitationPills({ sources, activeIndex = null, controlsId, onSelect }: CitationPillsProps) {
  const { t } = useI18n();
  if (sources.length === 0) return null;

  return (
    <ul aria-label={t.message.citedIn} className="mt-2 flex flex-wrap gap-1.5 whitespace-normal">
      {sources.map((source, i) => {
        const link = safeHttpUrl(source.link);
        const hostname = link ? getHostname(link) : "";
        return (
          <li key={`${source.documentId ?? source.link}-${i}`}>
            <button
              type="button"
              aria-haspopup="dialog"
              aria-expanded={activeIndex === i}
              aria-controls={controlsId}
              onClick={(event) => onSelect(i, event.currentTarget)}
              className={`inline-flex max-w-[12rem] cursor-pointer items-center gap-1 rounded-full border px-2 py-0.5 text-xs transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${
                activeIndex === i
                  ? "border-primary bg-primary text-text-inverted"
                  : "border-primary-100 bg-primary-50/70 text-primary-700 hover:border-primary-200 hover:bg-primary-100/70"
              }`}
            >
              <span className="font-semibold">{i + 1}</span>
              <span className="truncate">{hostname || source.title}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

export default CitationPills;
