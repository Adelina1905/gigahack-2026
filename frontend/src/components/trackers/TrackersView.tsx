import { useEffect, useState, type FormEvent } from "react";
import { useI18n } from "../../i18n/context";
import type { ProjectSummary } from "../../types/chat";
import type { PlanTracker } from "../../types/tracker";
import { CityGatesArt, TriumphalArchArt } from "../brand/Landmarks";
import TitleRule from "../brand/TitleRule";
import { CivicSurface, StatusBadge, StepProgress, TopicChip } from "../civic/CivicPrimitives";
import { iconProps } from "../sidebar/iconProps";

interface TrackersViewProps {
  trackers: PlanTracker[];
  selectedId: string | null;
  projects: ProjectSummary[];
  isCreating: boolean;
  creationProject?: ProjectSummary | null;
  onSelect: (trackerId: string) => void;
  onBackToList: () => void;
  onStartCreate: () => void;
  onCancelCreate: () => void;
  onCompleteCreate: (details: Partial<PlanTracker>, project?: ProjectSummary) => void;
  onUpdate: (tracker: PlanTracker) => void;
  onRemove: (trackerId: string) => void;
}

const intlLocale = (locale: string) => locale === "ro" ? "ro-MD" : locale === "ru" ? "ru-MD" : "en-GB";

function formatSnapshotDate(value: string, locale: string) {
  return new Intl.DateTimeFormat(intlLocale(locale), { day: "numeric", month: "long", year: "numeric" })
    .format(new Date(`${value}T12:00:00`));
}

function TagEditor({ items, onChange }: { items: string[]; onChange: (items: string[]) => void }) {
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
    <div>
      <div className="flex flex-wrap gap-2">
        {items.map((item) => (
          <span key={item} className="inline-flex min-h-9 items-center gap-1 rounded-[5px] border border-primary-100 bg-primary-50/70 py-1 pl-3 pr-1.5 text-sm text-primary-800">
            {item}
            <button type="button" onClick={() => onChange(items.filter((candidate) => candidate !== item))} aria-label={t.trackers.removeItem(item)} className="flex h-8 w-8 items-center justify-center rounded text-primary-500 hover:bg-white hover:text-danger focus-visible:outline-2 focus-visible:outline-primary">×</button>
          </span>
        ))}
      </div>
      <form onSubmit={submit} className="mt-4 flex max-w-xl flex-col gap-2 sm:flex-row">
        <input value={value} onChange={(event) => setValue(event.target.value)} placeholder={t.trackers.topicPlaceholder} className="min-h-11 min-w-0 flex-1 rounded-[5px] border border-border-strong bg-background px-3 text-sm outline-none transition-colors duration-200 focus:border-primary motion-reduce:transition-none" />
        <button type="submit" disabled={!value.trim()} className="min-h-11 rounded-[5px] border border-primary px-4 text-sm font-semibold text-primary transition-colors duration-200 hover:bg-primary-50 disabled:opacity-40 motion-reduce:transition-none">{t.trackers.add}</button>
      </form>
    </div>
  );
}

