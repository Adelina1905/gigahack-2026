import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { useI18n } from "../../i18n/context";
import type { ProjectSummary } from "../../types/chat";
import type { PlanTracker } from "../../types/tracker";
import { CityGatesArt, TriumphalArchArt } from "../brand/Landmarks";
import TitleRule from "../brand/TitleRule";
import { iconProps } from "../sidebar/iconProps";

interface TrackersViewProps {
  trackers: PlanTracker[];
  selectedId: string | null;
  projects: ProjectSummary[];
  isCreating: boolean;
  creationProject?: ProjectSummary | null;
  onSelect: (trackerId: string) => void;
  onStartCreate: () => void;
  onCancelCreate: () => void;
  onCompleteCreate: (details: Partial<PlanTracker>, project?: ProjectSummary) => void;
  onUpdate: (tracker: PlanTracker) => void;
  onRemove: (trackerId: string) => void;
}

function TagEditor({
  title,
  items,
  placeholder,
  onChange,
}: {
  title: string;
  items: string[];
  placeholder: string;
  onChange: (items: string[]) => void;
}) {
  const { t } = useI18n();
  const [value, setValue] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const label = value.trim();
    if (!label || items.some((item) => item.toLowerCase() === label.toLowerCase())) return;
    onChange([...items, label]);
    setValue("");
  };

  return (
    <section>
      <h3 className="font-serif text-lg text-primary">{title}</h3>
      <div className="mt-2 flex flex-wrap gap-2">
        {items.map((item) => (
          <span key={item} className="inline-flex items-center gap-1.5 rounded-sm border border-primary-200 bg-primary-50 px-2.5 py-1.5 text-sm text-primary-800">
            {item}
            <button
              type="button"
              onClick={() => onChange(items.filter((candidate) => candidate !== item))}
              aria-label={t.trackers.removeItem(item)}
              className="rounded-sm p-0.5 text-primary-500 hover:bg-white hover:text-danger"
            >
              ×
            </button>
          </span>
        ))}
      </div>
      <form onSubmit={submit} className="mt-3 flex max-w-xl gap-2">
        <input
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder={placeholder}
          className="min-w-0 flex-1 rounded-sm border border-border-strong bg-background px-3 py-2 text-sm outline-none focus:border-primary"
        />
        <button type="submit" disabled={!value.trim()} className="rounded-sm border border-primary px-3 py-2 text-sm font-semibold text-primary hover:bg-primary-50 disabled:opacity-40">
          {t.trackers.add}
        </button>
      </form>
    </section>
  );
}

