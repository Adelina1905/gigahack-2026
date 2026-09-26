import { useI18n } from "../../i18n/context";
import type { SourceDocument } from "../../types/chat";
import { safeHttpUrl } from "./safeLink";

interface SourceItemProps {
  source: SourceDocument;
  index: number;
}

const getHostname = (link: string) => {
  if (!link) return "";
  try {
    return new URL(link).hostname.replace(/^www\./, "");
  } catch {
    return link;
  }
};

const formatDate = (iso: string, locale: string) => {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(locale, { year: "numeric", month: "short", day: "numeric" });
};

function SourceItem({ source, index }: SourceItemProps) {
  const { t } = useI18n();
  const link = safeHttpUrl(source.link);
  const hostname = link ? getHostname(link) : "";
  const addedDate = formatDate(source.added_date, t.meta.intl);

  const content = (
    <>
      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-sm bg-primary text-xs font-semibold text-text-inverted">
        {index + 1}
      </span>

      <span className="flex min-w-0 flex-1 flex-col">
        <span className={`truncate text-sm font-medium text-primary${link ? " hover:underline" : ""}`}>
          {source.title}
        </span>
        {source.exactQuote && <span className="mt-1 text-xs text-text-muted">{source.exactQuote}</span>}
        {(hostname || addedDate) && (
          <span className="truncate text-xs text-text-subtle">
            {hostname}
            {hostname && addedDate && " · "}
            {addedDate && t.message.added(addedDate)}
          </span>
        )}
      </span>
    </>
  );

  // Sources without a URL are shown as plain text rather than a broken link.
  if (!link) {
    return (
      <li title={source.title} className="flex items-center gap-3 rounded-sm px-2 py-1.5">
        {content}
      </li>
    );
  }

  return (
    <li>
      <a
        href={link}
        target="_blank"
        rel="noopener noreferrer"
        title={source.title}
        className="flex items-center gap-3 rounded-sm px-2 py-1.5 transition-colors hover:bg-primary-50 focus-visible:bg-primary-50 focus-visible:outline-none"
      >
        {content}

        <svg viewBox="0 0 24 24" className="h-4 w-4 shrink-0 text-text-subtle" fill="none" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
        </svg>
      </a>
    </li>
  );
}

export default SourceItem;
