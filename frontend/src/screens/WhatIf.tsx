import { useState } from "react";
import type { Figure } from "../api";
import { query, useApi } from "../api";
import { SectionHead } from "../components/SectionHead";
import { Stamp } from "../components/Stamp";
import { WorkingSheet, type Opened } from "../components/WorkingSheet";
import type { FleetSummary, Scenario, WhatIf as WhatIfData } from "../fleetApi";
import { gbpFull } from "../format";
import { absRange, co2Text, litresText, moneyText } from "../ranges";

const SCENARIOS: { id: Scenario; name: string; about: string; amount: string; presets: number[] }[] = [
  {
    id: "implement_not_working",
    name: "Less fuel with a tool attached but not working",
    about: "Time spent driving, turning or waiting with a tool attached but not working. Cut it by a share and see what changes.",
    amount: "Cut this fuel by",
    presets: [10, 25, 50],
  },
  {
    id: "peer_outliers",
    name: "Machines that burn more than their peers come down",
    about: "The machines that burn more per hectare than similar machines on the same job move toward the typical machine.",
    amount: "Close this share of the gap",
    presets: [25, 50, 100],
  },
  {
    id: "hvo",
    name: "Switch part of the fuel to HVO",
    about: "HVO is a diesel made from waste oils. Engines burn a little more of it, and it costs more, but it releases far less CO2.",
    amount: "Share of fuel switched",
    presets: [10, 25, 100],
  },
];

function Loading({ what }: { what: string }) {
  return <p className="font-mono text-sm uppercase tracking-widest text-ink-soft">Loading {what}...</p>;
}

