import { useState } from "react";
import type { Answers, Intervention } from "../api";
import { query, useApi } from "../api";
import { QuestionBox } from "../components/QuestionBox";
import { IDEA, QUESTION_FOR } from "../names";
import { SectionHead } from "../components/SectionHead";
import { Stamp } from "../components/Stamp";
import { StrengthTag } from "../components/StrengthTag";
import { RangeBar } from "../components/RangeBar";
import { WorkingSheet, type Opened } from "../components/WorkingSheet";
import type { Benchmark, FleetOpportunities, FleetSummary } from "../fleetApi";
import { gbpFull, litres } from "../format";
import { absRange, co2Text, litresText, moneyText } from "../ranges";

function Loading({ what }: { what: string }) {
  return <p className="font-mono text-sm uppercase tracking-widest text-ink-soft">Loading {what}...</p>;
}

const costText = (i: Intervention) => {
  const c = i.figures.cost;
  if (!c || c.low == null || c.high == null) return i.cost_note || "Cost not yet sourced";
  const money = c.unit.startsWith("GBP per litre") ? `${Math.round(c.low * 100)}p to ${Math.round(c.high * 100)}p` : `${gbpFull(c.low)} to ${gbpFull(c.high)}`;
  return `${money} ${c.unit.replace(/^GBP /, "")}`;
};
const paybackText = (i: Intervention) => {
  const p = i.figures.payback_years;
  return p && p.low != null && p.high != null ? `${p.low.toFixed(1)} to ${p.high.toFixed(1)} years` : null;
};

interface IdeaProps {
  idea: Intervention;
  names: Record<string, string>;
  open: (o: Opened) => void;
  answers: Answers;
  unsure: Partial<Record<keyof Answers, boolean>>;
  onAnswer: (field: keyof Answers, value: boolean | string | undefined) => void;
}

