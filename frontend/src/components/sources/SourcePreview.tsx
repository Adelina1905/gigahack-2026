import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useI18n } from "../../i18n/context";
import type { SourceDocument } from "../../types/chat";
import { safeHttpUrl } from "./safeLink";

interface SourcePreviewProps {
  id: string;
  sources: SourceDocument[];
  activeIndex: number;
  trigger: HTMLButtonElement | null;
  onSelect: (index: number) => void;
  onClose: () => void;
}

const DESKTOP_QUERY = "(min-width: 768px)";

const isDesktopViewport = () => {
  if (typeof window.matchMedia === "function") return window.matchMedia(DESKTOP_QUERY).matches;
  return window.innerWidth >= 768;
};

const getHostname = (link: string) => {
  try {
    return new URL(link).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
};

const formatDate = (iso: string, locale: string) => {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(locale, { year: "numeric", month: "short", day: "numeric" });
};

const focusableElements = (container: HTMLElement | null) =>
  Array.from(container?.querySelectorAll<HTMLElement>(
    'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
  ) ?? []).filter(element => !element.hasAttribute("hidden"));

function SourcePreview({ id, sources, activeIndex, trigger, onSelect, onClose }: SourcePreviewProps) {
  const { t } = useI18n();
  const titleId = useId();
  const panelRef = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  const triggerRef = useRef(trigger);
  const [desktop, setDesktop] = useState(isDesktopViewport);
  const source = sources[activeIndex];
  const link = safeHttpUrl(source?.link);
  const hostname = link ? getHostname(link) : "";
  const addedDate = source ? formatDate(source.added_date, t.meta.intl) : "";

  useEffect(() => { onCloseRef.current = onClose; });
  useEffect(() => { triggerRef.current = trigger; }, [trigger]);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const media = window.matchMedia(DESKTOP_QUERY);
    const update = () => setDesktop(media.matches);
    media.addEventListener?.("change", update);
    return () => media.removeEventListener?.("change", update);
  }, []);

  useEffect(() => {
    closeRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab" || isDesktopViewport()) return;
      const focusable = focusableElements(panelRef.current);
      if (focusable.length === 0) {
        event.preventDefault();
        panelRef.current?.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      if (triggerRef.current?.isConnected) triggerRef.current.focus();
    };
  }, []);

  useEffect(() => {
    if (desktop) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = previousOverflow; };
  }, [desktop]);

  if (!source) return null;

  return createPortal(
    <div className="pointer-events-none fixed inset-0 z-50">
      <button
        type="button"
        aria-hidden="true"
        tabIndex={-1}
        data-testid="source-preview-backdrop"
        onClick={onClose}
        className="pointer-events-auto absolute inset-0 bg-black/40 md:hidden"
      />
      <section
        ref={panelRef}
        id={id}
        role="dialog"
        aria-modal={desktop ? undefined : true}
        aria-labelledby={titleId}
        tabIndex={-1}
        className="pointer-events-auto absolute inset-x-0 bottom-0 flex max-h-[75dvh] flex-col overflow-hidden rounded-t-2xl border border-border bg-background shadow-2xl md:inset-y-0 md:right-0 md:left-auto md:max-h-none md:w-[min(28rem,calc(100vw-2rem))] md:rounded-none md:border-y-0 md:border-r-0"
      >
        <div className="flex shrink-0 items-start justify-between gap-4 border-b border-border px-5 py-4">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-wide text-primary">
              {t.message.sourcePosition(activeIndex + 1, sources.length)}
            </p>
            <h2 id={titleId} className="mt-1 break-words font-serif text-xl leading-tight text-text">
              {source.title}
            </h2>
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label={t.message.closeSources}
            className="shrink-0 rounded-sm p-2 text-text-muted hover:bg-background-secondary hover:text-text focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
              <path strokeLinecap="round" d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
          {source.exactQuote && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
                {t.message.supportingQuote}
              </p>
              <blockquote className="mt-2 break-words border-l-4 border-accent bg-background-secondary px-4 py-3 text-sm leading-relaxed text-text">
                {source.exactQuote}
              </blockquote>
            </div>
          )}

          <dl className={`${source.exactQuote ? "mt-5" : ""} space-y-3 text-sm`}>
            {hostname && (
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wide text-text-muted">{t.message.website}</dt>
                <dd className="mt-1 break-all text-text">{hostname}</dd>
              </div>
            )}
            {addedDate && (
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wide text-text-muted">{t.message.date}</dt>
                <dd className="mt-1 text-text">{addedDate}</dd>
              </div>
            )}
            {source.documentId && (
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wide text-text-muted">{t.message.documentId}</dt>
                <dd className="mt-1 break-all text-text">{source.documentId}</dd>
              </div>
            )}
          </dl>

          {link ? (
            <a
              href={link}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-6 inline-flex items-center gap-2 rounded-sm bg-primary px-4 py-2.5 text-sm font-semibold text-text-inverted hover:bg-primary-dark focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            >
              {t.message.openSource}
              <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
              </svg>
            </a>
          ) : (
            <p className="mt-6 text-sm text-text-subtle">{t.message.noLink}</p>
          )}
        </div>

        {sources.length > 1 && (
          <div className="flex shrink-0 items-center justify-between gap-3 border-t border-border px-5 py-3">
            <button
              type="button"
              disabled={activeIndex === 0}
              onClick={() => onSelect(activeIndex - 1)}
              className="rounded-sm px-3 py-2 text-sm font-medium text-primary hover:bg-primary-50 disabled:cursor-not-allowed disabled:opacity-40"
            >
              ← {t.message.previousSource}
            </button>
            <button
              type="button"
              disabled={activeIndex === sources.length - 1}
              onClick={() => onSelect(activeIndex + 1)}
              className="rounded-sm px-3 py-2 text-sm font-medium text-primary hover:bg-primary-50 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {t.message.nextSource} →
            </button>
          </div>
        )}
      </section>
    </div>,
    document.body,
  );
}

export default SourcePreview;
