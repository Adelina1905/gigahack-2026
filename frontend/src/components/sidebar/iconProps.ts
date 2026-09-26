// Shared stroke style for the sidebar's inline icons.
export const iconProps = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

export const actionButtonClass =
  "cursor-pointer rounded-sm p-1.5 text-text-subtle hover:bg-background hover:text-primary";

export const dangerButtonClass =
  "cursor-pointer rounded-sm p-1.5 text-text-subtle hover:bg-danger-light hover:text-danger";
