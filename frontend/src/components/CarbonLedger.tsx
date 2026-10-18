import type { Figure } from "../api";
import type { Ledger, Verdict } from "../fleetApi";
import { RangeBar } from "./RangeBar";
import { SectionHead } from "./SectionHead";
import { Stamp } from "./Stamp";
import { Tile } from "./Tile";

const GOALS = [10, 20, 30, 50];
const VERDICT: Record<Verdict, string> = {
  reaches: "Reaches the goal",
  might_reach: "Might reach the goal",
  falls_short: "Falls short of the goal",
};
const one = new Intl.NumberFormat("en-GB", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

export const t1 = (n: number) => one.format(n);
export const span = (f: Figure) => (f.low != null && f.high != null ? `${t1(f.low)} to ${t1(f.high)}` : t1(f.value ?? 0));

interface Props {
  ledger: Ledger;
  goal: number;
  onGoal: (pct: number) => void;
  onOpen: (title: string, shown: string, f: Figure) => void;
}

interface RowProps {
  title: string;
  sub: string;
  pct: Figure;
  verdict: Verdict;
  goal: number;
  onOpen: Props["onOpen"];
}

function GoalRow({ title, sub, pct, verdict, goal, onOpen }: RowProps) {
  const shown = `${span(pct)}% of emissions`;
  return (
    <li className="grid items-center gap-4 py-3 md:grid-cols-[14rem_1fr_15rem]">
      <div>
        <p className="font-bold">{title}</p>
        <p className="font-mono text-xs uppercase tracking-widest text-ink-soft">{sub}</p>
      </div>
      <div className="relative">
        <RangeBar low={pct.low ?? 0} high={pct.high ?? 0} max={100} description={`${title}: ${shown}. ${VERDICT[verdict]}.`} />
        <span aria-hidden="true" className="absolute -inset-y-1.5 w-0.5 bg-ink" style={{ left: `${goal}%` }} />
      </div>
      <button
        onClick={() => onOpen(title, shown, pct)}
        className="btn-link flex flex-col items-start gap-1 text-left"
        aria-label={`${title}: ${shown}, ${VERDICT[verdict]}, ${pct.label}. Show how it was worked out.`}
      >
        <span className="num text-sm underline underline-offset-4">{shown}</span>
        <span className="text-sm font-bold">{VERDICT[verdict]}</span>
        <Stamp label={pct.label} />
      </button>
    </li>
  );
}

// The ledger: tonnes emitted, tonnes avoidable (a range, never added up) and tonnes proven, then the goal check.
export function CarbonLedger({ ledger, goal, onGoal, onOpen }: Props) {
  const { emitted, proven, proven_changes, avoidable, goal: g } = ledger;
  const top = avoidable.top_action;
  const topShown = span(top.co2e_avoided_t);
  const provenShown = span(proven);
  const provenNote = proven_changes.length ? `${proven_changes.length} logged change clearly worked (illustrative)` : "No logged change has clearly worked yet";
  return (
    <>
      <section aria-label="Carbon ledger" className="mx-6 grid gap-3 md:grid-cols-3">
        <Tile highlight title="Emitted" shown={t1(emitted.value ?? 0)} unit="t CO2e" figure={emitted} onOpen={() => onOpen("Emitted", `${t1(emitted.value ?? 0)} t CO2e`, emitted)} />
        <Tile
          title="Avoidable"
          shown={topShown}
          unit="t CO2e"
          note={`Strongest idea: ${top.name}`}
          figure={top.co2e_avoided_t}
          onOpen={() => onOpen(`Avoidable: ${top.name}`, `${topShown} t CO2e a year`, top.co2e_avoided_t)}
        />
        <Tile
          title="Proven"
          shown={provenShown}
          unit="t CO2e"
          note={provenNote}
          figure={proven}
          onOpen={() => onOpen("Proven", `${provenShown} t CO2e`, proven)}
        />
      </section>
      <p className="mx-6 -mt-6">
        <a href="#/proof" className="btn-link inline-flex min-h-11 items-center text-sm underline underline-offset-4">
          See the before-and-after proof
        </a>
      </p>

      <section className="px-6" aria-labelledby="h-goal">
        <SectionHead id="h-goal" title="Goal" tone="mark" note="share of fleet emissions" />
        <div className="mb-2 flex flex-wrap items-center gap-2" role="group" aria-label="Reduction goal">
          <span className="mr-2">Cut emissions by</span>
          {GOALS.map((p) => (
            <button
              key={p}
              onClick={() => onGoal(p)}
              aria-pressed={p === goal}
              className={`btn-tab min-h-11 border-2 px-4 font-mono text-sm ${p === goal ? "border-ink bg-ink font-bold text-paper" : "border-rule hover:border-ink"}`}
            >
              {p}%
            </button>
          ))}
          <button onClick={() => onOpen("Goal", `${t1(g.target_co2e.value ?? 0)} t CO2e`, g.target_co2e)} className="btn-link ml-2 text-sm underline underline-offset-4">
            That is {t1(g.target_co2e.value ?? 0)} t CO2e
          </button>
        </div>
        <ul className="divide-y divide-rule">
          <GoalRow title="Strongest idea" sub={top.name} pct={g.top_action_pct} verdict={g.top_action_verdict} goal={g.target_pct} onOpen={onOpen} />
          <GoalRow title="All ideas that fit" sub="includes the switch to HVO fuel" pct={g.combined_pct} verdict={g.combined_verdict} goal={g.target_pct} onOpen={onOpen} />
          <GoalRow title="Ideas that burn less fuel" sub="without the HVO switch" pct={g.burn_less_pct} verdict={g.burn_less_verdict} goal={g.target_pct} onOpen={onOpen} />
        </ul>
        <p className="mt-3 max-w-[70ch] text-sm text-ink-soft">
          The black line is the goal. Ideas cover {Math.round(avoidable.covered_share_pct)}% of the fleet&apos;s emissions. {avoidable.not_covered} Effects overlap, so
          these are not added: each combined bar runs from the largest single idea to the best idea of each overlapping group, combined as shares of what is left.
        </p>
      </section>
    </>
  );
}
