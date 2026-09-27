import { useId } from "react";
import { useI18n } from "../i18n/context";
import AlertDialogFrame from "./alerts/AlertDialogFrame";

interface ConfirmDialogProps {
  title: string;
  message: string;
  // Defaults to the shared "Delete" label.
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

// Asks before a destructive action. Mount it only while it is open: it is
// portalled to the body (clear of the sidebar's overflow and transform), puts
// focus on Cancel, cancels on Escape or the backdrop, and hands focus back to
// the button that opened it.
function ConfirmDialog({ title, message, confirmLabel, onConfirm, onCancel }: ConfirmDialogProps) {
  const { t } = useI18n();
  const messageId = useId();

  return (
    <AlertDialogFrame
      title={title}
      onClose={onCancel}
      role="alertdialog"
      describedBy={messageId}
      testId="confirm-dialog"
      className="max-w-sm animate-[fade-in_150ms_ease-out] motion-reduce:animate-none"
    >
      <p id={messageId} className="mt-4 break-words text-sm leading-relaxed text-text-muted">
        {message}
      </p>

      <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <button
          type="button"
          data-autofocus
          onClick={onCancel}
          className="min-h-11 cursor-pointer rounded-[5px] px-4 text-sm font-medium text-text-muted transition-colors duration-200 hover:bg-background-secondary hover:text-text focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary motion-reduce:transition-none sm:min-h-10"
        >
          {t.confirm.cancel}
        </button>
        <button
          type="button"
          onClick={onConfirm}
          className="min-h-11 cursor-pointer rounded-[5px] bg-danger px-4 text-sm font-semibold text-text-inverted transition-colors duration-200 hover:bg-danger/85 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-danger motion-reduce:transition-none sm:min-h-10"
        >
          {confirmLabel ?? t.confirm.delete}
        </button>
      </div>
    </AlertDialogFrame>
  );
}

export default ConfirmDialog;
