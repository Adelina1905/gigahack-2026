import type { SourceDocument } from "../../types/chat";

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

const formatDate = (iso: string) => {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString([], { year: "numeric", month: "short", day: "numeric" });
};

function SourceItem({ source, index }: SourceItemProps) {
  const hostname = getHostname(source.link);
  const addedDate = formatDate(source.added_date);

  const content = (
    <>
      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary-50 text-xs font-semibold text-primary">
        {index + 1}
      </span>

      <span className="flex min-w-0 flex-1 flex-col">
        <span className={`truncate text-sm font-medium text-primary${source.link ? " hover:underline" : ""}`}>
          {source.title}
        </span>
        {(hostname || addedDate) && (
          <span className="truncate text-xs text-text-subtle">
            {hostname}
            {hostname && addedDate && " · "}
            {addedDate && `Added ${addedDate}`}
          </span>
        )}
      </span>
    </>
  );

  // Sources without a URL are shown as plain text rather than a broken link.
  if (!source.link) {
    return (
      <li title={source.title} className="flex items-center gap-3 rounded-lg px-2 py-1.5">
        {content}
      </li>
    );
  }

  return (
    <li>
      <a
        href={source.link}
        target="_blank"
        rel="noopener noreferrer"
        title={source.title}
        className="flex items-center gap-3 rounded-lg px-2 py-1.5 transition-colors hover:bg-background-secondary focus-visible:bg-background-secondary focus-visible:outline-none"
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