export function WhatIf() {
  const [scenario, setScenario] = useState<Scenario>("implement_not_working");
  const [amount, setAmount] = useState(25);
  const [site, setSite] = useState("");
  const [opened, setOpened] = useState<Opened | null>(null);
  const sites = useApi<FleetSummary>("/api/fleet/summary?group_by=site");
  const result = useApi<WhatIfData>(`/api/fleet/what-if${query({ change: scenario, amount_pct: amount, site_id: site || undefined })}`);
  const current = SCENARIOS.find((s) => s.id === scenario)!;

  const open = (title: string, shown: string, f: Figure) => setOpened({ title, shown, label: f.label, how: f.how, sourceIds: f.source_ids });
  const r = result.data;
  const rows: { title: string; shown: string; f: Figure | undefined }[] = r?.available
    ? [
        {
          title: r.litres_saved && (r.litres_saved.high ?? r.litres_saved.value ?? 0) < 0 ? "Extra fuel burned" : "Fuel saved",
          shown: litresText(r.litres_saved ?? null),
          f: r.litres_saved,
        },
        { title: "Emissions avoided", shown: co2Text(r.co2e_avoided_kg ?? null), f: r.co2e_avoided_kg },
        {
          title: r.cost_saved_gbp && (r.cost_saved_gbp.high ?? r.cost_saved_gbp.value ?? 0) < 0 ? "Fuel bill goes up by" : "Money saved on fuel",
          shown: r.cost_saved_gbp && (r.cost_saved_gbp.high ?? r.cost_saved_gbp.value ?? 0) < 0 ? absRange(r.cost_saved_gbp, gbpFull) : moneyText(r.cost_saved_gbp ?? null),
          f: r.cost_saved_gbp,
        },
      ]
    : [];

  return (
    <div className="space-y-10 pb-10">
      <section className="px-6 pt-6" aria-labelledby="h-whatif">
        <h1 id="h-whatif" className="rise font-display text-6xl font-semibold leading-[1.02] tracking-tight" style={{ "--i": 1 } as React.CSSProperties}>
          What if
        </h1>
        <p className="mt-3 max-w-[70ch] text-ink-soft">
          Try a change and see what it would do over a year. You set the size of the change, so this is arithmetic on the fuel the fleet really
          burned, not a forecast.
        </p>
      </section>

      <section className="px-6" aria-labelledby="h-pick">
        <SectionHead id="h-pick" title="1. Pick a change" tone="solid" />
        <ul className="grid gap-4 lg:grid-cols-3">
          {SCENARIOS.map((s) => (
            <li key={s.id}>
              <button
                onClick={() => setScenario(s.id)}
                aria-pressed={scenario === s.id}
                className={`flex h-full w-full flex-col gap-2 rounded-3xl border-2 p-5 text-left transition-colors ${scenario === s.id ? "border-ink bg-ink text-paper" : "border-rule bg-tint hover:border-ink"}`}
              >
                <span className="font-display text-2xl font-semibold leading-tight">{s.name}</span>
                <span className="text-sm">{s.about}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section className="px-6" aria-labelledby="h-size">
        <SectionHead id="h-size" title="2. Set the size" tone="dashed" />
        <div className="flex flex-wrap items-end gap-6">
          <div role="group" aria-label={current.amount}>
            <p className="mb-2 font-mono text-xs uppercase tracking-widest text-ink-soft">{current.amount}</p>
            <div className="flex flex-wrap items-center gap-2">
              {current.presets.map((p) => (
                <button
                  key={p}
                  onClick={() => setAmount(p)}
                  aria-pressed={amount === p}
                  className={`btn-tab min-h-11 border-2 px-4 font-mono text-sm ${amount === p ? "border-ink bg-ink font-bold text-paper" : "border-rule hover:border-ink"}`}
                >
                  {p}%
                </button>
              ))}
              <label className="flex items-center gap-2 font-mono text-sm">
                <span className="sr-only">Or type a percentage</span>
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={amount}
                  onChange={(e) => setAmount(Math.min(100, Math.max(1, Number(e.target.value) || 1)))}
                  className="num min-h-11 w-24 border-2 border-ink bg-paper px-2 text-ink"
                />
                %
              </label>
            </div>
          </div>
          <label className="flex flex-col gap-2 text-sm text-ink-soft">
            Where
            <select value={site} onChange={(e) => setSite(e.target.value)} className="min-h-11 min-w-48 border-2 border-ink bg-paper px-2 font-sans text-base normal-case tracking-normal text-ink">
              <option value="">Whole fleet</option>
              {(sites.data?.rows ?? []).map((s) => (
                <option key={s.key} value={s.key}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
        </div>
      </section>

      <section className="px-6" aria-labelledby="h-result" aria-live="polite">
        <SectionHead id="h-result" title="3. What it would do" tone="mark" note="a scenario, not a forecast" />
        {!r ? (
          <Loading what="the scenario" />
        ) : !r.available ? (
          <p className="max-w-[70ch]">{r.reason}</p>
        ) : (
          <div className="space-y-5">
            <div className="max-w-[75ch]">
              <p className="font-bold">{r.scenario}</p>
              <p className="text-ink-soft">{r.assumption}</p>
            </div>
            <dl className="grid gap-x-8 gap-y-4 sm:grid-cols-[14rem_1fr_auto] sm:items-center">
              {rows.map((row) => (
                <div key={row.title} className="contents">
                  <dt className="font-bold">{row.title}</dt>
                  <dd className="num">
                    {row.shown} a year
                    {row.f && (
                      <button
                        onClick={() => open(row.title, `${row.shown} a year`, row.f!)}
                        className="btn-link ml-2 inline-flex min-h-11 items-center px-2 font-sans text-sm underline underline-offset-4"
                        aria-label={`How ${row.title} was worked out`}
                      >
                        How
                      </button>
                    )}
                  </dd>
                  <dd>{row.f && <Stamp label={row.f.label} />}</dd>
                </div>
              ))}
            </dl>
            <p className="max-w-[75ch] border-l-4 border-mark pl-4 text-sm text-ink-soft">
              These are ranges from the sizes you chose. They are arithmetic on measured fuel, so they carry the weakest label of what went in.
              Change the size above and the result updates.
            </p>
          </div>
        )}
      </section>

      <WorkingSheet opened={opened} onClose={() => setOpened(null)} />
    </div>
  );
}
