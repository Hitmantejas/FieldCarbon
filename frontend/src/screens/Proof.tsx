import { useState } from "react";
import type { Figure } from "../api";
import { useApi } from "../api";
import { t1 } from "../components/CarbonLedger";
import { SectionHead } from "../components/SectionHead";
import { Stamp } from "../components/Stamp";
import { Tile } from "../components/Tile";
import { WorkingSheet, type Opened } from "../components/WorkingSheet";
import type { ActionImpact, ActionImpactResult, ActionStatus } from "../fleetApi";
import { litres } from "../format";

const STATUS: Record<ActionStatus, { text: string; form: string }> = {
  reduction_shown: { text: "Worked: less fuel used", form: "border-ink bg-ink text-paper" },
  increase_shown: { text: "More fuel used", form: "border-ink" },
  cant_tell_yet: { text: "Not clear yet", form: "border-dashed border-ink" },
  not_enough_jobs: { text: "Too early", form: "border-dotted border-ink-soft text-ink-soft" },
};
const date = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" });
const pct = (n: number) => `${Math.round(Math.abs(n))}%`;

// A range of change in words: a minus sign is easy to miss, so say less or more.
function changeText(f: Figure): string {
  const lo = f.low ?? f.value ?? 0;
  const hi = f.high ?? f.value ?? 0;
  if (hi < 0) return `${pct(hi)} to ${pct(lo)} less`;
  if (lo > 0) return `${pct(lo)} to ${pct(hi)} more`;
  return `${pct(lo)} less to ${pct(hi)} more`;
}

function verdict(a: ActionImpact): string {
  const f = a.change_pct;
  if (!f) return a.headline;
  const when = date.format(new Date(a.action.start_date));
  const used = `After ${when}, the changed tractors used`;
  if (a.status !== "cant_tell_yet") return `${used} ${changeText(f)} fuel for each hectare than they would have without the change.`;
  return `${used} somewhere between ${changeText(f).replace(" to ", " and ")} fuel for each hectare than expected. The data cannot say yet whether the change made a difference.`;
}

interface Props {
  a: ActionImpact;
  onOpen: (title: string, shown: string, f: Figure) => void;
}

function ActionCard({ a, onOpen }: Props) {
  const { action, jobs } = a;
  const status = STATUS[a.status];
  const id = `h-${action.action_id}`;
  const rows: { title: string; sub: string; jobs: string; f: Figure | null; result?: boolean }[] = [
    {
      title: "The tractors that were changed",
      sub: action.machines.map((m) => m.split(",")[0]).join(", "),
      jobs: `${jobs.changed_before} jobs before, ${jobs.changed_after} after`,
      f: a.changed_change_pct,
    },
    {
      title: "All other tractors at this site",
      sub: "Not changed. Shows what happened anyway, for example with the season.",
      jobs: `${jobs.others_before} jobs before, ${jobs.others_after} after`,
      f: a.others_change_pct,
    },
    { title: "Effect of the change", sub: "The changed tractors compared with the other tractors", jobs: "", f: a.change_pct, result: true },
  ];

  return (
    <article aria-labelledby={id} className="rounded-3xl bg-tint p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 id={id} className="font-display text-2xl font-semibold leading-tight">
            {action.name}
          </h3>
          <p className="mt-1 font-mono text-xs uppercase tracking-widest text-ink-soft">
            {action.site_name} · from {date.format(new Date(action.start_date))} · {action.is_illustrative ? "illustrative" : "logged"}
          </p>
        </div>
        <span className={`border-2 px-3 py-1 font-mono text-xs font-bold uppercase tracking-widest ${status.form}`}>{status.text}</span>
      </div>

      <p className="mt-3 max-w-[70ch]">
        <span className="font-bold">What was changed: </span>
        {action.what_changed}
      </p>
      <p className="mt-3 max-w-[70ch] text-lg font-bold leading-snug">{verdict(a)}</p>

      {a.change_pct && (
        <table className="mt-4 w-full border-collapse text-left">
          <thead>
            <tr className="font-mono text-xs uppercase tracking-widest text-ink-soft">
              <th scope="col" className="pb-2 font-normal">
                Machines
              </th>
              <th scope="col" className="pb-2 font-normal">
                Jobs compared
              </th>
              <th scope="col" className="pb-2 font-normal">
                Fuel consumed for each hectare, after compared with before
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) =>
              r.f ? (
                <tr key={r.title} className={`border-t align-top ${r.result ? "border-t-2 border-ink" : "border-rule"}`}>
                  <th scope="row" className="py-3 pr-4 font-normal">
                    <span className="font-bold">{r.title}</span>
                    <span className="block max-w-[34ch] text-sm text-ink-soft">{r.sub}</span>
                  </th>
                  <td className="py-3 pr-4 text-sm">{r.jobs}</td>
                  <td className="py-3">
                    <button
                      onClick={() => onOpen(`${action.name}: ${r.title.toLowerCase()}`, `Fuel for each hectare: ${changeText(r.f!)}`, r.f!)}
                      className="btn-link flex flex-col items-start gap-1 text-left"
                      aria-label={`${r.title}: fuel for each hectare, ${changeText(r.f)}, ${r.f.label}. Show how it was worked out.`}
                    >
                      <span className={`num underline underline-offset-4 ${r.result ? "text-lg font-bold" : ""}`}>{changeText(r.f)}</span>
                      <Stamp label={r.f.label} />
                    </button>
                  </td>
                </tr>
              ) : null,
            )}
          </tbody>
        </table>
      )}

      {a.co2e_avoided_t && a.litres_avoided && (
        <dl className="mt-4 grid gap-x-8 gap-y-3 sm:grid-cols-[14rem_1fr_auto] sm:items-center">
          {[
            { title: "Fuel saved", f: a.litres_avoided, shown: `${litres(a.litres_avoided.low ?? 0)} to ${litres(a.litres_avoided.high ?? 0)} litres` },
            { title: "CO2e avoided", f: a.co2e_avoided_t, shown: `${t1(a.co2e_avoided_t.low ?? 0)} to ${t1(a.co2e_avoided_t.high ?? 0)} tonnes` },
          ].map((r) => (
            <div key={r.title} className="contents">
              <dt className="font-bold">{r.title}</dt>
              <dd className="num">
                {r.shown}
                <button
                  onClick={() => onOpen(`${action.name}: ${r.title.toLowerCase()}`, r.shown, r.f)}
                  className="btn-link ml-2 inline-flex min-h-11 items-center px-2 font-sans text-sm underline underline-offset-4"
                  aria-label={`How ${r.title} was worked out`}
                >
                  How is this worked out?
                </button>
              </dd>
              <dd>
                <Stamp label={r.f.label} />
              </dd>
            </div>
          ))}
        </dl>
      )}

      <p className="mt-4 max-w-[70ch] text-sm">
        <span className="font-bold">{a.change_pct ? "To get a firmer answer: " : "What is needed: "}</span>
        {a.what_would_improve}
      </p>
    </article>
  );
}

