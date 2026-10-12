import { useState, type CSSProperties } from "react";
import { query, useApi, type Answers, type Figure, type Goal, type GoalIdea, type Intervention } from "../api";
import { goalText, gbpFull, litres, pctText } from "../format";
import { IDEA, QUESTION_FOR, QUESTIONS, plain } from "../names";
import { GoalBar } from "../components/GoalBar";
import { QuestionBox } from "../components/QuestionBox";
import { SectionHead } from "../components/SectionHead";
import { Stamp } from "../components/Stamp";
import { StrengthTag } from "../components/StrengthTag";
import { VerdictTag } from "../components/VerdictTag";
import { WorkingSheet, type Opened } from "../components/WorkingSheet";

const step = (i: number) => ({ "--i": i }) as CSSProperties;
const PRESETS = [10, 20, 30, 50];

// The tillage ideas have no yield figures in any source we hold.
const NO_YIELD_FIGURE = new Set(["reduced_tillage", "no_till"]);

const span = (f: Figure, fmt: (n: number) => string) =>
  f.low === f.high ? fmt(f.low!) : `${fmt(f.low!)} to ${fmt(f.high!)}`;

const tonnesSpan = (f: Figure) => {
  const t = (kg: number) => (kg / 1000).toFixed(1);
  return f.low === f.high ? t(f.low!) : `${t(f.low!)} to ${t(f.high!)}`;
};

const sizeText = (low: number, high: number) =>
  low === high ? `about ${pctText(low)}%` : `${pctText(low)}% to ${pctText(high)}%`;

function yearsText(low: number, high: number): string {
  const one = (n: number) => (n < 1 ? "under a year" : `${Math.round(n)} ${Math.round(n) === 1 ? "year" : "years"}`);
  if (high < 1) return "under a year";
  if (low >= 1 && Math.round(low) === Math.round(high)) return one(low);
  return low < 1 ? `under a year to ${one(high)}` : `${Math.round(low)} to ${one(high)}`;
}

const perUnit = (f: Figure) => f.unit.replace(/^GBP /, "").replace(", retrofit", "");

// Working the land and sowing: the cost falls when the figures are negative.
function landCost(low: number, high: number): { sentence: string; short: string } {
  const noEquipment = "It does not count the cost of any new equipment, such as a drill: we have no price for that.";
  if (high <= 0) {
    const amount = `${high === 0 ? `up to ${gbpFull(-low)}` : `${gbpFull(-high)} to ${gbpFull(-low)}`} a year`;
    return {
      sentence: `Could cut the cost of working the land and sowing by ${amount}. This includes the fuel you save. ${noEquipment}`,
      short: `Cuts yearly costs by ${amount}`,
    };
  }
  const amount = `${gbpFull(Math.max(low, 0))} to ${gbpFull(high)} a year`;
  return { sentence: `Could raise the cost of working the land and sowing by ${amount}. ${noEquipment}`, short: `Raises yearly costs by ${amount}` };
}

// The short figure shown at the top of the cost sheet.
function costShort(item: Intervention): string {
  const f = item.figures;
  if (item.cost_kind === "capex_one_off") return `${span(f.cost!, gbpFull)} ${perUnit(f.cost!)}`;
  const run = f.running_cost_change_gbp!;
  if (item.cost_kind === "operating_cost_per_area_change") return landCost(run.low!, run.high!).short;
  return `${gbpFull(run.low!)} to ${gbpFull(run.high!)} more a year`;
}

function costLine(item: Intervention): string {
  const f = item.figures;
  if (!f.cost) return "We do not have a price for this yet.";
  if (item.cost_kind === "capex_one_off") {
    const buy = `Costs about ${span(f.cost, gbpFull)} ${perUnit(f.cost)}.`;
    if (!f.payback_years) return buy;
    const time = yearsText(f.payback_years.low!, f.payback_years.high!);
    return time === "under a year"
      ? `${buy} It would pay for itself in under a year.`
      : `${buy} It would take about ${time} of fuel savings to pay for itself.`;
  }
  const run = f.running_cost_change_gbp!;
  if (item.cost_kind === "operating_cost_per_area_change") return landCost(run.low!, run.high!).sentence;
  return `Would cost you about ${gbpFull(run.low!)} to ${gbpFull(run.high!)} more a year. We only have a rough price for HVO: ask a fuel supplier for a quote.`;
}

const answerLabel = (field: keyof Answers, value: boolean | string) =>
  [QUESTIONS[field].yes, QUESTIONS[field].no].find((o) => o.value === value)?.label;

interface Common {
  answers: Answers;
  onAnswer: (field: keyof Answers, value: boolean | string | undefined) => void;
}

