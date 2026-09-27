import type { ButtonHTMLAttributes, ReactNode } from "react";

export function CivicSurface({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-[6px] border border-border/80 bg-background shadow-[0_1px_2px_rgba(0,58,141,0.04)] ${className}`}>{children}</div>;
}

export function StatusBadge({ children, tone = "blue" }: { children: ReactNode; tone?: "blue" | "gold" | "neutral" }) {
  const tones = {
    blue: "bg-primary-50 text-primary-700",
    gold: "bg-accent/15 text-primary-900",
    neutral: "bg-background-secondary text-text-muted",
  };
  return <span className={`inline-flex min-h-6 items-center rounded px-2 py-1 text-[11px] font-semibold leading-none ${tones[tone]}`}>{children}</span>;
}

interface TopicChipProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  selected?: boolean;
  interactive?: boolean;
}

export function TopicChip({ children, selected = false, interactive = false, className = "", ...props }: TopicChipProps) {
  const classes = `inline-flex min-h-9 items-center rounded-[5px] border px-3 py-1.5 text-sm transition-[color,background-color,border-color] duration-200 motion-reduce:transition-none ${
    selected ? "border-primary bg-primary text-white" : "border-primary-100 bg-primary-50/70 text-primary-800"
  } ${interactive ? "cursor-pointer hover:border-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary" : ""} ${className}`;

  if (interactive) return <button type="button" aria-pressed={selected} className={classes} {...props}>{children}</button>;
  return <span className={classes}>{children}</span>;
}

export function StepProgress({ current, total, label }: { current: number; total: number; label: string }) {
  return (
    <div className="flex items-center gap-3" aria-label={label}>
      <span className="shrink-0 text-xs font-semibold text-text-muted">{current}/{total}</span>
      <div className="flex flex-1 gap-1.5" aria-hidden="true">
        {Array.from({ length: total }, (_, index) => (
          <span key={index} className={`h-1.5 flex-1 rounded-full transition-colors duration-200 motion-reduce:transition-none ${index < current ? "bg-primary" : "bg-border"}`} />
        ))}
      </div>
    </div>
  );
}

