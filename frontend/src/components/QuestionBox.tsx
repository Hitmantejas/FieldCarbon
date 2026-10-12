import type { Answers } from "../api";
import { QUESTIONS } from "../names";

interface Props {
  field: keyof Answers;
  answer: boolean | string | undefined;
  unsure: boolean | undefined;
  onAnswer: (field: keyof Answers, value: boolean | string | undefined) => void;
}

// The farmer answers here; the plan re-sorts itself with the new answer.
export function QuestionBox({ field, answer, unsure, onAnswer }: Props) {
  const q = QUESTIONS[field];
  const labelId = `q-${field}`;
  return (
    <div role="group" aria-labelledby={labelId} className="mt-3 border-2 border-dashed border-ink p-3">
      <p id={labelId} className="font-bold">
        {q.question}
      </p>
      {q.hint && <p className="text-sm text-ink-soft">{q.hint}</p>}
      <p className="mt-1 max-w-[65ch] text-sm">
        <span className="font-bold">Why we ask: </span>
        {q.why}
      </p>
      <div className="mt-3 flex flex-wrap gap-3">
        {[q.yes, q.no].map((o) => (
          <button
            key={o.label}
            aria-pressed={answer === o.value}
            onClick={() => onAnswer(field, o.value)}
            className={`btn-outline min-h-11 border-2 border-ink px-4 font-mono text-xs uppercase tracking-widest ${answer === o.value ? "bg-ink text-paper" : ""}`}
          >
            {o.label}
          </button>
        ))}
        <button
          aria-pressed={unsure && answer === undefined}
          onClick={() => onAnswer(field, "unsure")}
          className={`btn-outline min-h-11 border-2 border-dashed border-ink px-4 font-mono text-xs uppercase tracking-widest ${unsure && answer === undefined ? "bg-ink text-paper" : ""}`}
        >
          Not sure
        </button>
      </div>
      {unsure && answer === undefined && (
        <p className="mt-3 max-w-[65ch] text-sm font-bold">
          That is fine. This idea stays here until you know. The saving shown is what you would get if it applies.
        </p>
      )}
    </div>
  );
}