function TrackerConversation({ project, onCancel, onComplete }: { project?: ProjectSummary | null; onCancel: () => void; onComplete: (details: Partial<PlanTracker>, project?: ProjectSummary) => void }) {
  const { t } = useI18n();
  const [step, setStep] = useState(1);
  const [reviewing, setReviewing] = useState(false);
  const [plan, setPlan] = useState(project?.name ?? "");
  const [location, setLocation] = useState("");
  const [topics, setTopics] = useState<string[]>([]);
  const trackerName = project?.name || plan.trim() || t.trackers.newTracker;
  const canContinue = step === 1 ? Boolean(plan.trim()) : step === 2 ? Boolean(location.trim()) : topics.length > 0;
  const toggleTopic = (topic: string) => setTopics((current) => current.includes(topic) ? current.filter((item) => item !== topic) : [...current, topic]);

  const goBack = () => {
    if (reviewing) setReviewing(false);
    else if (step > 1) setStep((current) => current - 1);
    else onCancel();
  };
  const continueSetup = () => {
    if (!canContinue) return;
    if (step < 3) setStep((current) => current + 1);
    else setReviewing(true);
  };

  return (
    <div className="mx-auto w-full max-w-2xl px-4 py-8 sm:px-8 sm:py-10">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div><StatusBadge tone="gold">{t.trackers.guidedLabel}</StatusBadge><h2 className="mt-3 font-serif text-2xl text-primary sm:text-3xl">{trackerName}</h2></div>
        <button type="button" onClick={onCancel} className="min-h-11 rounded-[5px] px-3 text-sm text-text-muted hover:bg-background-secondary focus-visible:outline-2 focus-visible:outline-primary">{t.trackers.cancel}</button>
      </div>
      <StepProgress current={step} total={3} label={t.trackers.guideProgress} />

      <CivicSurface className="mt-5 overflow-hidden">
        <div className="min-h-[18rem] p-5 sm:p-7">
          {!reviewing ? (
            <div className="animate-[fade-in_180ms_ease-out] motion-reduce:animate-none">
              <div className="flex items-start gap-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[5px] bg-primary text-sm font-bold text-white" aria-hidden="true">C</span>
                <div><p className="font-serif text-xl leading-snug text-primary">{step === 1 ? t.trackers.guideIntro : step === 2 ? t.trackers.guideLocation : t.trackers.guideTopics}</p><p className="mt-1 text-xs text-text-subtle">{t.trackers.guidedLabel}</p></div>
              </div>
              {step === 1 && <textarea autoFocus value={plan} onChange={(event) => setPlan(event.target.value)} placeholder={t.trackers.guidePlanPlaceholder} rows={4} className="mt-6 w-full resize-none rounded-[5px] border border-border-strong bg-background px-4 py-3 text-base leading-relaxed text-text outline-none transition-colors duration-200 focus:border-primary focus:ring-2 focus:ring-primary/10 motion-reduce:transition-none" />}
              {step === 2 && <input autoFocus value={location} onChange={(event) => setLocation(event.target.value)} placeholder={t.trackers.guideLocationPlaceholder} className="mt-6 min-h-12 w-full rounded-[5px] border border-border-strong bg-background px-4 text-base text-text outline-none transition-colors duration-200 focus:border-primary focus:ring-2 focus:ring-primary/10 motion-reduce:transition-none" />}
              {step === 3 && <div className="mt-6 flex flex-wrap gap-2">{t.trackers.suggestedTopics.map((topic) => <TopicChip key={topic} interactive selected={topics.includes(topic)} onClick={() => toggleTopic(topic)}>{topics.includes(topic) ? "✓ " : "+ "}{topic}</TopicChip>)}</div>}
            </div>
          ) : (
            <div className="animate-[fade-in_180ms_ease-out] motion-reduce:animate-none">
              <div className="flex items-start gap-3"><span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[5px] bg-primary text-sm font-bold text-white" aria-hidden="true">C</span><p className="font-serif text-xl leading-snug text-primary">{t.trackers.guideReview}</p></div>
              <dl className="mt-6 grid gap-5 sm:grid-cols-2"><div><dt className="text-sm font-semibold text-text-subtle">{t.trackers.plan}</dt><dd className="mt-1 leading-relaxed text-text">{plan}</dd></div><div><dt className="text-sm font-semibold text-text-subtle">{t.trackers.location}</dt><dd className="mt-1 leading-relaxed text-text">{location}</dd></div></dl>
              <div className="mt-5 flex flex-wrap gap-2">{topics.map((topic) => <TopicChip key={topic}>{topic}</TopicChip>)}</div>
            </div>
          )}
        </div>
        <div className="flex items-center justify-between gap-3 border-t border-border/80 bg-background-secondary/50 px-5 py-3 sm:px-7">
          <button type="button" onClick={goBack} className="min-h-11 rounded-[5px] px-3 text-sm font-semibold text-text-muted hover:bg-background focus-visible:outline-2 focus-visible:outline-primary">{t.trackers.back}</button>
          {reviewing ? <button type="button" onClick={() => onComplete({ name: trackerName, plan, location, summary: plan, topics }, project ?? undefined)} className="min-h-11 rounded-[5px] bg-primary px-5 text-sm font-semibold text-white transition-colors duration-200 hover:bg-primary-dark focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary motion-reduce:transition-none">{t.trackers.confirmCreate}</button> : <button type="button" disabled={!canContinue} onClick={continueSetup} className="min-h-11 rounded-[5px] bg-primary px-5 text-sm font-semibold text-white transition-colors duration-200 hover:bg-primary-dark disabled:cursor-not-allowed disabled:opacity-40 motion-reduce:transition-none">{t.trackers.continue}</button>}
        </div>
      </CivicSurface>
    </div>
  );
}

