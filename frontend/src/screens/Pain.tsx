import { useState, type CSSProperties } from "react";
import type { Band, PainPoints, Rating, State } from "../api";
import { litres, pct } from "../format";
import { BandRange } from "../components/BandRange";
import { Stamp } from "../components/Stamp";
import { WorkingSheet, type Opened } from "../components/WorkingSheet";

const step = (i: number) => ({ "--i": i }) as CSSProperties;

const BAND_TEXT: Record<Band, string> = {
  below_typical: "Below typical",
  typical: "Typical",
  above_typical: "Above typical",
  well_above: "Well above",
  insufficient_data: "Too little data",
  no_reference: "No reference",
};

// The band is carried by the word and the border form: plain, marker, marker with a double border.
const BAND_FORM: Record<Band, string> = {
  below_typical: "border border-ink-soft",
  typical: "border border-ink-soft",
  above_typical: "bg-mark text-on-mark border-2 border-transparent",
  well_above: "bg-mark text-on-mark border-4 border-double border-ink",
  insufficient_data: "border border-dashed border-ink-soft",
  no_reference: "border border-dashed border-ink-soft",
};

const MATCH_NOTE: Record<Rating["match_quality"], string | null> = {
  direct: null,
  closest: "The reference is the closest available job, not an exact match.",
  composite: "The reference adds two jobs together.",
  none: null,
};

function BandTag({ band }: { band: Band }) {
  return (
    <span className={`inline-block whitespace-nowrap px-2 py-1 font-mono text-xs uppercase tracking-widest ${BAND_FORM[band]}`}>
      {BAND_TEXT[band]}
    </span>
  );
}

const range = (r: Rating) => `${r.reference!.low.toFixed(1)} to ${r.reference!.high.toFixed(1)}`;

