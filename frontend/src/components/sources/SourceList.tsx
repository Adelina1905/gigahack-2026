import type { SourceDocument } from "../../types/chat";
import SourceItem from "./SourceItem";

interface SourceListProps {
  sources: SourceDocument[];
}

function SourceList({ sources }: SourceListProps) {
  if (sources.length === 0) return null;

  return (
    <div className="mt-3 border-t border-border pt-2 whitespace-normal">
      <p className="px-2 pb-1 text-xs font-semibold uppercase tracking-wide text-text-subtle">
        Sources ({sources.length})
      </p>
      <ul className="flex flex-col">
        {sources.map((source, i) => (
          <SourceItem key={`${source.link}-${i}`} source={source} index={i} />
        ))}
      </ul>
    </div>
  );
}

export default SourceList;
