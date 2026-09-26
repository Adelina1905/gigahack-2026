import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { createPortal } from "react-dom";
import { useI18n } from "../i18n/context";
import TitleRule from "./brand/TitleRule";

interface ProjectDialogProps {
  title: string;
  submitLabel: string;
  initialName?: string;
  onSubmit: (name: string) => void;
  onCancel: () => void;
}

// Names a new project or renames one. Mount it only while it is open, so the
// name starts from initialName each time.
function ProjectDialog({ title, submitLabel, initialName = "", onSubmit, onCancel }: ProjectDialogProps) {
  const { t } = useI18n();
  const [name, setName] = useState(initialName);
  const inputRef = useRef<HTMLInputElement>(null);
  const titleId = useId();
  const trimmed = name.trim();

  const onCancelRef = useRef(onCancel);
  useEffect(() => {
    onCancelRef.current = onCancel;
  });

  // Focus the name, cancel on Escape wherever focus is, and hand focus back
  // to whatever had it when the dialog closes.
  useEffect(() => {
    const previousFocus = document.activeElement as HTMLElement | null;
    inputRef.current?.focus();
    inputRef.current?.select();

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onCancelRef.current();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      previousFocus?.focus?.();
    };
  }, []);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (trimmed) onSubmit(trimmed);
  };

  // Portalled out of the sidebar, whose transform would otherwise contain it.
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        data-testid="project-dialog-backdrop"
        className="absolute inset-0 bg-black/40"
        onClick={onCancel}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="relative w-full max-w-sm rounded-sm border border-border bg-background p-5 shadow-lg"
      >
        <h2 id={titleId} className="font-serif text-xl leading-tight text-primary">
          {title}
        </h2>
        <TitleRule className="mt-2" />

        <form onSubmit={handleSubmit} className="mt-4">
          <label className="block text-sm font-medium text-text-muted">
            {t.projects.name}
            <input
              ref={inputRef}
              value={name}
              maxLength={255}
              onChange={(e) => setName(e.target.value)}
              placeholder={t.projects.namePlaceholder}
              className="mt-1.5 w-full rounded-sm border border-border-strong bg-background px-3 py-2 text-sm font-normal text-text focus:border-primary focus:outline-none"
            />
          </label>

          <div className="mt-5 flex justify-end gap-2">
            <button
              type="button"
              onClick={onCancel}
              className="cursor-pointer rounded-sm px-3 py-2 text-sm font-medium text-text-muted hover:bg-background-secondary hover:text-text"
            >
              {t.projects.cancel}
            </button>
            <button
              type="submit"
              disabled={!trimmed}
              className="cursor-pointer rounded-sm bg-primary px-4 py-2 text-sm font-semibold text-text-inverted transition-colors hover:bg-primary-dark disabled:cursor-not-allowed disabled:opacity-50"
            >
              {submitLabel}
            </button>
          </div>
        </form>
      </div>
    </div>,
    document.body,
  );
}

export default ProjectDialog;
