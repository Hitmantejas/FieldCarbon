import type { CSSProperties } from "react";
import { query, useApi, type Answers, type FarmId, type Sharpen as SharpenData, type SharpenQuestion } from "../api";
import { litres } from "../format";
import { QUESTIONS, plain } from "../names";
import { span } from "../planText";
import { Arrow } from "../components/Arrow";
import { QuestionBox } from "../components/QuestionBox";
import { RangeBar } from "../components/RangeBar";
import { Rich } from "../components/Rich";
import { SectionHead } from "../components/SectionHead";
import { Stamp } from "../components/Stamp";

const step = (i: number) => ({ "--i": i }) as CSSProperties;

interface Props {
  farm: FarmId;
  pct: number | null;
  answers: Answers;
  unsure: Partial<Record<keyof Answers, boolean>>;
  onAnswer: (field: keyof Answers, value: boolean | string | undefined) => void;
  onNext: () => void;
}

const answerText = (field: keyof Answers, value: boolean | string) =>
  [QUESTIONS[field].yes, QUESTIONS[field].no].find((o) => o.value === value)?.label ?? String(value);

export function Sharpen({ farm, pct, answers, unsure, onAnswer, onNext }: Props) {
  const { data, error } = useApi<SharpenData>(`/api/farms/${farm}/sharpen${query({ target_pct: pct ?? undefined, ...answers })}`);

  if (error && !data) {
    return (
      <div role="alert" className="mx-4 mb-6 border-2 border-ink p-4">
        <p className="font-bold">We could not load this screen.</p>
        <p>{error}. Check the API is running and reload this page.</p>
      </div>
    );
  }
  if (!data) return <p className="px-4 pb-6 text-ink-soft">Working out which question helps most...</p>;

  const [top, ...others] = data.questions;
  const answered = (Object.keys(answers) as (keyof Answers)[]).filter((f) => answers[f] !== undefined);

  // What each possible answer would do to the idea this question belongs to.
  const outcomes = (q: SharpenQuestion) => (
    <ul className="mt-3 space-y-3">
      {q.outcomes.map((o) => (
        <li key={String(o.answer)} className="border-l-4 border-ink pl-3">
          <p className="font-bold">If you answer: {answerText(q.field, o.answer)}</p>
          {o.applies && o.litres_saved ? (
            <>
              <p>
                {plain(q)} could save <span className="num bg-mark px-1 text-on-mark">{span(o.litres_saved, litres)} litres</span> a year.
              </p>
              <RangeBar low={o.litres_saved.low!} high={o.litres_saved.high!} max={o.litres_saved.high! * 1.1} description={`Could save ${span(o.litres_saved, litres)} litres a year`} />
            </>
          ) : (
            <p>This idea drops out of your plan.</p>
          )}
        </li>
      ))}
    </ul>
  );

  return (
    <>
      <section aria-labelledby="sharpen-h" className="print px-4 pb-6" style={step(3)}>
        <h2 id="sharpen-h" className="font-display text-4xl font-extrabold uppercase leading-none">
          Make it more certain
        </h2>
        <p className="mt-3 max-w-[65ch]">
          Some answers only you know. These questions would change your plan, the most useful one first.
        </p>
      </section>

      {top ? (
        <section aria-labelledby="top-h" className="print border-t-2 border-dashed border-rule px-4 py-6" style={step(4)}>
          <SectionHead id="top-h" title="The one that helps most" tone="solid" />
          <h3 className="text-xl font-bold">{plain(top)}</h3>
          <QuestionBox field={top.field} answer={answers[top.field]} unsure={unsure[top.field]} onAnswer={onAnswer} />
          <div className="mt-4 flex items-center gap-3">
            <p className="font-bold">Why this one</p>
            <Stamp label={top.swing.label} />
          </div>
          <Rich text={top.swing.how} />
          {outcomes(top)}
        </section>
      ) : (
        <section aria-labelledby="done-h" className="print border-t-2 border-dashed border-rule px-4 py-6" style={step(4)}>
          <SectionHead id="done-h" title="Nothing more to ask" tone="mark" />
          <p className="max-w-[65ch]">
            You have answered every question. Your plan is as certain as your answers can make it. What is left is
            uncertainty in the research itself, listed below.
          </p>
        </section>
      )}

      {others.length > 0 && (
        <section aria-labelledby="more-h" className="print border-t-2 border-dashed border-rule px-4 py-6" style={step(5)}>
          <SectionHead id="more-h" title="Other questions" tone="dashed" note={`${others.length}`} />
          <ul>
            {others.map((q) => (
              <li key={q.field} className="border-b border-rule py-5 last:border-b-0">
                <h3 className="text-lg font-bold">{plain(q)}</h3>
                <p className="mt-1">
                  Could save <span className="num">{span(q.swing, litres)} litres</span> a year if it applies to you.
                </p>
                <QuestionBox field={q.field} answer={answers[q.field]} unsure={unsure[q.field]} onAnswer={onAnswer} />
              </li>
            ))}
          </ul>
        </section>
      )}

      {answered.length > 0 && (
        <section aria-labelledby="ans-h" className="print border-t-2 border-dashed border-rule px-4 py-6" style={step(6)}>
          <SectionHead id="ans-h" title="Your answers" tone="muted" note={`${answered.length}`} />
          <ul>
            {answered.map((f) => (
              <li key={f} className="border-b border-rule py-3 last:border-b-0">
                <p>{QUESTIONS[f].question}</p>
                <p className="font-bold">
                  {answerText(f, answers[f]!)}.{" "}
                  <button onClick={() => onAnswer(f, undefined)} className="btn-link font-normal underline underline-offset-4">
                    Change
                  </button>
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-labelledby="left-h" className="print border-t-2 border-dashed border-rule px-4 py-6" style={step(7)}>
        <SectionHead id="left-h" title="What stays uncertain" tone="dashed" />
        <ul className="list-disc space-y-2 pl-5">
          {data.still_uncertain.map((t) => (
            <li key={t} className="max-w-[65ch]">
              {t}
            </li>
          ))}
        </ul>
      </section>

      <div className="no-print px-4 pb-6">
        <button
          onClick={onNext}
          className="btn-solid flex min-h-14 w-full items-center justify-between border-2 border-ink bg-ink px-4 font-mono text-sm uppercase tracking-widest text-paper"
        >
          Next: Report
          <Arrow />
        </button>
      </div>
    </>
  );
}
