import { useState, type CSSProperties } from "react";
import { useApi, type BreakdownRow, type FarmId, type Figure, type PainPoints, type State, type Summary } from "../api";
import { gbp, litres, pct, tonnes } from "../format";
import { span } from "../planText";
import { Arrow } from "../components/Arrow";
import { CountUp } from "../components/CountUp";
import { RangeBar, ShareBar } from "../components/RangeBar";
import { SectionHead } from "../components/SectionHead";
import { Stamp } from "../components/Stamp";
import { WorkingSheet, type Opened } from "../components/WorkingSheet";

const step = (i: number) => ({ "--i": i }) as CSSProperties;
const TOP_ROWS = 7;

// An estimated job split is a range; a measured or allocated one is a single number.
const litresText = (f: Figure) => (f.low !== null && f.high !== null && f.low !== f.high ? span(f, litres) : litres(f.value!));

interface Props {
  farm: FarmId;
  summary: State<Summary>;
  pain: State<PainPoints>;
  onNext: () => void;
}

export function Farm({ farm, summary, pain, onNext }: Props) {
  const ops = useApi<BreakdownRow[]>(`/api/farms/${farm}/breakdown/operation`);
  const [opened, setOpened] = useState<Opened | null>(null);
  const [showAll, setShowAll] = useState(false);

  const failed = summary.error ?? ops.error ?? pain.error;
  const s = summary.data;

  return (
    <>
      {failed && (
        <div role="alert" className="mx-4 mb-6 border-2 border-ink p-4">
          <p className="font-bold">We could not load your farm's figures.</p>
          <p>
            {failed}. Start the API with <span className="num text-sm">uvicorn backend.api.main:app --port 8080</span>{" "}
            and reload this page.
          </p>
        </div>
      )}

      {s && (
        <section aria-labelledby="fuel-h" className="print px-4 pb-6" style={step(3)}>
          <SectionHead id="fuel-h" title="Fuel used" tone="solid" aside={<Stamp label={s.litres.label} />} />
          <button
            onClick={() =>
              setOpened({ title: "Fuel used", shown: `${litres(s.litres.value!)} litres`, label: s.litres.label, how: s.litres.how,
 sourceIds: s.litres.source_ids, })
            }
            className="btn-row block w-full text-left"
            aria-label="Fuel used, how it was worked out"
          >
            <span className="flex items-baseline gap-2">
              <span className="font-display text-[7.5rem] font-extrabold leading-[0.9] tracking-tight">
                <CountUp to={s.litres.value!} format={litres} />
              </span>
              <span className="font-display text-3xl font-bold uppercase">litres</span>
            </span>
          </button>
          <p className="mt-3 max-w-[65ch] text-ink-soft">
            {s.farm.description}.{" "}
            {s.hours !== null
              ? `${litres(s.hours)} engine hours; ${litres(s.excluded_hours ?? 0)} h of stuck logger data left out.`
              : `Added up from ${s.receipts} fuel receipts. Receipts do not record engine hours.`}
          </p>

          <dl className="mt-6 space-y-5">
            <button
              onClick={() =>
                setOpened({
                  title: "Emissions",
                  shown: `${tonnes(s.co2e_kg.value!)} CO2e`,
                  label: s.co2e_kg.label,
                  how: s.co2e_kg.how,
 sourceIds: s.co2e_kg.source_ids,
                })
              }
              className="btn-row flex w-full items-end text-left"
            >
              <dt className="font-bold">Emissions</dt>
              <span className="leader" />
              <dd className="num text-lg">{tonnes(s.co2e_kg.value!)} CO2e</dd>
            </button>
            <div>
              <button
                onClick={() =>
                  setOpened({
                    title: "Fuel cost",
                    shown: span(s.cost_gbp, gbp),
                    label: s.cost_gbp.label,
                    how: s.cost_gbp.how,
 sourceIds: s.cost_gbp.source_ids,
                  })
                }
                className="btn-row flex w-full items-end text-left"
              >
                <dt className="font-bold">Fuel cost</dt>
                <span className="leader" />
                <dd className="num text-lg">{span(s.cost_gbp, gbp)}</dd>
              </button>
              {s.cost_gbp.low !== s.cost_gbp.high && (
                <div className="mt-2">
                  <RangeBar
                    low={s.cost_gbp.low!}
                    high={s.cost_gbp.high!}
                    max={s.cost_gbp.high! * 1.15}
                    description={`Cost range ${gbp(s.cost_gbp.low!)} to ${gbp(s.cost_gbp.high!)}`}
                  />
                </div>
              )}
              <p className="mt-2 flex items-center gap-3 text-sm text-ink-soft">
                <Stamp label={s.cost_gbp.label} />{" "}
                {s.cost_gbp.low !== s.cost_gbp.high
                  ? "A range, because the recording has no dates to pick a price from."
                  : "What you paid, from your receipts, before VAT."}
              </p>
            </div>
          </dl>
        </section>
      )}

      {pain.data && (
        <section aria-labelledby="idle-h" className="print border-t-2 border-dashed border-rule px-4 py-6" style={step(4)}>
          <SectionHead id="idle-h" title="Fuel not doing work" tone="mark" aside={<Stamp label={pain.data.not_working.label} />} />
          <p className="mt-2 flex items-baseline gap-3">
            <span className="bg-mark px-2 font-display text-6xl font-extrabold leading-none text-on-mark">
              <CountUp to={pain.data.not_working.share_pct} format={pct} />
            </span>
            <span className="num text-sm text-ink-soft">
              {pain.data.not_working.litres_low !== undefined
                ? `about ${litres(pain.data.not_working.litres_low)} to ${litres(pain.data.not_working.litres_high!)}`
                : litres(pain.data.not_working.litres)}{" "}
              of {litres(pain.data.not_working.total_litres)} L
            </span>
          </p>
          <div className="mt-3">
            <ShareBar
              pct={pain.data.not_working.share_pct}
              description={`${pct(pain.data.not_working.share_pct)} of fuel not doing work`}
            />
          </div>
          <p className="mt-3 max-w-[65ch]">
            {pain.data.not_working.litres_low !== undefined
              ? "Travel between fields, idling and time with the tool not working: what is left after the field jobs. Receipts cannot show it directly, so this is estimated."
              : "The tractor was running with a tool attached but not working, on the road, or idling."}
          </p>
        </section>
      )}

      {ops.data && (
        <section aria-labelledby="ops-h" className="print border-t-2 border-dashed border-rule px-4 py-6" style={step(5)}>
          <SectionHead id="ops-h" title="Where it went" tone="dashed" />
          <ul>
            {(showAll ? ops.data : ops.data.slice(0, TOP_ROWS)).map((r) => (
              <li key={r.key} className="border-b border-rule">
                <button
                  onClick={() =>
                    setOpened({
                      title: r.name,
                      shown: `${litresText(r.litres)} litres, ${pct(r.share_pct)}`,
                      label: r.litres.label,
                      how: r.litres.how,
 sourceIds: r.litres.source_ids,
                    })
                  }
                  className="btn-row block min-h-11 w-full py-2 text-left"
                >
                  <span className="flex items-end">
                    <span>{r.name}</span>
                    <span className="leader" />
                    <span className="num">{litresText(r.litres)} L</span>
                  </span>
                  <span className="mt-1 flex items-center gap-3">
                    <span className="block flex-1">
                      <ShareBar pct={r.share_pct} description={`${pct(r.share_pct)} of fuel`} />
                    </span>
                    <Stamp label={r.litres.label} />
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {ops.data.length > TOP_ROWS && (
            <button
              onClick={() => setShowAll(!showAll)}
              className="btn-outline mt-4 min-h-11 w-full border-2 border-ink px-4 font-mono text-xs uppercase tracking-widest"
            >
              {showAll ? "Show fewer" : `Show all ${ops.data.length}`}
            </button>
          )}
        </section>
      )}

      <div className="no-print px-4 pb-6">
        <button
          onClick={onNext}
          className="btn-solid flex min-h-14 w-full items-center justify-between border-2 border-ink bg-ink px-4 font-mono text-sm uppercase tracking-widest text-paper"
        >
          Next: Pain points
          <Arrow />
        </button>
      </div>

      <WorkingSheet opened={opened} onClose={() => setOpened(null)} />
    </>
  );
}
