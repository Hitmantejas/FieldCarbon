import type { CSSProperties } from "react";
import { query, useApi, type Answers, type FarmId, type Report as ReportData } from "../api";
import { gbpFull, goalText, litres } from "../format";
import { QUESTIONS, plain } from "../names";
import { costLine, tonnesSpan, span } from "../planText";
import { linkText } from "../sources";
import { Rich } from "../components/Rich";
import { SectionHead } from "../components/SectionHead";
import { Stamp } from "../components/Stamp";
import { StrengthTag } from "../components/StrengthTag";
import { VerdictTag } from "../components/VerdictTag";

const step = (i: number) => ({ "--i": i }) as CSSProperties;

const BAND = { above_typical: "Above typical", well_above: "Well above" } as Record<string, string>;

const AGREEMENT: Record<string, string> = {
  true: "Both research tables agree.",
  false: "The two research tables disagree, so we are less sure.",
  null: "Only one research table covers this job.",
};

const answerText = (field: keyof Answers, value: boolean | string) =>
  [QUESTIONS[field].yes, QUESTIONS[field].no].find((o) => o.value === value)?.label ?? String(value);

// A label, a dotted leader and a value: one line of the report.
function Line({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <li className="flex flex-wrap items-end gap-x-2 border-b border-rule py-2 last:border-b-0">
      <span className="font-bold">{label}</span>
      <span className="leader" />
      <span className="flex items-center gap-3">{children}</span>
    </li>
  );
}