function YourAnswer({ item, answers, onAnswer }: Common & { item: Intervention }) {
  const field = QUESTION_FOR[item.intervention_id];
  const answer = field ? answers[field] : undefined;
  if (!field || answer === undefined) return null;
  return (
    <p className="mt-2 text-sm">
      You answered: {answerLabel(field, answer)}.{item.state === "feasible" ? " So this idea applies to you." : ""}{" "}
      <button onClick={() => onAnswer(field, undefined)} className="btn-link underline underline-offset-4">
        Change
      </button>
    </p>
  );
}

interface CardProps extends Common {
  unsure: Partial<Record<keyof Answers, boolean>>;
  item: Intervention;
  idea: GoalIdea | undefined;
  target: number;
  scale: number;
  names: Record<string, string>;
  onWorking: (i: Intervention) => void;
  onCost: (i: Intervention) => void;
}

function IdeaCard({ item, idea, target, scale, names, answers, unsure, onAnswer, onWorking, onCost }: CardProps) {
  const [open, setOpen] = useState(false);
  const { litres_saved: l, co2e_avoided_kg: c, fuel_gbp_saved: m } = item.figures;
  const field = QUESTION_FOR[item.intervention_id];
  const maybe = item.state === "needs_info";
  const burnsMore = !!l && l.high! < 0;
  const reach = idea?.reach;
  const panel = `details-${item.intervention_id}`;

  return (
    <li className="border-b border-rule py-5 last:border-b-0">
      <h3 className="text-xl font-bold">{plain(item)}</h3>
      <p className="mt-1 text-ink-soft">{IDEA[item.intervention_id]?.summary}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <StrengthTag robustness={item.robustness} n={item.n_sources} />
        {idea && <VerdictTag verdict={idea.verdict} />}
      </div>

      {maybe && field && <QuestionBox field={field} answer={answers[field]} unsure={unsure[field]} onAnswer={onAnswer} />}
      <YourAnswer item={item} answers={answers} onAnswer={onAnswer} />

      {reach && (
        <>
          <GoalBar
            low={reach.low!}
            high={reach.high!}
            target={target}
            max={scale}
            description={`${plain(item)} could cut ${sizeText(reach.low!, reach.high!)} of your emissions. Your goal is ${goalText(target)}%.`}
          />
          <p className="mt-2 flex flex-wrap items-center gap-3">
            <span>
              {maybe ? "If it applies, it" : "It"} could cut{" "}
              <span className="num bg-mark px-1 text-on-mark">{sizeText(reach.low!, reach.high!)}</span> of your emissions.
            </span>
            <Stamp label={item.label} />
          </p>
        </>
      )}
      {burnsMore && c ? (
        <p className="mt-2">
          You would burn about <span className="num">{litres(-l!.high!)} litres</span> more fuel a year.
        </p>
      ) : (
        l && (
          <p className="mt-2">
            Saves <span className="num">{span(l, litres)} litres</span> of fuel a year
            {m && (
              <>
                , about <span className="num">{span(m, gbpFull)}</span>
              </>
            )}
            .
          </p>
        )
      )}
      {idea?.warning && <p className="mt-2 font-bold">{idea.warning}</p>}

      <button
        aria-expanded={open}
        aria-controls={panel}
        onClick={() => setOpen(!open)}
        className="btn-outline mt-3 min-h-11 border-2 border-ink px-4 font-mono text-xs uppercase tracking-widest"
      >
        {open ? "Hide details" : "Show details"}
      </button>

      {open && (
        <div id={panel} className="mt-4 space-y-4 border-t-2 border-dashed border-rule pt-4">
          <div>
            <h4 className="font-bold">What it is</h4>
            <p className="max-w-[65ch]">{IDEA[item.intervention_id]?.detail}</p>
          </div>
          <div>
            <h4 className="font-bold">What you could save in a year</h4>
            <ul className="mt-1 space-y-1">
              {l && (
                <li>
                  Fuel: <span className="num">{burnsMore ? `${litres(-l.high!)} litres more burned` : `${span(l, litres)} litres`}</span>
                </li>
              )}
              {m && (
                <li>
                  Money: <span className="num">{span(m, gbpFull)}</span>
                </li>
              )}
              {c && (
                <li>
                  CO2: <span className="num">{tonnesSpan(c)} tonnes{burnsMore ? " less" : ""}</span>
                </li>
              )}
            </ul>
          </div>
          <div>
            <h4 className="font-bold">What it costs</h4>
            <p className="max-w-[65ch]">{costLine(item)}</p>
            {item.figures.cost && (
              <button onClick={() => onCost(item)} className="btn-link underline underline-offset-4">
                Where this cost comes from
              </button>
            )}
          </div>
          {NO_YIELD_FIGURE.has(item.intervention_id) && (
            <div>
              <h4 className="font-bold">Your crop yield</h4>
              <p>We have no figures on how this changes it.</p>
            </div>
          )}
          {item.overlaps.length > 0 && (
            <div>
              <h4 className="font-bold">Before you choose</h4>
              <p className="max-w-[65ch]">
                This works on the same thing as {item.overlaps.map((o) => names[o]).join(" and ")}, so pick just one. Doing
                more than one will not save you more fuel.
              </p>
            </div>
          )}
          <button
            onClick={() => onWorking(item)}
            className="btn-outline min-h-11 border-2 border-ink px-4 font-mono text-xs uppercase tracking-widest"
          >
            How we worked this out
          </button>
        </div>
      )}
    </li>
  );
}