function Idea({ idea, names, open, answers, unsure, onAnswer }: IdeaProps) {
  const [more, setMore] = useState(false);
  const lit = idea.figures.litres_saved;
  const co2 = idea.figures.co2e_avoided_kg;
  const money = idea.figures.fuel_gbp_saved;
  const sources = [...new Set(Object.values(idea.figures).flatMap((f) => (f && typeof f === "object" ? f.source_ids : [])))];
  const showWorking = () =>
    open({ title: idea.name, shown: co2Text(co2), label: idea.label, how: idea.how, sourceIds: sources, evidence: idea.evidence });
  const payback = paybackText(idea);
  const text = IDEA[idea.intervention_id];
  const field = QUESTION_FOR[idea.intervention_id];
  return (
    <li className="py-7">
      <div className="flex flex-wrap items-center gap-3">
        <h3 className="font-display text-2xl font-semibold leading-tight">{idea.name}</h3>
        <StrengthTag robustness={idea.robustness} n={idea.n_sources} />
        <Stamp label={idea.label} />
      </div>
      {text && (
        <dl className="mt-4 grid max-w-[75ch] gap-x-6 gap-y-2 sm:grid-cols-[6.5rem_minmax(0,1fr)]">
          <dt className="font-bold">What it is</dt>
          <dd>{text.summary}</dd>
          {idea.state !== "not_feasible" && (
            <>
              <dt className="font-bold">What to do</dt>
              <dd>{text.action}</dd>
            </>
          )}
        </dl>
      )}
      {idea.state === "not_feasible" ? (
        <p className="mt-2 max-w-[70ch] text-ink-soft">{idea.reason}</p>
      ) : (
        <>

          <div className="mt-6">
            <p className="font-mono text-xs uppercase tracking-widest text-ink-soft">If this is done, each year</p>
            <dl className="mt-2 grid gap-x-8 gap-y-2 sm:grid-cols-[13rem_1fr]">
              <dt className="font-bold">{lit && lit.high != null && lit.high < 0 ? "Extra fuel burned" : "Fuel saved"}</dt>
              <dd className="num">{litresText(lit)}</dd>
              <dt className="font-bold">Emissions avoided</dt>
              <dd className="num">{co2Text(co2)}</dd>
              <dt className="font-bold">{money && money.high != null && money.high < 0 ? "Fuel bill goes up by" : "Money saved on fuel"}</dt>
              <dd className="num">{money && money.high != null && money.high < 0 ? absRange(money, gbpFull) : moneyText(money)}</dd>
            </dl>
          </div>
          {co2 && co2.low != null && co2.high != null && (
            <div className="mt-4 max-w-xl">
              <RangeBar low={co2.low} high={co2.high} max={Math.max(co2.high, 1)} description={`${idea.name}: ${co2Text(co2)} a year`} />
            </div>
          )}
        </>
      )}
      {field && (idea.state === "needs_info" || answers[field] !== undefined) && (
        <QuestionBox field={field} answer={answers[field]} unsure={unsure[field]} onAnswer={onAnswer} />
      )}
      <div className="mt-5 flex flex-wrap gap-3">
        <button onClick={showWorking} className="btn-outline min-h-11 border-2 border-ink px-4 text-sm font-bold">
          How this was worked out
        </button>
        {idea.state !== "not_feasible" && (
          <button onClick={() => setMore((v) => !v)} aria-expanded={more} className="btn-outline min-h-11 border-2 border-ink px-4 text-sm font-bold">
            {more ? "Hide details" : "Show details"}
          </button>
        )}
      </div>
      {more && (
        <dl className="mt-5 grid max-w-[70ch] gap-x-8 gap-y-2 border-l-4 border-mark pl-4 sm:grid-cols-[9rem_minmax(0,1fr)]">
          <dt className="font-bold">Cost</dt>
          <dd>{costText(idea)}</dd>
          {payback && (
            <>
              <dt className="font-bold">Pays back in</dt>
              <dd className="num">{payback}</dd>
            </>
          )}
          {idea.overlaps.length > 0 && (
            <>
              <dt className="font-bold">Overlaps with</dt>
              <dd>{idea.overlaps.map((o) => names[o] ?? o).join(", ")}. Do not add their savings together.</dd>
            </>
          )}
          {idea.missing_inputs.length > 0 && (
            <>
              <dt className="font-bold">Missing</dt>
              <dd>{idea.missing_inputs.map((m) => m.replace(/_/g, " ")).join(", ")}</dd>
            </>
          )}
          {idea.notes && (
            <>
              <dt className="font-bold">Note</dt>
              <dd>{idea.notes}</dd>
            </>
          )}
        </dl>
      )}
    </li>
  );
}