function TrackerList({ trackers, onSelect, onCreate }: { trackers: PlanTracker[]; onSelect: (trackerId: string) => void; onCreate: () => void }) {
  const { t, locale } = useI18n();
  if (trackers.length === 0) return <div className="mx-auto max-w-xl px-6 py-16 text-center"><h2 className="font-serif text-2xl text-primary">{t.trackers.emptyTitle}</h2><p className="mt-2 text-sm leading-relaxed text-text-muted">{t.trackers.empty}</p><button type="button" onClick={onCreate} className="mt-6 min-h-11 rounded-[5px] bg-primary px-5 text-sm font-semibold text-white">{t.trackers.newTracker}</button></div>;

  return (
    <div className="mx-auto w-full max-w-4xl px-4 py-6 sm:px-8 sm:py-8"><div className="space-y-3">
      {trackers.map((tracker) => (
        <CivicSurface key={tracker.id}><button type="button" onClick={() => onSelect(tracker.id)} aria-label={t.trackers.openTracker(tracker.name)} className="group flex min-h-[7.5rem] w-full items-center gap-4 px-4 py-4 text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary sm:px-5">
          <span className="hidden h-12 w-12 shrink-0 items-center justify-center rounded-[5px] bg-primary-50 text-primary sm:flex" aria-hidden="true"><svg {...iconProps} className="h-5 w-5"><path d="M4 19V8l8-5 8 5v11M8 21v-7h8v7M3 21h18" /></svg></span>
          <span className="min-w-0 flex-1"><span className="flex flex-wrap items-center gap-2"><span className="font-serif text-xl leading-snug text-primary">{tracker.name}</span>{tracker.isExample && <StatusBadge tone="neutral">{t.trackers.example}</StatusBadge>}<StatusBadge>{t.trackers.active}</StatusBadge></span><span className="mt-1 block text-sm text-text-muted">{tracker.location || t.trackers.locationMissing}</span><span className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-xs text-text-subtle"><span>{tracker.topics.length} {t.trackers.topics.toLowerCase()}</span><span>{t.trackers.availableThrough(formatSnapshotDate(tracker.dataThrough, locale))}</span></span></span>
          <svg {...iconProps} className="h-5 w-5 shrink-0 text-text-subtle transition-transform duration-200 group-hover:translate-x-1 group-hover:text-primary motion-reduce:transition-none" aria-hidden="true"><path d="m9 6 6 6-6 6" /></svg>
        </button></CivicSurface>
      ))}
    </div></div>
  );
}

