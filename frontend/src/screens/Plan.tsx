import { useState, type CSSProperties } from "react";
import { useApi, type Figure, type Intervention } from "../api";
import { gbpFull, litres } from "../format";
import { RangeBar } from "../components/RangeBar";
import { Stamp } from "../components/Stamp";
import { WorkingSheet, type Opened } from "../components/WorkingSheet";

const step = (i: number) => ({ "--i": i }) as CSSProperties;

const STRENGTH = {
  strong: { text: "Strong evidence", form: "border-2 border-ink bg-ink text-paper" },
  moderate: { text: "Moderate evidence", form: "border-2 border-ink" },
  limited: { text: "Limited evidence", form: "border-2 border-dashed border-ink-soft" },
};

// Names a farmer would use. The data keeps the research wording.
const PLAIN_NAME: Record<string, string> = {
  reduced_tillage: "Reduced tillage (plough less)",
  no_till: "No-till (no ploughing at all)",
  shift_up_throttle_down: "Change up a gear and ease the throttle back",
  hvo_switch: "Switch to HVO (a cleaner diesel)",
  correct_tyre_pressure: "Set the right tyre pressure",
  central_tyre_inflation: "Central tyre inflation (change pressure from the cab)",
  avoid_liquid_ballast: "Stop using liquid weights in the tyres",
  electric_tractor: "Electric tractor (small)",
};
const plain = (i: { intervention_id: string; name: string }) => PLAIN_NAME[i.intervention_id] ?? i.name;

// What we would ask the farmer, and when the idea then applies. Answering is not built yet.
const INPUTS: Record<string, { question: string; appliesIf: string }> = {
  tyre_pressure_checked: {
    question: "Have you checked your tyre pressures against the maker's tables?",
    appliesIf: "you have not checked them",
  },
  has_ctis: {
    question: "Does any of your tractors already have a central tyre inflation system?",
    appliesIf: "none is fitted",
  },
  ballast_type: {
    question: "Do your tractors carry liquid weight (water or fluid) in the tyres?",
    appliesIf: "they do",
  },
};

// The tillage ideas have no yield figures in any source we hold.
const NO_YIELD_FIGURE = new Set(["reduced_tillage", "no_till"]);

const span = (f: Figure, fmt: (n: number) => string) =>
  f.low === f.high ? fmt(f.low!) : `${fmt(f.low!)} to ${fmt(f.high!)}`;

const tonnesSpan = (f: Figure) => {
  const t = (kg: number) => (kg / 1000).toFixed(1);
  return f.low === f.high ? t(f.low!) : `${t(f.low!)} to ${t(f.high!)}`;
};

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

function StrengthTag({ item }: { item: Intervention }) {
  const s = STRENGTH[item.robustness];
  return (
    <span className={`inline-block whitespace-nowrap px-2 py-1 font-mono text-xs uppercase tracking-widest ${s.form}`}>
      {s.text} · {item.n_sources} {item.n_sources === 1 ? "source" : "sources"}
    </span>
  );
}

function Saving({ item, scale }: { item: Intervention; scale: number }) {
  const { litres_saved: l, co2e_avoided_kg: c, fuel_gbp_saved: m } = item.figures;
  if (l && l.high! < 0 && c) {
    return (
      <p className="mt-3">
        You would burn about <span className="num">{litres(-l.high!)} litres</span> more fuel a year, but release about{" "}
        <span className="num">{tonnesSpan(c)} tonnes</span> less CO2.
      </p>
    );
  }
  if (!l) {
    return c ? (
      <p className="mt-3">
        You would release about <span className="num">{tonnesSpan(c)} tonnes</span> less CO2 a year.
      </p>
    ) : null;
  }
  return (
    <>
      <p className="mt-3">
        Could save <span className="num bg-mark px-1 text-on-mark">{span(l, litres)} litres</span> of fuel a year.
        {m && <> That is about <span className="num">{span(m, gbpFull)}</span> in fuel</>}
        {c && <> and <span className="num">{tonnesSpan(c)} tonnes</span> of CO2</>}.
      </p>
      <div className="mt-2">
        <RangeBar low={l.low!} high={l.high!} max={scale} description={`Could save ${span(l, litres)} litres a year`} />
      </div>
    </>
  );
}