export function Report({ farm, pct, answers }: { farm: FarmId; pct: number | null; answers: Answers }) {
  const { data: r, error } = useApi<ReportData>(`/api/farms/${farm}/report${query({ target_pct: pct ?? undefined, ...answers })}`);

  if (error && !r) {
    return (
      <div role="alert" className="mx-4 mb-6 rounded-2xl border-2 border-clay p-4">
        <p className="font-bold">We could not build the report.</p>
        <p>{error}. Check the API is running and reload this page.</p>
      </div>
    );
  }
  if (!r) return <p className="px-4 pb-6 text-ink-soft">Building your report...</p>;

  const when = new Date(r.meta.generated_at).toLocaleString("en-GB", { dateStyle: "long", timeStyle: "short" });
  const given = (Object.keys(r.answers) as (keyof Answers)[]).filter((f) => r.answers[f] !== undefined);
  const section = "rise border-t border-rule px-4 py-6";

  const print = (
    <button
      onClick={() => window.print()}
      className="btn-solid no-print flex min-h-14 w-full items-center justify-center border-2 border-ink bg-ink px-4 text-sm font-bold text-paper"
    >
      Print or save as PDF
    </button>
  );

  return (
    <>
      <section aria-labelledby="report-h" className="rise px-4 pb-6" style={step(3)}>
        <h2 id="report-h" className="font-display text-4xl font-semibold leading-tight">
          {r.meta.title}
        </h2>
        <p className="mt-2 font-bold">
          {r.meta.farm} · {when}
        </p>
        <p className="mt-3 max-w-[65ch]">{r.meta.statement}</p>
        <p className="no-print mt-3 max-w-[65ch] text-sm text-ink-soft">
          Share this with a buyer or adviser. It includes your goal and your answers.
        </p>
        <div className="mt-4">{print}</div>
      </section>

      <section aria-labelledby="nums-h" className={section} style={step(4)}>
        <SectionHead id="nums-h" title="Your numbers" tone="solid" />
        <ul>
          <Line label="Fuel used">
            <span className="num">{litres(r.totals.litres.value!)} litres</span>
            <Stamp label={r.totals.litres.label} />
          </Line>
          <Line label="Emissions">
            <span className="num">{(r.totals.co2e_kg.value! / 1000).toFixed(1)} tonnes of CO2</span>
            <Stamp label={r.totals.co2e_kg.label} />
          </Line>
          <Line label="Fuel cost">
            <span className="num">{span(r.totals.cost_gbp, gbpFull)}</span>
            <Stamp label={r.totals.cost_gbp.label} />
          </Line>
          {r.totals.engine_hours !== null && (
            <Line label="Time worked">
              <span className="num">{litres(r.totals.engine_hours)} hours</span>
            </Line>
          )}
        </ul>
        {r.totals.excluded_hours !== null && (
          <p className="mt-3 max-w-[65ch] text-sm">
            We left out {litres(r.totals.excluded_hours)} hours where the recorder froze.
          </p>
        )}
      </section>

      <section aria-labelledby="went-h" className={section} style={step(5)}>
        <SectionHead id="went-h" title="Where the fuel went" tone="dashed" />
        <ul>
          {r.where_it_went.map((w) => (
            <Line key={w.name} label={w.name}>
              <span className="num">
                {w.litres.low !== null && w.litres.high !== null && w.litres.low !== w.litres.high
                  ? `${litres(w.litres.low)} to ${litres(w.litres.high)}`
                  : litres(w.litres.value!)}{" "}
                litres
              </span>
              <Stamp label={w.litres.label} />
            </Line>
          ))}
        </ul>
      </section>

      <section aria-labelledby="pain-r-h" className={section} style={step(6)}>
        <SectionHead id="pain-r-h" title="Jobs using more fuel than usual" tone="mark" note={`${r.pain_points.length}`} />
        {r.pain_points.length === 0 && <p>{r.pain_points_note ?? "No job is above its typical range."}</p>}
        <ul>
          {r.pain_points.map((p) => (
            <li key={p.name} className="break-inside-avoid border-b border-rule py-4 last:border-b-0">
              <p className="font-bold">
                {p.name} <span className="font-normal">({BAND[p.band]})</span>
              </p>
              <div className="mt-2 grid grid-cols-[auto_1fr] gap-x-6 gap-y-1">
                <span className="font-bold">You</span>
                <span className="num">{p.you_l_per_ha.toFixed(1)} litres per hectare</span>
                <span className="font-bold">Typical</span>
                <span className="num">
                  {p.typical_low.toFixed(1)} to {p.typical_high.toFixed(1)} litres per hectare
                </span>
                <span className="font-bold">Area worked</span>
                <span className="num">{p.hectares.toFixed(0)} hectares</span>
                <span className="font-bold">Could be saved</span>
                <span className="flex items-center gap-3">
                  <span className="num">{span(p.at_stake, litres)} litres</span>
                  <Stamp label={p.at_stake.label} />
                </span>
              </div>
              <p className="mt-2 text-sm">{AGREEMENT[String(p.sources_agree)]}</p>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="plan-r-h" className={section} style={step(7)}>
        <SectionHead id="plan-r-h" title="Your goal and plan" tone="solid" />
        <p className="max-w-[65ch]">
          <span className="font-bold">Goal: cut emissions by {goalText(r.plan.goal.target_pct)}%.</span> That is about{" "}
          {(r.plan.goal.target_co2e.value! / 1000).toFixed(1)} tonnes of CO2 a year, or{" "}
          {litres(r.plan.goal.target_litres.value!)} litres of diesel.
        </p>
        {given.length > 0 && (
          <>
            <h3 className="mt-4 font-bold">What you told us</h3>
            <ul className="mt-1 list-disc space-y-1 pl-5">
              {given.map((f) => (
                <li key={f}>
                  {QUESTIONS[f].question} <span className="font-bold">{answerText(f, r.answers[f]!)}.</span>
                </li>
              ))}
            </ul>
          </>
        )}
        <h3 className="mt-4 font-bold">Ideas that suit your farm</h3>
        <ul>
          {r.plan.ideas.map((i) => {
            const l = i.figures.litres_saved;
            const c = i.figures.co2e_avoided_kg;
            const m = i.figures.fuel_gbp_saved;
            return (
              <li key={i.intervention_id} className="break-inside-avoid border-b border-rule py-4 last:border-b-0">
                <p className="text-lg font-bold">{plain(i)}</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <StrengthTag robustness={i.robustness} n={i.n_sources} />
                  <VerdictTag verdict={i.verdict} />
                </div>
                {l && l.high! < 0 && c ? (
                  <p className="mt-2">
                    You would burn about {litres(-l.high!)} litres more fuel a year, but release about {tonnesSpan(c)} tonnes less CO2.
                  </p>
                ) : (
                  l && (
                    <p className="mt-2">
                      Could save {span(l, litres)} litres of fuel a year
                      {m && <>, about {span(m, gbpFull)}</>}
                      {c && <>, and {tonnesSpan(c)} tonnes of CO2</>}.
                    </p>
                  )
                )}
                <p className="mt-2 max-w-[65ch] text-sm">{costLine(i)}</p>
              </li>
            );
          })}
        </ul>
        {r.plan.waiting > 0 && (
          <p className="mt-3 max-w-[65ch]">
            {r.plan.waiting} more {r.plan.waiting === 1 ? "idea is" : "ideas are"} waiting for an answer from you, so{" "}
            {r.plan.waiting === 1 ? "it is" : "they are"} not counted here.
          </p>
        )}
        <p className="mt-3 max-w-[65ch] text-sm">
          Some of these ideas do the same job, so their savings do not add up.
        </p>
      </section>

      <section aria-labelledby="limits-h" className={section} style={step(8)}>
        <SectionHead id="limits-h" title="What we do not know" tone="muted" />
        <ul className="list-disc space-y-2 pl-5">
          {r.limits.map((t) => (
            <li key={t} className="max-w-[65ch]">
              {t}
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="method-h" className={section} style={step(9)}>
        <SectionHead id="method-h" title="How the numbers were worked out" tone="dashed" />
        <Rich text={r.method} />
        <ul className="mt-4 space-y-2">
          {r.labels.map((l) => (
            <li key={l.label} className="flex flex-wrap items-center gap-3">
              <Stamp label={l.label} />
              <span className="max-w-[55ch]">{l.meaning}</span>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="src-h" className={section} style={step(10)}>
        <SectionHead id="src-h" title="Sources" tone="dashed" note={`${r.sources.length}`} />
        <ul className="space-y-3">
          {r.sources.map((s) => (
            <li key={s.source_id} className="break-inside-avoid text-sm">
              <span className="font-bold">{s.title}</span>
              <span className="block text-ink-soft">
                {[s.publisher_or_authors, s.year].filter(Boolean).join(", ")} · {linkText(s.link_status)}
              </span>
              {s.url && <span className="block break-all">{s.url}</span>}
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="lic-h" className={section} style={step(11)}>
        <SectionHead id="lic-h" title="Data and licence" tone="muted" />
        <ul className="space-y-2 text-sm">
          <li>{r.attribution.dataset}</li>
          <li>Licence: {r.attribution.licence}.</li>
          <li>{r.attribution.attribution}</li>
          <li>Emission factors: {r.attribution.emission_factors}.</li>
        </ul>
        <p className="mt-4 text-sm text-ink-soft">
          Demo data: illustrative. Generated {when}.
        </p>
      </section>

      <div className="px-4 pb-6">{print}</div>
    </>
  );
}