function TrackerDetail({ tracker, project, onBack, onUpdate, onRemove }: { tracker: PlanTracker; project?: ProjectSummary; onBack: () => void; onUpdate: (tracker: PlanTracker) => void; onRemove: () => void }) {
  const { t, locale } = useI18n();
  const [draft, setDraft] = useState(tracker);
  const [isEditing, setIsEditing] = useState(false);
  useEffect(() => { setDraft(tracker); setIsEditing(false); }, [tracker]);
  const save = () => { onUpdate(draft); setIsEditing(false); };
  const hasConsiderations = draft.risks.length > 0 || draft.opportunities.length > 0;

  return (
    <article className="mx-auto w-full max-w-4xl px-4 pb-12 pt-5 sm:px-8 sm:pt-7">
      <button type="button" onClick={onBack} className="inline-flex min-h-11 items-center gap-2 rounded-[5px] px-2 text-sm font-semibold text-primary hover:bg-primary-50 focus-visible:outline-2 focus-visible:outline-primary"><span aria-hidden="true">←</span>{t.trackers.backToTrackers}</button>
      <div className="mt-4 flex flex-wrap items-start justify-between gap-5"><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><StatusBadge>{t.trackers.active}</StatusBadge>{draft.isExample && <StatusBadge tone="neutral">{t.trackers.example}</StatusBadge>}</div>{isEditing ? <input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} aria-label={t.trackers.name} className="mt-3 w-full border-b border-border-strong bg-transparent font-serif text-3xl leading-tight text-primary outline-none focus:border-primary sm:text-4xl" /> : <h2 className="mt-3 font-serif text-3xl leading-tight text-primary sm:text-4xl">{draft.name}</h2>}{project && <p className="mt-2 text-sm text-text-subtle">{t.trackers.fromProject(project.name)}</p>}<TitleRule className="mt-4" /></div>{!isEditing && <button type="button" onClick={() => setIsEditing(true)} className="min-h-11 rounded-[5px] border border-primary px-4 text-sm font-semibold text-primary hover:bg-primary-50 focus-visible:outline-2 focus-visible:outline-primary">{t.trackers.adjust}</button>}</div>

      <CivicSurface className="mt-7 p-5 sm:p-6"><div className="grid gap-6 sm:grid-cols-2">
        {isEditing ? <><label><span className="text-sm font-semibold text-text-subtle">{t.trackers.plan}</span><input value={draft.plan} onChange={(event) => setDraft({ ...draft, plan: event.target.value })} placeholder={t.trackers.planPlaceholder} className="mt-2 min-h-11 w-full rounded-[5px] border border-border-strong px-3 text-sm outline-none focus:border-primary" /></label><label><span className="text-sm font-semibold text-text-subtle">{t.trackers.location}</span><input value={draft.location} onChange={(event) => setDraft({ ...draft, location: event.target.value })} placeholder={t.trackers.locationPlaceholder} className="mt-2 min-h-11 w-full rounded-[5px] border border-border-strong px-3 text-sm outline-none focus:border-primary" /></label><label className="sm:col-span-2"><span className="text-sm font-semibold text-text-subtle">{t.trackers.summary}</span><textarea value={draft.summary} onChange={(event) => setDraft({ ...draft, summary: event.target.value })} placeholder={t.trackers.summaryPlaceholder} rows={3} className="mt-2 w-full resize-y rounded-[5px] border border-border-strong px-3 py-2.5 text-sm leading-relaxed outline-none focus:border-primary" /></label></> : <><div><p className="text-sm font-semibold text-text-subtle">{t.trackers.plan}</p><p className="mt-2 leading-relaxed text-text">{draft.plan || "—"}</p></div><div><p className="text-sm font-semibold text-text-subtle">{t.trackers.location}</p><p className="mt-2 leading-relaxed text-text">{draft.location || "—"}</p></div><div className="sm:col-span-2"><p className="text-sm font-semibold text-text-subtle">{t.trackers.summary}</p><p className="mt-2 leading-relaxed text-text-muted">{draft.summary || "—"}</p></div></>}
      </div></CivicSurface>

      <CivicSurface className="mt-4 flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between"><div><h3 className="font-serif text-lg text-primary">{t.trackers.freshness}</h3><p className="mt-1 text-sm text-text-muted">{t.trackers.availableThrough(formatSnapshotDate(draft.dataThrough, locale))}</p></div><StatusBadge tone="gold">{t.trackers.notLive}</StatusBadge></CivicSurface>
      <CivicSurface className="mt-4 p-5 sm:p-6"><h3 className="font-serif text-xl text-primary">{t.trackers.topics}</h3><div className="mt-4">{isEditing ? <TagEditor items={draft.topics} onChange={(topics) => setDraft({ ...draft, topics })} /> : <div className="flex flex-wrap gap-2">{draft.topics.map((topic) => <TopicChip key={topic}>{topic}</TopicChip>)}</div>}</div></CivicSurface>
      <CivicSurface className="mt-4 p-5 sm:p-6"><h3 className="font-serif text-xl text-primary">{t.trackers.updates}</h3><div className="mt-4 flex gap-3 rounded-[5px] bg-background-secondary/70 p-4 text-sm leading-relaxed text-text-muted"><span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-accent" aria-hidden="true" /><p>{t.trackers.noUpdates}</p></div></CivicSurface>

      {hasConsiderations && <div className="mt-4 grid gap-4 md:grid-cols-2">{draft.risks.length > 0 && <CivicSurface className="p-5"><h3 className="font-serif text-lg text-primary">{t.trackers.risks}</h3><ul className="mt-3 space-y-2">{draft.risks.map((item) => <li key={item} className="flex gap-2 text-sm text-text-muted"><span className="text-danger" aria-hidden="true">—</span>{item}</li>)}</ul></CivicSurface>}{draft.opportunities.length > 0 && <CivicSurface className="p-5"><h3 className="font-serif text-lg text-primary">{t.trackers.opportunities}</h3><ul className="mt-3 space-y-2">{draft.opportunities.map((item) => <li key={item} className="flex gap-2 text-sm text-text-muted"><span className="text-primary" aria-hidden="true">+</span>{item}</li>)}</ul></CivicSurface>}</div>}

      <div className="mt-6 flex flex-wrap items-center justify-between gap-4 border-t border-border/70 pt-5"><p className="max-w-2xl text-xs leading-relaxed text-text-subtle">{t.trackers.prototypeNote}</p><div className="flex items-center gap-2"><button type="button" onClick={onRemove} className="min-h-11 rounded-[5px] px-3 text-sm font-medium text-text-subtle hover:bg-danger-light hover:text-danger">{t.trackers.remove}</button>{isEditing && <button type="button" onClick={save} className="min-h-11 rounded-[5px] bg-primary px-5 text-sm font-semibold text-white hover:bg-primary-dark">{t.trackers.save}</button>}</div></div>
    </article>
  );
}

