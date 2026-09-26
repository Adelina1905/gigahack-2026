interface TitleRuleProps {
  // "light" sits on the blue brand panels, "dark" on white.
  tone?: "light" | "dark";
  className?: string;
}

// The long + short bar that chisinau.md puts under its section titles.
function TitleRule({ tone = "dark", className = "" }: TitleRuleProps) {
  return (
    <span aria-hidden="true" className={`flex items-center gap-2 ${className}`}>
      <span className={`h-[3px] w-10 ${tone === "light" ? "bg-white" : "bg-primary"}`} />
      <span className="h-[3px] w-3 bg-accent" />
    </span>
  );
}

export default TitleRule;
