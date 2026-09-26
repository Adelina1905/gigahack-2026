import { useCallback, useEffect, useId, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { createPortal } from "react-dom";
import { api } from "../../api";
import type { SourcePreviewView, SourceSectionView } from "../../api/types";
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

const DESKTOP_QUERY = "(min-width: 1024px)";
const PAGE_SIZE = 40;
const MIN_WIDTH = 360;
const DEFAULT_WIDTH = 440;
const previewCache = new Map<string, SourcePreviewView>();

const isDesktopViewport = () => typeof window.matchMedia === "function"
  ? window.matchMedia(DESKTOP_QUERY).matches
  : window.innerWidth >= 1024;

const getHostname = (link: string) => {
  try { return new URL(link).hostname.replace(/^www\./, ""); } catch { return ""; }
};

const formatDate = (iso: string, locale: string) => {
  if (!iso) return "";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString(locale, { year: "numeric", month: "short", day: "numeric" });
};

const focusableElements = (container: HTMLElement | null) =>
  Array.from(container?.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])') ?? [])
    .filter(element => !element.hasAttribute("hidden"));

const mergePreview = (current: SourcePreviewView | null, incoming: SourcePreviewView) => {
  if (!current || current.documentId !== incoming.documentId || current.versionId !== incoming.versionId) return incoming;
  const sections = new Map<number, SourceSectionView>();
  [...current.sections, ...incoming.sections].forEach(section => sections.set(section.order, section));
  return {
    ...incoming,
    start: Math.min(current.start, incoming.start),
    focusIndex: current.focusIndex ?? incoming.focusIndex,
    focusSectionId: current.focusSectionId ?? incoming.focusSectionId,
    hasPrevious: current.hasPrevious && incoming.hasPrevious,
    hasNext: current.hasNext && incoming.hasNext,
    sections: [...sections.values()].sort((a, b) => a.order - b.order),
  };
};

function HighlightedText({ text, quote }: { text: string; quote?: string | null }) {
  if (!quote) return <>{text}</>;
  const index = text.indexOf(quote);
  if (index < 0) return <>{text}</>;
  return <>{text.slice(0, index)}<mark className="rounded-sm bg-accent/35 px-0.5 text-inherit">{quote}</mark>{text.slice(index + quote.length)}</>;
}

