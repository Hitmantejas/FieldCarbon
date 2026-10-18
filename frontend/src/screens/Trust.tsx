import { useApi } from "../api";
import { SectionHead } from "../components/SectionHead";
import type { TrustCheck, TrustScoreboard } from "../fleetApi";

const STATUS: Record<TrustCheck["status"], { text: string; form: string }> = {
  pass: { text: "Passing", form: "border-ink bg-ink text-paper" },
  partial: { text: "Not perfect", form: "border-dashed border-ink" },
  not_run: { text: "Not run yet", form: "border-dotted border-ink-soft text-ink-soft" },
};
const TONES = ["solid", "mark", "dashed", "solid", "muted"] as const;

function Group({ title, tone, checks, id }: { title: string; tone: (typeof TONES)[number]; checks: TrustCheck[]; id: string }) {
  return (
    <section aria-labelledby={id} className="border-t border-rule px-6 py-6">
      <SectionHead id={id} title={title} tone={tone} />
      <table className="w-full border-collapse text-left">
        <thead className="sr-only">
          <tr>
            <th scope="col">What we test</th>
            <th scope="col">Result</th>
            <th scope="col">Status</th>
          </tr>
        </thead>
        <tbody>
          {checks.map((c) => (
            <tr key={c.question} className="border-t border-rule align-top first:border-t-0">
              <th scope="row" className="max-w-[46ch] py-3 pr-6 font-normal">
                <span className="font-bold">{c.question}</span>
                <span className="mt-1 block text-sm text-ink-soft">{c.detail}</span>
              </th>
              <td className="num py-3 pr-6 text-lg font-bold">{c.result}</td>
              <td className="py-3 text-right">
                <span className={`inline-block border-2 px-3 py-1 font-mono text-xs font-bold uppercase tracking-widest ${STATUS[c.status].form}`}>{STATUS[c.status].text}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export function Trust() {
  const { data: t, error } = useApi<TrustScoreboard>("/api/fleet/trust");
  const groups = t ? [...new Set(t.checks.map((c) => c.group))] : [];
  const when = t?.updated ? new Date(t.updated).toLocaleString("en-GB", { dateStyle: "long", timeStyle: "short" }) : "";

  return (
    <div className="pb-10">
      <section className="px-6 pt-6" aria-labelledby="h-trust">
        <h1 id="h-trust" className="rise font-display text-5xl font-semibold leading-[1.02] sm:text-6xl tracking-tight" style={{ "--i": 1 } as React.CSSProperties}>
          How far can you trust this?
        </h1>
        <p className="mt-3 max-w-[70ch] text-ink-soft">
          We test the app against answers we already know. These are the latest results. Where a score is not perfect, or a test has limits, we say so.
        </p>
        {when && <p className="mt-2 font-mono text-xs uppercase tracking-widest text-ink-soft">Last run {when}</p>}
      </section>

      {error && !t ? (
        <p role="alert" className="mx-6 mt-6 rounded-2xl border-2 border-clay p-4">
          The results could not be loaded. {error}
        </p>
      ) : !t ? (
        <p className="px-6 pt-6 font-mono text-sm uppercase tracking-widest text-ink-soft">Loading the results...</p>
      ) : !t.available ? (
        <p className="mx-6 mt-6 rounded-2xl border-2 border-ink p-4">{t.message}</p>
      ) : (
        <div className="mt-8">
          {groups.map((g, i) => (
            <Group key={g} id={`g-${i}`} title={g} tone={TONES[i % TONES.length]} checks={t.checks.filter((c) => c.group === g)} />
          ))}
          <section aria-labelledby="g-limits" className="border-t border-rule px-6 py-6">
            <SectionHead id="g-limits" title="What these tests do not show" tone="muted" />
            <ul className="max-w-[75ch] list-disc space-y-2 pl-5">
              {t.limits.map((l) => (
                <li key={l}>{l}</li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </div>
  );
}
