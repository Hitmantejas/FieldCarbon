import type { Intervention } from "../api";

const STRENGTH = {
  strong: { text: "Strong evidence", form: "border-2 border-ink bg-ink text-paper" },
  moderate: { text: "Moderate evidence", form: "border-2 border-ink" },
  limited: { text: "Limited evidence", form: "border-2 border-dashed border-ink-soft" },
};

export function StrengthTag({ robustness, n }: { robustness: Intervention["robustness"]; n: number }) {
  const s = STRENGTH[robustness];
  return (
    <span className={`inline-block whitespace-nowrap px-2 py-1 font-mono text-xs uppercase tracking-widest ${s.form}`}>
      {s.text} · {n} {n === 1 ? "source" : "sources"}
    </span>
  );
}
