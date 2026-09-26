import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import TitleRule from "../brand/TitleRule";

interface AlertDialogFrameProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
  testId?: string;
  className?: string;
}

// The modal shell of ProjectDialog: portalled to the body, closes on Escape
// or the backdrop, and hands focus back when it unmounts.
function AlertDialogFrame({ title, onClose, children, testId, className = "max-w-sm" }: AlertDialogFrameProps) {
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });

  useEffect(() => {
    const previousFocus = document.activeElement as HTMLElement | null;
    const first = dialogRef.current?.querySelector<HTMLElement>("[data-autofocus]")
      ?? dialogRef.current?.querySelector<HTMLElement>("button, input");
    first?.focus();

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onCloseRef.current();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      previousFocus?.focus?.();
    };
  }, []);

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        data-testid={testId ? `${testId}-backdrop` : undefined}
        className="absolute inset-0 bg-black/40"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`relative flex max-h-[calc(100dvh-2rem)] w-full flex-col overflow-y-auto rounded-sm border border-border bg-background p-5 shadow-lg ${className}`}
      >
        <h2 id={titleId} className="font-serif text-xl leading-tight text-primary">
          {title}
        </h2>
        <TitleRule className="mt-2" />
        {children}
      </div>
    </div>,
    document.body,
  );
}

export default AlertDialogFrame;
