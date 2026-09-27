import { useI18n } from "../../i18n/context";
import type { SourceDocument } from "../../types/chat";

// The year of a "YYYY-MM-DD" publication date, or null when it is missing.
const yearOf = (date: string | null | undefined) => /^(\d{4})/.exec(date ?? "")?.[1] ?? null;

// Marks a source that is older than the newest document found on the topic.
function OlderDocumentBadge({ source, className = "" }: { source: SourceDocument; className?: string }) {
  const { t } = useI18n();
  if (!source.outdated) return null;

  return (
    <span className={`inline-flex shrink-0 items-center rounded-sm border border-accent-dark/40 bg-accent/20 px-1.5 py-px text-[11px] font-medium text-text-muted ${className}`}>
      {t.message.olderDocument(yearOf(source.publishedDate))}
    </span>
  );
}

export default OlderDocumentBadge;