function SourcePreview({ id, sources, activeIndex, trigger, onSelect, onClose }: SourcePreviewProps) {
  const { t } = useI18n();
  const titleId = useId();
  const panelRef = useRef<HTMLElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const earlierRef = useRef<HTMLButtonElement>(null);
  const laterRef = useRef<HTMLButtonElement>(null);
  const loadingRef = useRef(false);
  const pendingLoadsRef = useRef(0);
  const closeRef = useRef<HTMLButtonElement>(null);
  const triggerRef = useRef(trigger);
  const onCloseRef = useRef(onClose);
  const [desktop, setDesktop] = useState(isDesktopViewport);
  const [panelWidth, setPanelWidth] = useState(DEFAULT_WIDTH);
  const [preview, setPreview] = useState<SourcePreviewView | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const source = sources[activeIndex];
  const previewForSource = preview?.documentId === source?.documentId ? preview : null;
  const link = safeHttpUrl(source?.link ?? previewForSource?.sourceUrl);
  const hostname = link ? getHostname(link) : "";
  const addedDate = source ? formatDate(source.added_date || previewForSource?.publishedDate || "", t.meta.intl) : "";
  const cacheKey = source?.documentId ? `${source.documentId}:${source.versionId ?? "current"}` : "";

  useEffect(() => { onCloseRef.current = onClose; });
  useEffect(() => { triggerRef.current = trigger; }, [trigger]);
  useEffect(() => {
    const media = window.matchMedia?.(DESKTOP_QUERY);
    if (!media) return;
    const update = () => setDesktop(media.matches);
    media.addEventListener?.("change", update);
    return () => media.removeEventListener?.("change", update);
  }, []);

  const load = useCallback(async (start?: number, signal?: AbortSignal) => {
    if (!source?.documentId) { setFailed(true); return; }
    pendingLoadsRef.current += 1;
    loadingRef.current = true;
    setLoading(true);
    try {
      const result = await api.getSourcePreview(source.documentId, {
        versionId: source.versionId,
        focusEvidenceId: start === undefined ? source.evidenceId : undefined,
        start,
        limit: PAGE_SIZE,
        signal,
      });
      setPreview(current => {
        const merged = mergePreview(current, result);
        previewCache.set(cacheKey, merged);
        return merged;
      });
      setFailed(false);
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) setFailed(true);
    } finally {
      pendingLoadsRef.current = Math.max(0, pendingLoadsRef.current - 1);
      loadingRef.current = pendingLoadsRef.current > 0;
      if (!signal?.aborted) setLoading(loadingRef.current);
    }
  }, [cacheKey, source?.documentId, source?.evidenceId, source?.versionId]);

  useEffect(() => {
    const cached = cacheKey ? previewCache.get(cacheKey) ?? null : null;
    setPreview(cached);
    setFailed(false);
    const controller = new AbortController();
    if (!cached) void load(undefined, controller.signal);
    return () => controller.abort();
  }, [cacheKey, load]);

  useEffect(() => {
    if (!preview?.focusSectionId) return;
    requestAnimationFrame(() => Array.from(panelRef.current?.querySelectorAll<HTMLElement>("[data-source-section]") ?? [])
      .find(element => element.dataset.sourceSection === preview.focusSectionId)
      ?.scrollIntoView({ block: "center" }));
  }, [preview?.focusSectionId]);

  useEffect(() => {
    if (!preview || loading || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) {
        if (!entry.isIntersecting || loadingRef.current) continue;
        if (entry.target === earlierRef.current && preview.hasPrevious) {
          void load(Math.max(0, preview.start - PAGE_SIZE));
        } else if (entry.target === laterRef.current && preview.hasNext) {
          void load(preview.start + preview.sections.length);
        }
      }
    }, { root: scrollRef.current, rootMargin: "120px 0px" });
    if (earlierRef.current) observer.observe(earlierRef.current);
    if (laterRef.current) observer.observe(laterRef.current);
    return () => observer.disconnect();
  }, [load, loading, preview]);

  useEffect(() => {
    closeRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); onCloseRef.current(); return; }
      if (event.key !== "Tab" || isDesktopViewport()) return;
      const focusable = focusableElements(panelRef.current);
      if (!focusable.length) { event.preventDefault(); panelRef.current?.focus(); return; }
      const first = focusable[0]; const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      if (triggerRef.current?.isConnected) triggerRef.current.focus();
    };
  }, []);

  useEffect(() => {
    document.documentElement.style.setProperty("--source-panel-width", `${panelWidth}px`);
    if (desktop) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = previousOverflow; };
  }, [desktop, panelWidth]);

  if (!source) return null;

  const beginResize = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = panelWidth;
    const move = (moveEvent: PointerEvent) => setPanelWidth(Math.min(window.innerWidth * 0.45,
      Math.max(MIN_WIDTH, startWidth + startX - moveEvent.clientX)));
    const stop = () => { document.removeEventListener("pointermove", move); document.removeEventListener("pointerup", stop); };
    document.addEventListener("pointermove", move);
    document.addEventListener("pointerup", stop);
  };

  const locatorLabel = (locator: Record<string, unknown>) => {
    const page = locator.page ?? locator.pageNumber;
    if (typeof page === "number" || typeof page === "string") return t.message.sourcePage(String(page));
    const startLine = locator.startLine;
    const endLine = locator.endLine;
    if (typeof startLine === "number") return t.message.sourceLines(startLine, typeof endLine === "number" ? endLine : startLine);
    return "";
  };

  return createPortal(
    <div className="pointer-events-none fixed inset-0 z-50" data-source-panel>
      <button type="button" aria-hidden="true" tabIndex={-1} data-testid="source-preview-backdrop"
        onClick={onClose} className="pointer-events-auto absolute inset-0 bg-black/40 lg:hidden" />
      <section ref={panelRef} id={id} role="dialog" aria-modal={desktop ? undefined : true} aria-labelledby={titleId}
        tabIndex={-1} style={desktop ? { width: panelWidth } : undefined}
        className="pointer-events-auto absolute inset-x-0 bottom-0 flex max-h-[75dvh] flex-col overflow-hidden rounded-t-2xl border border-border bg-background shadow-2xl lg:inset-y-0 lg:right-0 lg:left-auto lg:max-h-none lg:rounded-none lg:border-y-0 lg:border-r-0">
        {desktop && <div role="separator" aria-orientation="vertical" aria-label={t.message.resizeSources}
          aria-valuemin={MIN_WIDTH} aria-valuemax={Math.round(window.innerWidth * 0.45)} aria-valuenow={Math.round(panelWidth)}
          tabIndex={0} onPointerDown={beginResize}
          onKeyDown={event => {
            if (event.key === "ArrowLeft") setPanelWidth(width => Math.min(window.innerWidth * 0.45, width + 16));
            if (event.key === "ArrowRight") setPanelWidth(width => Math.max(MIN_WIDTH, width - 16));
          }} className="absolute inset-y-0 left-0 z-10 w-2 -translate-x-1/2 cursor-col-resize focus-visible:bg-accent/40 focus-visible:outline-none" />}

        <header className="flex shrink-0 items-start justify-between gap-4 border-b border-border px-5 py-4">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-wide text-primary">{t.message.sourcePosition(activeIndex + 1, sources.length)}</p>
            <h2 id={titleId} className="mt-1 break-words font-serif text-xl leading-tight text-text">{source.title}</h2>
          </div>
          <button ref={closeRef} type="button" onClick={onClose} aria-label={t.message.closeSources}
            className="cursor-pointer shrink-0 rounded-sm p-2 text-text-muted hover:bg-background-secondary hover:text-text focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary">
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true"><path strokeLinecap="round" d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        </header>

        <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
          {(hostname || addedDate || source.documentId) && <div className="mb-4 flex flex-wrap gap-x-3 gap-y-1 text-xs text-text-subtle">
            {hostname && <span>{hostname}</span>}{addedDate && <span>{addedDate}</span>}{source.documentId && <span className="truncate">{source.documentId}</span>}
          </div>}

          {source.exactQuote && <div className="mb-5">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">{t.message.supportingQuote}</p>
            <blockquote className="break-words border-l-4 border-accent bg-background-secondary px-4 py-3 text-sm leading-relaxed text-text">{source.exactQuote}</blockquote>
          </div>}

          {loading && !preview && <div role="status" className="space-y-3" aria-label={t.message.loadingSource}>
            {[0, 1, 2, 3].map(item => <div key={item} className="h-16 animate-pulse rounded-sm bg-background-secondary" />)}
          </div>}

          {preview && <article className="space-y-4">
            {preview.hasPrevious && <button ref={earlierRef} type="button" disabled={loading} onClick={() => void load(Math.max(0, preview.start - PAGE_SIZE))}
              className="w-full cursor-pointer rounded-sm border border-border px-3 py-2 text-sm font-medium text-primary hover:bg-primary-50 disabled:opacity-50">{t.message.loadEarlier}</button>}
            {preview.sections.map(section => {
              const focused = section.id === preview.focusSectionId;
              const label = locatorLabel(section.locator);
              return <section key={section.id} data-source-section={section.id}
                className={`scroll-m-6 rounded-sm border px-4 py-3 ${focused ? "border-accent bg-accent/10 shadow-sm" : "border-border bg-background"}`}>
                {section.headingPath.length > 0 && <p className="mb-1 text-xs font-semibold text-primary">{section.headingPath.join(" › ")}</p>}
                {label && <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-text-subtle">{label}</p>}
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-text"><HighlightedText text={section.text} quote={focused ? source.exactQuote : null} /></p>
              </section>;
            })}
            {preview.hasNext && <button ref={laterRef} type="button" disabled={loading} onClick={() => void load(preview.start + preview.sections.length)}
              className="w-full cursor-pointer rounded-sm border border-border px-3 py-2 text-sm font-medium text-primary hover:bg-primary-50 disabled:opacity-50">{t.message.loadMore}</button>}
          </article>}

          {(!preview && (failed || !source.documentId)) && <div>
            <p className="mb-3 text-sm text-text-muted">{t.message.previewUnavailable}</p>
          </div>}

          {link ? <a href={link} target="_blank" rel="noopener noreferrer"
            className="mt-6 inline-flex cursor-pointer items-center gap-2 rounded-sm bg-primary px-4 py-2.5 text-sm font-semibold text-text-inverted hover:bg-primary-dark focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary">
            {t.message.openSource}<span aria-hidden="true">↗</span></a>
            : <p className="mt-6 text-sm text-text-subtle">{t.message.noLink}</p>}
        </div>

        {sources.length > 1 && <footer className="flex shrink-0 items-center justify-between gap-3 border-t border-border px-5 py-3">
          <button type="button" disabled={activeIndex === 0} onClick={() => onSelect(activeIndex - 1)}
            className="cursor-pointer rounded-sm px-3 py-2 text-sm font-medium text-primary hover:bg-primary-50 disabled:cursor-not-allowed disabled:opacity-40">← {t.message.previousSource}</button>
          <button type="button" disabled={activeIndex === sources.length - 1} onClick={() => onSelect(activeIndex + 1)}
            className="cursor-pointer rounded-sm px-3 py-2 text-sm font-medium text-primary hover:bg-primary-50 disabled:cursor-not-allowed disabled:opacity-40">{t.message.nextSource} →</button>
        </footer>}
      </section>
    </div>, document.body,
  );
}

export default SourcePreview;
