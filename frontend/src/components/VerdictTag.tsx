import type { GoalIdea } from "../api";

const VERDICT = {
  reaches: { text: "Gets you there", form: "border-2 border-ink bg-ink text-paper" },
  might_reach: { text: "Might get you there", form: "border-2 border-ink bg-mark text-on-mark" },
  falls_short: { text: "Not enough alone", form: "border-2 border-dashed border-ink-soft" },
};

export function VerdictTag({ verdict, count }: { verdict: GoalIdea["verdict"]; count?: number }) {
  if (verdict === "not_applicable") return null;
  const v = VERDICT[verdict];
  return (
    <span className={`inline-block whitespace-nowrap px-2 py-1 font-mono text-xs uppercase tracking-widest ${v.form}`}>
      {v.text}
      {count !== undefined && ` · ${count}`}
    </span>
  );
}
