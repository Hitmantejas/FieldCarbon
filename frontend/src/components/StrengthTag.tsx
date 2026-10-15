import type { Intervention } from "../api";

const STRENGTH = {
  strong: { text: "Strong evidence", form: "border-2 border-moss bg-moss text-paper" },
  moderate: { text: "Moderate evidence", form: "border-2 border-moss text-moss" },
  limited: { text: "Limited evidence", form: "border-2 border-dashed border-ink-soft" },
};

export function StrengthTag({ robustness, n }: { robustness: Intervention["robustness"]; n: number }) {
  const s = STRENGTH[robustness];
  return (
    <span className={`inline-block whitespace-nowrap rounded-full px-3 py-1 font-mono text-xs uppercase tracking-widest ${s.form}`}>
      {s.text} · {n} {n === 1 ? "source" : "sources"}
    </span>
  );
}