interface PlanProps extends Common {
  unsure: Partial<Record<keyof Answers, boolean>>;
  pct: number | null;
  setPct: (n: number) => void;
}

export function Plan({ pct, setPct, answers, unsure, onAnswer }: PlanProps) {
  const ideas = useApi<Intervention[]>(`/api/farms/a/interventions${query({ ...answers })}`);
  const goal = useApi<Goal>(`/api/farms/a/goal${query({ target_pct: pct ?? undefined, ...answers })}`);
  // null = not typed in; a typed value that is not a preset is shown in the box and counts as the chosen goal.
  const [custom, setCustom] = useState<string | null>(null);
  const [opened, setOpened] = useState<Opened | null>(null);

  const failed = (ideas.error || goal.error) && !(ideas.data && goal.data);
  if (failed) {
    return (
      <div role="alert" className="mx-4 mb-6 border-2 border-ink p-4">
        <p className="font-bold">We could not load the plan.</p>
        <p>{ideas.error ?? goal.error}. Check the API is running and reload this page.</p>
      </div>
    );
  }
  if (!ideas.data || !goal.data) return <p className="px-4 pb-6 text-ink-soft">Loading the plan...</p>;

  const g = goal.data;
  const target = g.target_pct;
  const data = ideas.data;
  const verdicts = Object.fromEntries(g.ideas.map((i) => [i.intervention_id, i]));
  const names = Object.fromEntries(data.map((i) => [i.intervention_id, plain(i)]));
  const ready = data.filter((i) => i.state === "feasible");
  const check = data.filter((i) => i.state === "needs_info");
  const no = data.filter((i) => i.state === "not_feasible");
  const options = [...new Set([g.suggested_pct, ...PRESETS])].sort((a, b) => a - b);
  const typedActive = !options.includes(target);
  const shownCustom = custom ?? (typedActive ? goalText(target) : "");
  const customInvalid = custom !== null && custom !== "" && !(Number(custom) >= 1 && Number(custom) <= 90);
  // Layout scale only: one shared track so the bars compare across ideas.
  const scale = Math.max(target, 10, ...g.ideas.map((i) => i.reach?.high ?? 0)) * 1.1;

  const openWorking = (i: Intervention) => {
    const f = i.figures.litres_saved ?? i.figures.co2e_avoided_kg!;
    setOpened({
      title: plain(i),
      shown: i.figures.litres_saved
        ? `${span(i.figures.litres_saved, litres)} litres a year`
        : `${tonnesSpan(i.figures.co2e_avoided_kg!)} tonnes of CO2 a year`,
      label: i.label,
      how: i.how,
      sourceIds: f.source_ids,
      evidence: i.evidence,
    });
  };

  const openCost = (i: Intervention) => {
    const f = i.figures.running_cost_change_gbp ?? i.figures.cost!;
    setOpened({ title: `${plain(i)}: cost`, shown: costShort(i), label: f.label, how: f.how, sourceIds: f.source_ids });
  };

  const card = (i: Intervention) => (
    <IdeaCard
      key={i.intervention_id}
      item={i}
      idea={verdicts[i.intervention_id]}
      target={target}
      scale={scale}
      names={names}
      answers={answers}
      unsure={unsure}
      onAnswer={onAnswer}
      onWorking={openWorking}
      onCost={openCost}
    />
  );

  return (
    <>
      <section aria-labelledby="plan-h" className="print px-4 pb-6" style={step(3)}>
        <h2 id="plan-h" className="font-display text-4xl font-extrabold uppercase leading-none">
          Your plan
        </h2>
        <p className="mt-3 max-w-[65ch]">Pick how much you want to cut. We show which ideas can get you there.</p>

        <p className="mt-5 font-bold">I want to cut my emissions by</p>
        <div role="group" aria-label="Your goal" className="mt-2 flex flex-wrap gap-3">
          {options.map((p) => (
            <button
              key={p}
              aria-pressed={p === target}
              onClick={() => {
                setPct(p);
                setCustom(null);
              }}
              className={`btn-outline min-h-14 min-w-20 border-2 border-ink px-4 font-display text-3xl font-bold ${p === target ? "bg-ink text-paper" : ""}`}
            >
              {p}%
            </button>
          ))}
        </div>
        <label className="mt-3 flex flex-wrap items-center gap-3">
          <span>Or type a number (1 to 90):</span>
          <input
            type="number"
            inputMode="numeric"
            min={1}
            max={90}
            value={shownCustom}
            aria-invalid={customInvalid}
            onChange={(e) => {
              setCustom(e.target.value);
              const n = Number(e.target.value);
              if (e.target.value !== "" && n >= 1 && n <= 90) setPct(n);
            }}
            className={`num min-h-11 w-24 border-2 border-ink px-3 ${typedActive && !customInvalid ? "bg-ink text-paper" : "bg-paper text-ink"}`}
          />
          <span>%</span>
        </label>
        {customInvalid && <p className="mt-1 text-sm font-bold">Please type a number from 1 to 90.</p>}
        <p className="mt-3 max-w-[65ch] text-sm text-ink-soft">{g.suggested_how}</p>

        <p className="mt-5 flex flex-wrap items-center gap-3">
          <span>
            {goalText(target)}% is{" "}
            <span className="num bg-mark px-1 text-on-mark">{(g.target_co2e.value! / 1000).toFixed(1)} tonnes</span> of CO2 a year,
            about <span className="num">{litres(g.target_litres.value!)} litres</span> of diesel.
          </span>
          <Stamp label={g.target_co2e.label} />
        </p>

        <p className="mt-5 font-bold">What can get you to {goalText(target)}%</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {(["reaches", "might_reach", "falls_short"] as const).map((v) => (
            <VerdictTag key={v} verdict={v} count={g.counts[v]} />
          ))}
        </div>

        <div className="mt-5 border-2 border-rule p-3">
          <p className="text-sm font-bold">How to read the bars</p>
          <GoalBar low={20} high={60} target={40} max={80} goalLabel="Your goal" description="Example bar" />
          <p className="mt-2 max-w-[65ch] text-sm">
            The yellow bar is how much an idea could cut. The dashed line is your goal. If the bar reaches the line, the
            idea can get you there.
          </p>
          <p className="mt-1 max-w-[65ch] text-sm text-ink-soft">
            ESTIMATED means we worked it out from research and your own fuel use. The real number can be different.
          </p>
        </div>
      </section>

      {ready.length > 0 && (
        <section aria-labelledby="ready-h" className="print border-t-2 border-dashed border-rule px-4 py-6" style={step(4)}>
          <SectionHead id="ready-h" title="Ready for your farm" tone="solid" note={`${ready.length}`} />
          <ul>{ready.map(card)}</ul>
        </section>
      )}

      {check.length > 0 && (
        <section aria-labelledby="check-h" className="print border-t-2 border-dashed border-rule px-4 py-6" style={step(5)}>
          <SectionHead id="check-h" title="Waiting for your answer" tone="mark" note={`${check.length}`} />
          <p className="mb-2 max-w-[65ch]">
            These ideas only help if something is true on your farm. Answer each question and we will move the idea to
            the right place.
          </p>
          <ul>{check.map(card)}</ul>
        </section>
      )}

      {no.length > 0 && (
        <section aria-labelledby="no-h" className="print border-t-2 border-dashed border-rule px-4 py-6" style={step(6)}>
          <SectionHead id="no-h" title="Not for your farm" tone="muted" note={`${no.length}`} />
          <ul>
            {no.map((i) => (
              <li key={i.intervention_id} className="border-b border-rule py-4 text-ink-soft last:border-b-0">
                <span className="font-bold">{plain(i)}</span>
                <span className="block">{i.reason}</span>
                <YourAnswer item={i} answers={answers} onAnswer={onAnswer} />
              </li>
            ))}
          </ul>
        </section>
      )}

      <p className="print px-4 pb-4 text-sm text-ink-soft" style={step(7)}>
        Some of these ideas do the same job, so their savings do not add up.
      </p>

      <div className="px-4 pb-6">
        <button
          disabled
          className="flex min-h-14 w-full items-center justify-between border-2 border-ink px-4 font-mono text-sm uppercase tracking-widest text-ink-soft"
        >
          <span className="line-through decoration-2">Next: Sharpen</span>
          <span>Next step</span>
        </button>
      </div>

      <WorkingSheet opened={opened} onClose={() => setOpened(null)} />
    </>
  );
}
