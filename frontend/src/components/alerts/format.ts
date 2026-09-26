// "YYYY-MM-DD" is a calendar date, so it is read in local time rather than as UTC midnight.
export function formatCalendarDate(value: string | null, locale: string): string {
  if (!value) return "";
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return value;
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return date.toLocaleDateString(locale, { year: "numeric", month: "short", day: "numeric" });
}

export function formatDateTime(timestamp: number, locale: string): string {
  return new Date(timestamp).toLocaleString(locale, {
    day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
  });
}