export function Pain({ pain }: { pain: State<PainPoints> }) {
  const [opened, setOpened] = useState<Opened | null>(null);
  const open = (r: Rating, shown: string) =>
    setOpened({ title: r.display_name, shown, label: r.label, how: r.how });

  if (pain.error) {
    return (
      <div role="alert" className="mx-4 mb-6 border-2 border-ink p-4">
        <p className="font-bold">We could not load the pain points.</p>
        <p>{pain.error}. Check the API is running and reload this page.</p>
      </div>
    );
  }
  if (!pain.data) return <p className="px-4 pb-6 text-ink-soft">Loading pain points...</p>;

  const { ratings, above_range: above, not_working: idle } = pain.data;
  const flagged = ratings.filter((r) => r.band === "above_typical" || r.band === "well_above");
  const fine = ratings.filter((r) => r.band === "typical" || r.band === "below_typical");
  const unrated = ratings.filter((r) => r.band === "insufficient_data" || r.band === "no_reference");

  return (
    <>
      <section aria-labelledby="pain-h" className="print px-4 pb-6" style={step(3)}>
        <h2 id="pain-h" className="font-display text-4xl font-extrabold uppercase leading-none">
          Pain points
        </h2>
        <p className="mt-3 max-w-[65ch]">
          Each job's fuel use per hectare, set against the typical range for that job. Biggest first.
        </p>
        <p className="mt-4">
          {above.count > 0 ? (
            <>
              <span className="font-bold">
                {above.count} {above.count === 1 ? "job" : "jobs"} above the typical range.
              </span>{" "}
              <span className="bg-mark px-2 py-0.5 num text-on-mark">
                {litres(above.litres_low)} to {litres(above.litres_high)} L
              </span>{" "}
              at stake.
            </>
          ) : (
            <span className="font-bold">No job is above its typical range.</span>
          )}
        </p>
      </section>

      {flagged.length > 0 && (
        <section aria-labelledby="above-h" className="print border-t-2 border-dashed border-rule px-4 py-6" style={step(4)}>
          <h2 id="above-h" className="mb-2 font-mono text-sm uppercase tracking-widest">
            Above the typical range
          </h2>
          <ul>
            {flagged.map((r) => (
              <li key={r.operation_code} className="border-b border-rule py-5 last:border-b-0">
                <button
                  onClick={() => open(r, `${r.l_per_ha!.toFixed(1)} L/ha, typical ${range(r)}`)}
                  className="block w-full text-left"
                >
                  <span className="flex items-start justify-between gap-3">
                    <span className="text-lg font-bold">{r.display_name}</span>
                    <BandTag band={r.band} />
                  </span>
                  <BandRange
                    yours={r.l_per_ha!}
                    low={r.reference!.low}
                    high={r.reference!.high}
                    description={`${r.display_name}: ${r.l_per_ha!.toFixed(1)} litres per hectare, typical ${range(r)}`}
                  />
                  <span className="num mt-2 block text-sm">
                    You {r.l_per_ha!.toFixed(1)} L/ha. Typical {range(r)}.
                  </span>
                  <span className="mt-2 block">
                    About <span className="num">{litres(r.litres_at_stake_low)} to {litres(r.litres_at_stake_high)} L</span>{" "}
                    over {r.hectares.toFixed(0)} ha.
                  </span>
                  <span className="mt-2 flex flex-wrap items-center gap-3 text-sm text-ink-soft">
                    <Stamp label={r.label} />
                    {MATCH_NOTE[r.match_quality]}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-labelledby="idle-h" className="print border-t-2 border-dashed border-rule px-4 py-6" style={step(5)}>
        <div className="flex items-center justify-between gap-3">
          <h2 id="idle-h" className="font-mono text-sm uppercase tracking-widest">
            Also worth knowing
          </h2>
          <Stamp label={idle.label} />
        </div>
        <p className="mt-2 max-w-[65ch]">
          <span className="font-bold">{pct(idle.share_pct)} of your fuel was not doing work</span> ({litres(idle.litres)} L).
          This is an observation only: we do not yet have a sourced fix for it, so we do not suggest one.
        </p>
      </section>

      {fine.length > 0 && (
        <section aria-labelledby="fine-h" className="print border-t-2 border-dashed border-rule px-4 py-6" style={step(6)}>
          <h2 id="fine-h" className="mb-2 font-mono text-sm uppercase tracking-widest">
            In line with typical
          </h2>
          <ul>
            {fine.map((r) => (
              <li key={r.operation_code} className="border-b border-rule">
                <button
                  onClick={() => open(r, `${r.l_per_ha!.toFixed(1)} L/ha, typical ${range(r)}`)}
                  className="flex min-h-11 w-full items-end py-2 text-left"
                >
                  <span>{r.display_name}</span>
                  <span className="leader" />
                  <span className="num mr-4 text-sm">{r.l_per_ha!.toFixed(1)} L/ha</span>
                  <BandTag band={r.band} />
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {unrated.length > 0 && (
        <section aria-labelledby="unrated-h" className="print border-t-2 border-dashed border-rule px-4 py-6" style={step(7)}>
          <h2 id="unrated-h" className="mb-2 font-mono text-sm uppercase tracking-widest">
            Not rated
          </h2>
          <ul>
            {unrated.map((r) => (
              <li key={r.operation_code} className="border-b border-rule">
                <button
                  onClick={() => open(r, BAND_TEXT[r.band])}
                  className="flex min-h-11 w-full items-end py-2 text-left"
                >
                  <span>{r.display_name}</span>
                  <span className="leader" />
                  <BandTag band={r.band} />
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="px-4 pb-6">
        <button
          disabled
          className="flex min-h-14 w-full items-center justify-between border-2 border-ink px-4 font-mono text-sm uppercase tracking-widest text-ink-soft"
        >
          <span className="line-through decoration-2">Next: Set a goal</span>
          <span>Next step</span>
        </button>
      </div>

      <WorkingSheet opened={opened} onClose={() => setOpened(null)} />
    </>
  );
}