function SimpleList({ title, items, tone }: { title: string; items: string[]; tone: "risk" | "opportunity" }) {
  const color = tone === "risk" ? "text-danger bg-danger-light" : "text-primary-700 bg-primary-50";
  return (
    <section className="rounded-sm border border-border bg-background p-4">
      <h3 className="font-serif text-lg text-primary">{title}</h3>
      {items.length ? (
        <ul className="mt-3 space-y-2">
          {items.map((item) => (
            <li key={item} className="flex gap-2 text-sm text-text-muted">
              <span aria-hidden="true" className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs font-bold ${color}`}>
                {tone === "risk" ? "!" : "+"}
              </span>
              {item}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm text-text-subtle">—</p>
      )}
    </section>
  );
}

function GuideBubble({ children, user = false }: { children: ReactNode; user?: boolean }) {
  return (
    <div className={`flex ${user ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[85%] rounded-sm px-4 py-3 text-sm leading-relaxed shadow-sm ${user ? "bg-primary text-white" : "border border-border bg-background text-text"}`}>
        {children}
      </div>
    </div>
  );
}

function TrackerConversation({ project, onCancel, onComplete }: { project?: ProjectSummary | null; onCancel: () => void; onComplete: (details: Partial<PlanTracker>, project?: ProjectSummary) => void }) {
  const { t } = useI18n();
  const [step, setStep] = useState(0);
  const [plan, setPlan] = useState(project?.name ?? "");
  const [location, setLocation] = useState("");
  const [topics, setTopics] = useState<string[]>([]);
  const toggleTopic = (topic: string) => setTopics((current) => current.includes(topic) ? current.filter((item) => item !== topic) : [...current, topic]);
  const trackerName = project?.name || plan.trim() || t.trackers.newTracker;

  return (
    <div className="mx-auto w-full max-w-3xl px-5 py-8 sm:px-8">
      <div className="mb-5 flex items-center justify-between gap-3">
        <span className="inline-flex items-center gap-2 rounded-sm border border-accent bg-accent/10 px-2.5 py-1 text-[11px] font-bold uppercase tracking-[0.12em] text-primary-900">
          <span className="h-1.5 w-1.5 rounded-full bg-accent" />
          {t.trackers.guidedLabel}
        </span>
        <button type="button" onClick={onCancel} className="rounded-sm px-3 py-1.5 text-sm text-text-muted hover:bg-background-secondary">{t.trackers.cancel}</button>
      </div>

      <div className="space-y-3" aria-live="polite">
        <GuideBubble>{t.trackers.guideIntro}</GuideBubble>
        {step === 0 ? (
          <div className="ml-auto max-w-[85%] rounded-sm bg-primary p-3 shadow-sm">
            <textarea autoFocus value={plan} onChange={(event) => setPlan(event.target.value)} placeholder={t.trackers.guidePlanPlaceholder} rows={3} className="w-full resize-none rounded-sm border border-white/30 bg-white px-3 py-2.5 text-sm text-text outline-none" />
            <div className="mt-2 flex justify-end">
              <button type="button" disabled={!plan.trim()} onClick={() => setStep(1)} className="rounded-sm bg-white px-3 py-2 text-sm font-semibold text-primary disabled:opacity-50">{t.trackers.continue}</button>
            </div>
          </div>
        ) : (
          <GuideBubble user>{plan}</GuideBubble>
        )}

        {step >= 1 && <GuideBubble>{t.trackers.guideLocation}</GuideBubble>}
        {step === 1 ? (
          <div className="ml-auto max-w-[85%] rounded-sm bg-primary p-3 shadow-sm">
            <input autoFocus value={location} onChange={(event) => setLocation(event.target.value)} placeholder={t.trackers.guideLocationPlaceholder} className="w-full rounded-sm border border-white/30 bg-white px-3 py-2.5 text-sm text-text outline-none" />
            <div className="mt-2 flex justify-between">
              <button type="button" onClick={() => setStep(0)} className="px-2 py-2 text-sm font-medium text-white/85">{t.trackers.back}</button>
              <button type="button" disabled={!location.trim()} onClick={() => setStep(2)} className="rounded-sm bg-white px-3 py-2 text-sm font-semibold text-primary disabled:opacity-50">{t.trackers.continue}</button>
            </div>
          </div>
        ) : step > 1 ? <GuideBubble user>{location}</GuideBubble> : null}

        {step >= 2 && <GuideBubble>{t.trackers.guideTopics}</GuideBubble>}
        {step === 2 && (
          <div className="rounded-sm border border-border bg-background p-4 shadow-sm">
            <div className="flex flex-wrap gap-2">
              {t.trackers.suggestedTopics.map((topic) => (
                <button key={topic} type="button" onClick={() => toggleTopic(topic)} aria-pressed={topics.includes(topic)} className={`rounded-sm border px-3 py-2 text-sm transition-colors ${topics.includes(topic) ? "border-primary bg-primary text-white" : "border-border-strong bg-background hover:border-primary hover:text-primary"}`}>
                  {topics.includes(topic) ? "✓ " : "+ "}{topic}
                </button>
              ))}
            </div>
            <div className="mt-4 flex justify-between">
              <button type="button" onClick={() => setStep(1)} className="px-2 py-2 text-sm font-medium text-text-muted">{t.trackers.back}</button>
              <button type="button" disabled={topics.length === 0} onClick={() => setStep(3)} className="rounded-sm bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{t.trackers.continue}</button>
            </div>
          </div>
        )}

        {step === 3 && (
          <>
            <GuideBubble>{t.trackers.guideReview}</GuideBubble>
            <div className="ml-auto max-w-[92%] rounded-sm border border-primary-200 bg-primary-50 p-5 shadow-sm">
              <p className="font-serif text-xl text-primary">{trackerName}</p>
              <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
                <div><dt className="text-xs font-bold uppercase tracking-wide text-text-subtle">{t.trackers.plan}</dt><dd className="mt-1 text-text">{plan}</dd></div>
                <div><dt className="text-xs font-bold uppercase tracking-wide text-text-subtle">{t.trackers.location}</dt><dd className="mt-1 text-text">{location}</dd></div>
              </dl>
              <div className="mt-4 flex flex-wrap gap-1.5">{topics.map((topic) => <span key={topic} className="rounded-sm border border-primary-200 bg-white px-2 py-1 text-xs text-primary-700">{topic}</span>)}</div>
              <div className="mt-5 flex flex-wrap justify-between gap-2 border-t border-primary-200 pt-4">
                <button type="button" onClick={() => setStep(2)} className="px-2 py-2 text-sm font-medium text-text-muted">{t.trackers.back}</button>
                <button type="button" onClick={() => onComplete({ name: trackerName, plan, location, summary: plan, topics }, project ?? undefined)} className="rounded-sm bg-primary px-4 py-2.5 text-sm font-semibold text-white hover:bg-primary-dark">{t.trackers.confirmCreate}</button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function TrackerDetail({ tracker, project, onUpdate, onRemove }: { tracker: PlanTracker; project?: ProjectSummary; onUpdate: (tracker: PlanTracker) => void; onRemove: () => void }) {
  const { t, locale } = useI18n();
  const [draft, setDraft] = useState(tracker);
  const [saved, setSaved] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  useEffect(() => {
    setDraft(tracker);
    setSaved(false);
    setIsEditing(false);
  }, [tracker]);

  const save = () => {
    onUpdate(draft);
    setSaved(true);
    setIsEditing(false);
  };
  const date = new Intl.DateTimeFormat(locale === "ro" ? "ro-MD" : locale === "ru" ? "ru-MD" : "en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(new Date(`${draft.dataThrough}T12:00:00`));

  return (
    <article className="mx-auto w-full max-w-5xl px-5 pb-12 pt-6 sm:px-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-sm bg-primary px-2 py-1 text-[10px] font-bold uppercase tracking-[0.14em] text-white">{t.trackers.profile}</span>
            {draft.isExample && <span className="rounded-sm border border-accent bg-accent/15 px-2 py-1 text-[10px] font-bold uppercase tracking-[0.12em] text-primary-900">{t.trackers.example}</span>}
          </div>
          {isEditing ? <input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} aria-label={t.trackers.name} className="mt-3 w-full min-w-0 border-b border-border-strong bg-transparent font-serif text-3xl leading-tight text-primary outline-none focus:border-primary sm:text-4xl" /> : <h2 className="mt-3 font-serif text-3xl leading-tight text-primary sm:text-4xl">{draft.name}</h2>}
          {project && <p className="mt-1 text-sm text-text-subtle">{t.trackers.fromProject(project.name)}</p>}
          <TitleRule className="mt-4" />
        </div>
        <div className="rounded-sm border border-border bg-background px-4 py-3 text-right shadow-sm">
          <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-text-subtle">{t.trackers.freshness}</p>
          <p className="mt-1 text-sm font-semibold text-text">{t.trackers.availableThrough(date)}</p>
          <p className="mt-1 inline-flex items-center gap-1.5 text-xs text-text-muted">
            <span className="h-1.5 w-1.5 rounded-full bg-accent" /> {t.trackers.notLive}
          </p>
        </div>
      </div>

      <div className="mt-7 grid gap-5 rounded-sm border border-border bg-background p-5 shadow-sm sm:grid-cols-2">
        {isEditing ? <><label className="block">
          <span className="text-xs font-bold uppercase tracking-[0.1em] text-text-subtle">{t.trackers.plan}</span>
          <input value={draft.plan} onChange={(event) => setDraft({ ...draft, plan: event.target.value })} placeholder={t.trackers.planPlaceholder} className="mt-2 w-full rounded-sm border border-border-strong px-3 py-2.5 text-sm outline-none focus:border-primary" />
        </label>
        <label className="block">
          <span className="text-xs font-bold uppercase tracking-[0.1em] text-text-subtle">{t.trackers.location}</span>
          <input value={draft.location} onChange={(event) => setDraft({ ...draft, location: event.target.value })} placeholder={t.trackers.locationPlaceholder} className="mt-2 w-full rounded-sm border border-border-strong px-3 py-2.5 text-sm outline-none focus:border-primary" />
        </label>
        <label className="block sm:col-span-2">
          <span className="text-xs font-bold uppercase tracking-[0.1em] text-text-subtle">{t.trackers.summary}</span>
          <textarea value={draft.summary} onChange={(event) => setDraft({ ...draft, summary: event.target.value })} placeholder={t.trackers.summaryPlaceholder} rows={3} className="mt-2 w-full resize-y rounded-sm border border-border-strong px-3 py-2.5 text-sm leading-relaxed outline-none focus:border-primary" />
        </label></> : <>
          <div><p className="text-xs font-bold uppercase tracking-[0.1em] text-text-subtle">{t.trackers.plan}</p><p className="mt-2 text-sm leading-relaxed text-text">{draft.plan || "—"}</p></div>
          <div><p className="text-xs font-bold uppercase tracking-[0.1em] text-text-subtle">{t.trackers.location}</p><p className="mt-2 text-sm leading-relaxed text-text">{draft.location || "—"}</p></div>
          <div className="sm:col-span-2"><p className="text-xs font-bold uppercase tracking-[0.1em] text-text-subtle">{t.trackers.summary}</p><p className="mt-2 text-sm leading-relaxed text-text-muted">{draft.summary || "—"}</p></div>
        </>}
      </div>

      <div className="mt-7 rounded-sm border border-border bg-background p-5 shadow-sm">
        {isEditing ? <TagEditor title={t.trackers.topics} items={draft.topics} placeholder={t.trackers.topicPlaceholder} onChange={(topics) => setDraft({ ...draft, topics })} /> : <section><h3 className="font-serif text-lg text-primary">{t.trackers.topics}</h3><div className="mt-3 flex flex-wrap gap-2">{draft.topics.map((topic) => <span key={topic} className="rounded-sm border border-primary-200 bg-primary-50 px-2.5 py-1.5 text-sm text-primary-800">{topic}</span>)}</div></section>}
      </div>

      <div className="mt-5 grid gap-5 md:grid-cols-2">
        <SimpleList title={t.trackers.risks} items={draft.risks} tone="risk" />
        <SimpleList title={t.trackers.opportunities} items={draft.opportunities} tone="opportunity" />
      </div>

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-5">
        <p className="max-w-2xl text-xs leading-relaxed text-text-subtle">{t.trackers.prototypeNote}</p>
        <div className="flex items-center gap-2">
          <button type="button" onClick={onRemove} className="rounded-sm px-3 py-2 text-sm font-medium text-text-subtle hover:bg-danger-light hover:text-danger">{t.trackers.remove}</button>
          {isEditing ? <button type="button" onClick={save} className="rounded-sm bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary-dark">{saved ? t.trackers.saved : t.trackers.save}</button> : <button type="button" onClick={() => setIsEditing(true)} className="rounded-sm bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary-dark">{t.trackers.adjust}</button>}
        </div>
      </div>
    </article>
  );
}

export default function TrackersView({ trackers, selectedId, projects, isCreating, creationProject, onSelect, onStartCreate, onCancelCreate, onCompleteCreate, onUpdate, onRemove }: TrackersViewProps) {
  const { t } = useI18n();
  const selected = trackers.find((tracker) => tracker.id === selectedId) ?? trackers[0];

  return (
    <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden bg-background-canvas">
      <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 bottom-0 hidden items-end justify-between px-6 text-primary opacity-[0.07] xl:flex">
        <TriumphalArchArt className="h-44" />
        <CityGatesArt className="h-56" />
      </div>
      <header className="relative border-b border-border bg-background/90 px-5 py-5 sm:px-8">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-primary">{t.trackers.eyebrow}</p>
            <h1 className="mt-1 font-serif text-2xl text-primary sm:text-3xl">{t.trackers.title}</h1>
            <p className="mt-1 max-w-2xl text-sm text-text-muted">{t.trackers.description}</p>
          </div>
          <button type="button" onClick={onStartCreate} className="inline-flex items-center gap-2 rounded-sm bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-primary-dark">
            <svg {...iconProps} className="h-4 w-4"><path d="M12 5v14M5 12h14" /></svg>
            {t.trackers.newTracker}
          </button>
        </div>
      </header>

      {!isCreating && <div className="relative border-b border-border bg-background px-5 py-3 sm:px-8">
        <div className="mx-auto flex max-w-5xl gap-2 overflow-x-auto pb-1">
          {trackers.map((tracker) => (
            <button key={tracker.id} type="button" onClick={() => onSelect(tracker.id)} className={`min-w-[13rem] rounded-sm border px-3 py-2.5 text-left transition-colors ${selected?.id === tracker.id ? "border-primary bg-primary-50" : "border-border bg-background hover:border-primary-200"}`}>
              <span className="block truncate text-sm font-semibold text-text">{tracker.name}</span>
              <span className="mt-0.5 block truncate text-xs text-text-subtle">{tracker.location || t.trackers.locationMissing}</span>
            </button>
          ))}
          {trackers.length === 0 && <p className="py-2 text-sm text-text-subtle">{t.trackers.empty}</p>}
        </div>
      </div>}

      <div className="relative min-h-0 flex-1 overflow-y-auto">
        {isCreating ? (
          <TrackerConversation project={creationProject} onCancel={onCancelCreate} onComplete={onCompleteCreate} />
        ) : selected ? (
          <TrackerDetail tracker={selected} project={projects.find((project) => project.id === selected.projectId)} onUpdate={onUpdate} onRemove={() => onRemove(selected.id)} />
        ) : (
          <div className="mx-auto max-w-xl px-6 py-16 text-center">
            <h2 className="font-serif text-2xl text-primary">{t.trackers.emptyTitle}</h2>
            <p className="mt-2 text-sm text-text-muted">{t.trackers.empty}</p>
          </div>
        )}
      </div>
    </div>
  );
}