export function Plan() {
  const { data, error } = useApi<Intervention[]>("/api/farms/a/interventions");
  const [opened, setOpened] = useState<Opened | null>(null);

  if (error) {
    return (
      <div role="alert" className="mx-4 mb-6 border-2 border-ink p-4">
        <p className="font-bold">We could not load the plan.</p>
        <p>{error}. Check the API is running and reload this page.</p>
      </div>
    );
  }
  if (!data) return <p className="px-4 pb-6 text-ink-soft">Loading the plan...</p>;

  const names = Object.fromEntries(data.map((i) => [i.intervention_id, plain(i)]));
  const ready = data.filter((i) => i.state === "feasible");
  const check = data.filter((i) => i.state === "needs_info");
  const no = data.filter((i) => i.state === "not_feasible");
  // Layout scale only: one shared track so the bars compare across ideas.
  const scale = Math.max(1, ...data.map((i) => i.figures.litres_saved?.high ?? 0)) * 1.1;

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

  const item = (i: Intervention) => {
    const input = INPUTS[i.missing_inputs[0]];
    return (
      <li key={i.intervention_id} className="border-b border-rule py-5 last:border-b-0">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <h3 className="text-lg font-bold">{plain(i)}</h3>
          <StrengthTag item={i} />
        </div>

        {i.state === "needs_info" && (
          <p className="mt-3 border-2 border-dashed border-ink-soft p-3">
            <span className="font-bold">A question for you: </span>
            {input?.question ?? i.missing_inputs.join(", ")} If {input?.appliesIf ?? "it fits"}, this idea applies to you.
            You will be able to answer in a later step.
          </p>
        )}

        <Saving item={i} scale={scale} />
        <p className="mt-2 flex items-center gap-3 text-sm text-ink-soft">
          <Stamp label={i.label} /> Our estimate: the real saving could be anywhere in this range.
        </p>

        <p className="mt-3">
          {costLine(i)}{" "}
          {i.figures.cost && (
            <button onClick={() => openCost(i)} className="btn-link underline underline-offset-4">
              Where this cost comes from
            </button>
          )}
        </p>

        {NO_YIELD_FIGURE.has(i.intervention_id) && (
          <p className="mt-2 text-sm">We have no figures on how this changes your crop yield.</p>
        )}
        {i.overlaps.length > 0 && (
          <p className="mt-2 text-sm">
            This works on the same thing as {i.overlaps.map((o) => names[o]).join(" and ")}, so pick just one. Doing more
            than one will not save you more fuel.
          </p>
        )}

        <button
          onClick={() => openWorking(i)}
          className="btn-outline mt-3 min-h-11 border-2 border-ink px-4 font-mono text-xs uppercase tracking-widest"
        >
          How we worked this out
        </button>
      </li>
    );
  };

  return (
    <>
      <section aria-labelledby="plan-h" className="print px-4 pb-6" style={step(3)}>
        <h2 id="plan-h" className="font-display text-4xl font-extrabold uppercase leading-none">
          Plan
        </h2>
        <p className="mt-3 max-w-[65ch]">
          Ways to use less fuel and release less CO2. The ideas with the strongest proof come first, even when another
          idea saves more.
        </p>
        <p className="mt-3 max-w-[65ch] text-sm text-ink-soft">
          Strong evidence means 3 or more separate sources back an idea. Moderate means 2. Limited means 1.
        </p>
        <p className="mt-3">
          <span className="font-bold">
            {ready.length} {ready.length === 1 ? "idea suits" : "ideas suit"} your farm.
          </span>
          {check.length > 0 && <> {check.length} more could suit it, but we need to ask you a question first.</>}
        </p>
      </section>

      {ready.length > 0 && (
        <section aria-labelledby="ready-h" className="print border-t-2 border-dashed border-rule px-4 py-6" style={step(4)}>
          <h2 id="ready-h" className="mb-1 font-mono text-sm uppercase tracking-widest">
            Ideas that suit your farm
          </h2>
          <ul>{ready.map(item)}</ul>
        </section>
      )}

      {check.length > 0 && (
        <section aria-labelledby="check-h" className="print border-t-2 border-dashed border-rule px-4 py-6" style={step(5)}>
          <h2 id="check-h" className="mb-1 font-mono text-sm uppercase tracking-widest">
            We need to ask you something
          </h2>
          <ul>{check.map(item)}</ul>
        </section>
      )}

      {no.length > 0 && (
        <section aria-labelledby="no-h" className="print border-t-2 border-dashed border-rule px-4 py-6" style={step(6)}>
          <h2 id="no-h" className="mb-1 font-mono text-sm uppercase tracking-widest text-ink-soft">
            Not for your farm
          </h2>
          <ul>
            {no.map((i) => (
              <li key={i.intervention_id} className="border-b border-rule py-4 text-ink-soft last:border-b-0">
                <span className="font-bold">{plain(i)}</span>
                <span className="block">{i.reason}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <p className="print px-4 pb-4 text-sm text-ink-soft" style={step(7)}>
        Some of these ideas save fuel in the same way, so their savings cannot be added together to make one total.
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