export function Proof() {
  const result = useApi<ActionImpactResult>("/api/fleet/actions");
  const [opened, setOpened] = useState<Opened | null>(null);
  const open = (title: string, shown: string, f: Figure) => setOpened({ title, shown, label: f.label, how: f.how, sourceIds: f.source_ids });
  const r = result.data;
  const proven = r?.proven_co2e_t;
  const shown = proven ? (proven.low != null && proven.high != null ? `${t1(proven.low)} to ${t1(proven.high)}` : t1(proven.value ?? 0)) : "";
  const worked = r?.actions.filter((a) => a.status === "reduction_shown").length ?? 0;

  return (
    <div className="space-y-10 pb-10">
      <section className="px-6 pt-6" aria-labelledby="h-proof">
        <h1 id="h-proof" className="rise font-display text-5xl font-semibold leading-[1.02] sm:text-6xl tracking-tight" style={{ "--i": 1 } as React.CSSProperties}>
          Did the changes work?
        </h1>
        <p className="mt-3 max-w-[70ch] text-ink-soft">
          Each time we change how some tractors are run, we log it. For every change we compare the fuel each tractor consumed for each hectare before and
          after, and set that against tractors that were not changed, so the season and the type of job do not fool us. A saving counts only when the
          result is clear. The two changes below are made up to show how the check works. The fuel records under them are real and unchanged.
        </p>
      </section>

      {result.error && !r ? (
        <p className="px-6">The proof could not be loaded. {result.error}</p>
      ) : !r || !proven ? (
        <p className="px-6 font-mono text-sm uppercase tracking-widest text-ink-soft">Loading the changes...</p>
      ) : (
        <>
          <section aria-label="Proven so far" className="mx-6 grid gap-3 md:grid-cols-3">
            <Tile highlight title="CO2e avoided, proven" shown={shown} unit="t CO2e" note="Counts only changes that clearly worked" figure={proven} onOpen={() => open("CO2e avoided, proven", `${shown} t CO2e`, proven)} />
            <Tile title="Changes logged" shown={String(r.actions.length)} unit="" />
            <Tile title="Changes that worked" shown={String(worked)} unit="" note="The rest are not clear yet" />
          </section>

          <section className="px-6" aria-labelledby="h-changes">
            <SectionHead id="h-changes" title="Logged changes" tone="solid" note="illustrative demo data" />
            <div className="space-y-6">
              {r.actions.map((a) => (
                <ActionCard key={a.action.action_id} a={a} onOpen={open} />
              ))}
            </div>
          </section>
        </>
      )}

      <WorkingSheet opened={opened} onClose={() => setOpened(null)} />
    </div>
  );
}