export default function TrackersView({ trackers, selectedId, projects, isCreating, creationProject, onSelect, onBackToList, onStartCreate, onCancelCreate, onCompleteCreate, onUpdate, onRemove }: TrackersViewProps) {
  const { t } = useI18n();
  const selected = trackers.find((tracker) => tracker.id === selectedId);
  return (
    <div className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-background-canvas">
      <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 bottom-0 hidden items-end justify-between px-6 text-primary opacity-[0.055] xl:flex"><TriumphalArchArt className="h-44" /><CityGatesArt className="h-56" /></div>
      <header className="relative border-b border-border/80 bg-background/95 px-4 py-5 sm:px-8"><div className="mx-auto flex max-w-4xl flex-wrap items-center justify-between gap-4"><div><p className="text-sm font-semibold text-primary">{t.trackers.eyebrow}</p><h1 className="mt-1 font-serif text-2xl text-primary sm:text-3xl">{t.trackers.title}</h1><p className="mt-1 max-w-2xl text-sm leading-relaxed text-text-muted">{t.trackers.description}</p></div>{!isCreating && <button type="button" onClick={onStartCreate} className="inline-flex min-h-11 items-center gap-2 rounded-[5px] bg-primary px-4 text-sm font-semibold text-white transition-colors duration-200 hover:bg-primary-dark focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary motion-reduce:transition-none"><svg {...iconProps} className="h-4 w-4"><path d="M12 5v14M5 12h14" /></svg>{t.trackers.newTracker}</button>}</div></header>
      <div className="relative min-h-0 flex-1 overflow-y-auto">{isCreating ? <TrackerConversation project={creationProject} onCancel={onCancelCreate} onComplete={onCompleteCreate} /> : selected ? <TrackerDetail tracker={selected} project={projects.find((project) => project.id === selected.projectId)} onBack={onBackToList} onUpdate={onUpdate} onRemove={() => onRemove(selected.id)} /> : <TrackerList trackers={trackers} onSelect={onSelect} onCreate={onStartCreate} />}</div>
    </div>
  );
}