export function Opportunities() {
  const sites = useApi<FleetSummary>("/api/fleet/summary?group_by=site");
  const [site, setSite] = useState<string>("");
  const [answers, setAnswers] = useState<Answers>({});
  // "Not sure" is kept so the card can say so, but it is no answer, so it never goes to the API.
  const [unsure, setUnsure] = useState<Partial<Record<keyof Answers, boolean>>>({});
  const ideas = useApi<FleetOpportunities>(`/api/fleet/opportunities${query({ site_id: site || undefined, ...answers })}`);
  const bench = useApi<Benchmark>(`/api/fleet/benchmark${query({ site_id: site || undefined })}`);

  const onAnswer = (field: keyof Answers, value: boolean | string | undefined) => {
    setAnswers((a) => {
      const next = { ...a } as Record<string, unknown>;
      if (value === undefined || value === "unsure") delete next[field];
      else next[field] = value;
      return next as Answers;
    });
    setUnsure((u) => {
      const next = { ...u };
      if (value === "unsure") next[field] = true;
      else delete next[field];
      return next;
    });
  };
  const [opened, setOpened] = useState<Opened | null>(null);

  const names = Object.fromEntries((ideas.data?.ideas ?? []).map((i) => [i.intervention_id, i.name]));
  const ready = (ideas.data?.ideas ?? []).filter((i) => i.state === "feasible");
  const waiting = (ideas.data?.ideas ?? []).filter((i) => i.state === "needs_info");
  const no = (ideas.data?.ideas ?? []).filter((i) => i.state === "not_feasible");
  const flagged = (bench.data?.groups ?? [])
    .flatMap((g) => g.peers.filter((p) => p.above_peers).map((p) => ({ g, p })))
    .sort((a, b) => (b.p.litres_at_stake.high ?? 0) - (a.p.litres_at_stake.high ?? 0));

  return (
    <div className="space-y-10 pb-10">
      <section className="px-6 pt-6" aria-labelledby="h-opp">
        <h1 id="h-opp" className="rise font-display text-5xl font-semibold leading-[1.02] sm:text-6xl tracking-tight" style={{ "--i": 1 } as React.CSSProperties}>
          Opportunities
        </h1>
        <p className="mt-3 max-w-[70ch] text-ink-soft">
          Two kinds of lead. Ideas from published research, applied to the fuel your machines really burned. And machines that burn more than
          others doing the same job. Savings are ranges, and ideas overlap, so they are never added together.
        </p>
        <div role="group" aria-label="Which site" className="mt-4 flex flex-wrap gap-2 text-sm">
          {[{ key: "", name: "All sites" }, ...(sites.data?.rows ?? [])].map((s) => (
            <button
              key={s.key}
              onClick={() => setSite(s.key)}
              aria-pressed={site === s.key}
              className={`btn-tab min-h-11 border-2 px-4 ${site === s.key ? "border-ink bg-ink font-bold text-paper" : "border-rule hover:border-ink"}`}
            >
              {s.name}
            </button>
          ))}
        </div>
      </section>

      <section className="px-6" aria-labelledby="h-ideas">
        <SectionHead id="h-ideas" title="Ideas from research" tone="mark" note="ranked by strength of evidence" />
        <div className="mb-4 max-w-[75ch] space-y-2">
          <p>
            <strong>How to use this list:</strong> start at the top, where the evidence is strongest. Read <em>What to do</em>, pick one or two ideas,
            and try them on a few jobs before rolling them out.
          </p>
          <p className="text-ink-soft">
            The ranges come from published studies applied to your fleet's fuel. Where an idea needs a fact we do not have, there is a question on
            its card: answer it and the list updates.
          </p>
        </div>
        {!ideas.data ? (
          <Loading what="ideas" />
        ) : ideas.data.reason ? (
          <p className="max-w-[70ch]">{ideas.data.reason}</p>
        ) : (
          <>
            <ul className="divide-y divide-rule">
              {ready.map((i) => (
                <Idea key={i.intervention_id} idea={i} names={names} open={setOpened} answers={answers} unsure={unsure} onAnswer={onAnswer} />
              ))}
            </ul>
            {waiting.length > 0 && (
              <>
                <div className="mt-10">
                  <SectionHead id="h-wait" title="Waiting for an answer" tone="dashed" note="answer the question on each card" />
                </div>
                <ul className="divide-y divide-rule">
                  {waiting.map((i) => (
                    <Idea key={i.intervention_id} idea={i} names={names} open={setOpened} answers={answers} unsure={unsure} onAnswer={onAnswer} />
                  ))}
                </ul>
              </>
            )}
            {no.length > 0 && (
              <>
                <div className="mt-10">
                  <SectionHead id="h-no" title="Does not apply" tone="muted" note="and why" />
                </div>
                <ul className="divide-y divide-rule">
                  {no.map((i) => (
                    <Idea key={i.intervention_id} idea={i} names={names} open={setOpened} answers={answers} unsure={unsure} onAnswer={onAnswer} />
                  ))}
                </ul>
              </>
            )}
          </>
        )}
      </section>

      <section className="px-6" aria-labelledby="h-peers">
        <SectionHead id="h-peers" title="Machines burning more than similar machines" tone="dashed" note="to investigate, not waste" />
        {!bench.data ? (
          <Loading what="peer comparison" />
        ) : (
          <>
            <div className="mb-5 max-w-[75ch] space-y-2">
              <p>
                Each machine is compared only with other machines doing the same job at the same site. The machines listed below burned
                more fuel per hectare than the typical machine for that job.
              </p>
              <p className="text-ink-soft">
                A gap is a reason to look, not proof that fuel was lost: slope, soil, field and tool can all differ. <strong>What to do:</strong> open
                the machine's name to see the numbers, then compare these jobs in the job notes (tool, field, how it was driven). If nothing explains
                the gap, look again next month.
              </p>
            </div>
            {flagged.length === 0 ? (
              <p>No machine is more than {bench.data.settings.flag_pct}% above its peers.</p>
            ) : (
              <div className="overflow-x-auto">
              <table className="w-full text-left">
                <caption className="sr-only">Machines using more fuel per hectare than their peers</caption>
                <thead>
                  <tr className="border-b-2 border-rule font-mono text-xs uppercase tracking-widest text-ink-soft">
                    <th scope="col" className="px-3 py-3 pl-0 font-normal">Machine</th>
                    <th scope="col" className="px-3 py-3 font-normal">Job</th>
                    <th scope="col" className="px-3 py-3 text-right font-normal">This machine<br />(litres per ha)</th>
                    <th scope="col" className="px-3 py-3 text-right font-normal">Typical machine<br />(litres per ha)</th>
                    <th scope="col" className="px-3 py-3 text-right font-normal">Burns more by</th>
                    <th scope="col" className="px-3 py-3 text-right font-normal">Possible saving</th>
                    <th scope="col" className="px-3 py-3 pr-0 font-normal">Label</th>
                  </tr>
                </thead>
                <tbody>
                  {flagged.map(({ g, p }) => (
                    <tr key={g.site_id + g.operation_code + p.machine_id} className="border-b border-rule transition-colors hover:bg-mark/20">
                      <th scope="row" className="px-3 py-4 pl-0 font-bold">
                        <button
                          onClick={() =>
                            setOpened({ title: `${p.machine}: ${g.operation}`, shown: `${litres(p.litres_at_stake.low ?? 0)} to ${litres(p.litres_at_stake.high ?? 0)} L`, label: p.litres_at_stake.label, how: p.litres_at_stake.how, sourceIds: p.litres_at_stake.source_ids })
                          }
                          className="btn-link text-left underline underline-offset-4"
                        >
                          {p.machine}
                        </button>
                      </th>
                      <td className="px-3 py-4">
                        {g.operation}
                        <span className="block font-mono text-xs uppercase tracking-widest text-ink-soft">{g.site}</span>
                      </td>
                      <td className="num px-3 py-4 text-right">{(p.l_per_ha.value ?? 0).toFixed(1)}</td>
                      <td className="num px-3 py-4 text-right">{(g.median_l_per_ha.value ?? 0).toFixed(1)}</td>
                      <td className="num px-3 py-4 text-right">{p.difference_pct.toFixed(0)}%</td>
                      <td className="num whitespace-nowrap px-3 py-4 text-right">{litres(p.litres_at_stake.low ?? 0)} to {litres(p.litres_at_stake.high ?? 0)} L</td>
                      <td className="px-3 py-4 pr-0"><Stamp label={p.litres_at_stake.label} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            )}
            {bench.data.skipped.length > 0 && (
              <details className="mt-4">
                <summary className="min-h-11 font-mono text-xs uppercase tracking-widest">{bench.data.skipped.length} jobs could not be compared</summary>
                <ul className="mt-2 space-y-1 text-sm text-ink-soft">
                  {bench.data.skipped.map((s) => (
                    <li key={s.site_id + s.operation_code}>
                      {s.operation} ({s.site_id}): {s.reason}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </>
        )}
      </section>

      <WorkingSheet opened={opened} onClose={() => setOpened(null)} />
    </div>
  );
}
