import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { useI18n } from "../i18n/context";
import type { VoiceError, VoicePhase } from "../hooks/useVoiceMode";

interface ChatInputProps {
  onSend: (text: string) => string | null;
  disabled?: boolean;
  placeholder?: string;
  voice: {
    enabled: boolean;
    phase: VoicePhase;
    error: VoiceError | null;
    level: number;
    elapsedSeconds: number;
    toggleEnabled: () => void;
    toggleRecording: () => void;
    cancelRecording: () => void;
    dismissError: () => void;
  };
}

const MAX_HEIGHT_PX = 160; // ~6 lines

function ChatInput({ onSend, disabled = false, placeholder, voice }: ChatInputProps) {
  const { t } = useI18n();
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const voiceBlocksInput = ["requesting", "listening", "transcribing", "waiting", "generating"].includes(voice.phase);
  const canSend = value.trim().length > 0 && value.trim().length <= 8000 && !disabled && !voiceBlocksInput;

  // Grow with content up to MAX_HEIGHT_PX, then scroll.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT_PX)}px`;
  }, [value]);

  const submit = () => {
    if (!canSend) return;
    onSend(value.trim());
    setValue("");
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-3">
        <button
          type="button"
          role="switch"
          aria-checked={voice.enabled}
          onClick={voice.toggleEnabled}
          className="inline-flex items-center gap-2 rounded-sm px-1 py-1 text-xs font-medium text-text-muted hover:text-primary focus-visible:outline-2 focus-visible:outline-primary"
        >
          <span className={`relative h-5 w-9 rounded-full transition-colors ${voice.enabled ? "bg-primary" : "bg-border-strong"}`}>
            <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${voice.enabled ? "translate-x-[18px]" : "translate-x-0.5"}`} />
          </span>
          {t.voice.mode}
        </button>
        {voice.enabled && voice.phase !== "idle" && (
          <div role="status" aria-live="polite" className="flex min-w-0 items-center gap-2 text-xs text-text-muted">
            {voice.phase === "listening" && (
              <span className="h-1.5 w-20 overflow-hidden rounded-full bg-background-secondary">
                <span className="block h-full origin-left bg-accent transition-transform" style={{ transform: `scaleX(${Math.max(0.04, voice.level)})` }} />
              </span>
            )}
            <span>{t.voice.status[voice.phase]}</span>
            {voice.phase === "listening" && <span>{voice.elapsedSeconds}s</span>}
          </div>
        )}
      </div>

      {voice.error && (
        <div role="alert" className="flex items-center justify-between gap-3 rounded-sm border border-danger bg-danger-light px-3 py-2 text-sm text-danger">
          <span>{t.voice.errors[voice.error]}</span>
          <button type="button" onClick={voice.dismissError} aria-label={t.chat.dismissError} className="rounded-sm px-1.5 text-base leading-none hover:bg-background">×</button>
        </div>
      )}

      <div className="flex items-end gap-2 rounded-sm border border-border-strong bg-background py-2 pr-2 pl-3 shadow-sm transition focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/15">
        {voice.enabled && (
          <button
            type="button"
            onClick={voice.toggleRecording}
            disabled={disabled || !["idle", "listening"].includes(voice.phase)}
            aria-label={voice.phase === "listening" ? t.voice.stop : t.voice.start}
            className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-sm transition-colors ${voice.phase === "listening" ? "animate-pulse bg-danger text-white" : "bg-primary/10 text-primary hover:bg-primary/20 disabled:cursor-not-allowed disabled:opacity-40"}`}
          >
            {voice.phase === "listening" ? (
              <span className="h-3 w-3 rounded-[2px] bg-current" />
            ) : (
              <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
                <rect x="9" y="3" width="6" height="11" rx="3" />
                <path d="M5 11a7 7 0 0 0 14 0M12 18v3M9 21h6" />
              </svg>
            )}
          </button>
        )}
        <textarea
          ref={textareaRef}
          rows={1}
          maxLength={8000}
          value={value}
          disabled={disabled || voiceBlocksInput}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={voice.enabled && voice.phase === "listening" ? t.voice.listeningPlaceholder : (placeholder ?? t.chat.placeholder)}
          className="max-h-40 flex-1 resize-none bg-transparent py-1.5 text-base text-text placeholder:text-text-subtle focus:outline-none disabled:opacity-60"
        />
        {voice.phase === "listening" && (
          <button type="button" onClick={voice.cancelRecording} className="h-9 rounded-sm px-2 text-xs text-text-muted hover:bg-background-secondary">
            {t.voice.cancel}
          </button>
        )}
        <button
          type="button"
          onClick={submit}
          disabled={!canSend}
          aria-label={t.chat.send}
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-sm transition-colors ${
            canSend
              ? "bg-primary text-text-inverted hover:bg-primary-dark"
              : "cursor-not-allowed bg-background-secondary text-text-subtle"
          }`}
        >
          <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 19V5M5 12l7-7 7 7" />
          </svg>
        </button>
      </div>
    </div>
  );
}

export default ChatInput;
