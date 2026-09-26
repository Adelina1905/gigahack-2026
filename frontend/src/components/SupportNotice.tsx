interface SupportNoticeProps {
  onDismiss: () => void;
}

const SUPPORT_NUMBER = "14 04";

function SupportNotice({ onDismiss }: SupportNoticeProps) {
  return (
    <div
      role="status"
      className="flex items-center gap-2.5 rounded-2xl border border-primary-200/60 bg-primary-50/70 py-2 pr-2 pl-3 text-sm text-primary-700 backdrop-blur-sm"
    >
      <svg viewBox="0 0 24 24" className="h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="9" />
        <path d="M12 11v5M12 8h.01" />
      </svg>
      <span className="flex-1">
        For more information, contact support at{" "}
        <a href={`tel:${SUPPORT_NUMBER.replace(/\s/g, "")}`} className="font-semibold whitespace-nowrap hover:underline">
          {SUPPORT_NUMBER}
        </a>
      </span>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss"
        className="shrink-0 rounded-full p-1 text-primary-400 transition-colors hover:bg-primary-100/70 hover:text-primary-700"
      >
        <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" aria-hidden="true">
          <path d="M6 6l12 12M18 6L6 18" />
        </svg>
      </button>
    </div>
  );
}

export default SupportNotice;
