import { useEffect, useState } from "react";
import { query, useApi } from "../api";
import { AuditBadge } from "../components/AuditBadge";
import { Rich } from "../components/Rich";
import { SectionHead } from "../components/SectionHead";
import { Stamp } from "../components/Stamp";
import { StrengthTag } from "../components/StrengthTag";
import { fetchClientStatement } from "../fleetApi";
import type { ClientEmissions, ClientStatement, FleetReport, Narrative, StatementLanguage } from "../fleetApi";
import { gbpFull, litres, pctText, tonnes } from "../format";
import { co2Text, litresText } from "../ranges";
import { linkText } from "../sources";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const monthName = (key: string) => `${MONTHS[Number(key.slice(5)) - 1]} ${key.slice(0, 4)}`;

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

const LANGUAGES: { code: StatementLanguage; name: string }[] = [
  { code: "en", name: "English" },
  { code: "de", name: "Deutsch" },
  { code: "es", name: "Español" },
  { code: "hi", name: "हिन्दी (Hindi)" },
];
const oneDecimal = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1 });

// F4: the statement's figures come at once (standard wording, no model); the Gemini summary follows and replaces it.
// If Gemini cannot write it (a limit, an outage), the plain message shows and the figures stay.
function useStatement(client: string, language: StatementLanguage) {
  const [s, setS] = useState<ClientStatement>();
  const [written, setWritten] = useState<Narrative>();
  const [writing, setWriting] = useState(false);
  const [error, setError] = useState<string>();
  useEffect(() => {
    setS(undefined);
    setWritten(undefined);
    setError(undefined);
    setWriting(Boolean(client));
    if (!client) return;
    const ac = new AbortController();
    const fail = (e: Error) => {
      if (e.name !== "AbortError") setError(e.message);
    };
    fetchClientStatement(client, language, false, ac.signal).then(setS).catch(fail);
    fetchClientStatement(client, language, true, ac.signal)
      .then((r) => setWritten(r.narrative))
      .catch(fail)
      .finally(() => {
        if (!ac.signal.aborted) setWriting(false);
      });
    return () => ac.abort();
  }, [client, language]);
  return { s, narrative: written ?? (writing ? undefined : s?.narrative), writing, error };
}

export function Reports() {
  const [client, setClient] = useState("");
  const [language, setLanguage] = useState<StatementLanguage>("en");
  const st = useStatement(client, language);
  const clients = useApi<ClientEmissions>("/api/fleet/clients");
  const { data: r, error } = useApi<FleetReport>(`/api/fleet/report${query({ client_id: client || undefined })}`);
  const section = "border-t border-rule px-6 py-6";

  const controls = (
    <section className="no-print px-6 pt-6" aria-label="Choose a report">
      <h1 className="font-display text-5xl font-semibold leading-[1.02] sm:text-6xl tracking-tight">Reports</h1>
      <p className="mt-3 max-w-[70ch] text-ink-soft">
        A report you can print or save as a PDF. Every figure lists its sources. Choose the whole company, or a statement for one client farm to
        send with their invoice.
      </p>
      <div className="mt-4 flex flex-wrap items-end gap-4">
        <label className="flex flex-col gap-2 text-sm text-ink-soft">
          Report for
          <select value={client} onChange={(e) => setClient(e.target.value)} className="min-h-11 min-w-56 border-2 border-ink bg-paper px-2 font-sans text-base normal-case tracking-normal text-ink">
            <option value="">The whole company</option>
            {(clients.data?.rows ?? []).map((c) => (
              <option key={c.client_id} value={c.client_id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        {client && (
          <label className="flex flex-col gap-2 text-sm text-ink-soft">
            Statement language
            <select value={language} onChange={(e) => setLanguage(e.target.value as StatementLanguage)} className="min-h-11 min-w-44 border-2 border-ink bg-paper px-2 font-sans text-base normal-case tracking-normal text-ink">
              {LANGUAGES.map((l) => (
                <option key={l.code} value={l.code} lang={l.code}>
                  {l.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <button onClick={() => window.print()} className="btn-solid min-h-11 border-2 border-ink bg-ink px-4 text-sm font-bold text-paper">
          Print or save as PDF
        </button>
      </div>
    </section>
  );

  if (error && !r) {
    return (
      <>
        {controls}
        <div role="alert" className="mx-6 my-6 rounded-2xl border-2 border-clay p-4">
          <p className="font-bold">We could not build the report.</p>
          <p>{error}. Check the API is running and reload this page.</p>
        </div>
      </>
    );
  }
  if (!r) {
    return (
      <>
        {controls}
        <p className="px-6 py-6 text-ink-soft">Building the report...</p>
      </>
    );
  }

  const when = new Date(r.meta.generated_at).toLocaleString("en-GB", { dateStyle: "long", timeStyle: "short" });
  const t = r.totals;
  const s = client && st.s?.client_id === client ? st.s : undefined;
  const n = st.narrative;

  return (
    <>
      {controls}
      <article aria-labelledby="report-h" className={client ? "statement-print" : undefined}>
        <header className="px-6 pb-6 pt-8">
          <h2 id="report-h" className="font-display text-4xl font-semibold leading-tight">
            {r.meta.title}
          </h2>
          <p className="mt-2 font-bold">
            {r.meta.client ?? "The whole company"} · {s ? `${monthName(s.period.from)} to ${monthName(s.period.to)}` : r.meta.period} · prepared {when}
          </p>
          {r.meta.demo_data && <p className="mt-2 inline-block rounded-full bg-mark px-3 py-1 font-mono text-xs uppercase tracking-widest text-on-mark">Demo data: illustrative</p>}
          <p className="mt-3 max-w-[65ch]">{r.meta.statement}</p>
        </header>

        {client && (
          <section aria-labelledby="r-summary" className={section}>
            <SectionHead id="r-summary" title="In short" tone="solid" aside={n && <AuditBadge narrative={n} />} />
            <div role="status" aria-live="polite" className="no-print text-ink-soft">
              {st.writing && "Writing your statement..."}
            </div>
            {st.error && (
              <p role="alert" className="no-print mb-3 max-w-[70ch] rounded-2xl border-2 border-clay p-3">
                {st.error} The figures below are not affected.
              </p>
            )}
            {n?.error && <p className="no-print mb-3 max-w-[70ch] text-ink-soft">{n.error}</p>}
            {n && n.narrative_language !== language && <p className="no-print mb-3 text-ink-soft">The standard wording is only available in English.</p>}
            {n && (
              <p lang={n.narrative_language} className="max-w-[70ch] text-lg leading-relaxed">
                {n.text}
              </p>
            )}
          </section>
        )}

        {s && (
          <section aria-labelledby="r-statement" className={section}>
            <SectionHead id="r-statement" title="The numbers" tone="solid" />
            <div className="grid gap-x-10 sm:grid-cols-2 print:grid-cols-2">
              <ul>
                <Line label="Fuel burned">
                  <span className="num">{litres(s.totals.litres.value ?? 0)} litres</span>
                  <Stamp label={s.totals.litres.label} />
                </Line>
                <Line label="Emissions">
                  <span className="num">{litres(s.totals.co2e_kg.value ?? 0)} kg CO2e</span>
                  <Stamp label={s.totals.co2e_kg.label} />
                </Line>
                {s.co2e_per_ha && (
                  <Line label="Per hectare">
                    <span className="num">{oneDecimal.format(s.co2e_per_ha.value ?? 0)} kg CO2e</span>
                    <Stamp label={s.co2e_per_ha.label} />
                  </Line>
                )}
                {s.co2e_per_job && (
                  <Line label="Per job">
                    <span className="num">{oneDecimal.format(s.co2e_per_job.value ?? 0)} kg CO2e</span>
                    <Stamp label={s.co2e_per_job.label} />
                  </Line>
                )}
                <Line label="Fuel cost">
                  <span className="num">{gbpFull(s.totals.cost_gbp.value ?? 0)}</span>
                  <Stamp label={s.totals.cost_gbp.label} />
                </Line>
                <Line label="Area worked">
                  <span className="num">{oneDecimal.format(s.area_ha.value ?? 0)} hectares</span>
                  <Stamp label={s.area_ha.label} />
                </Line>
                <Line label="Work done">
                  <span className="num">
                    {litres(s.jobs)} jobs · {litres(s.hours)} engine hours
                  </span>
                </Line>
              </ul>
              <div>
                <h3 className="mt-4 font-bold sm:mt-0 print:mt-0">By operation</h3>
                <ul>
                  {s.by_operation.map((o) => (
                    <Line key={o.operation} label={o.operation}>
                      <span className="num">
                        {litres(o.litres.value ?? 0)} L · {pctText(o.share_pct)}%
                      </span>
                      <Stamp label={o.litres.label} />
                    </Line>
                  ))}
                </ul>
              </div>
            </div>
            {s.jobs_without_area > 0 && (
              <p className="mt-3 max-w-[70ch] text-sm text-ink-soft">
                {s.jobs_without_area} jobs have no recorded area. Their fuel is in the totals, but not in the figure per hectare.
              </p>
            )}
          </section>
        )}

        {!s && (
        <section aria-labelledby="r-totals" className={section}>
          <SectionHead id="r-totals" title="The numbers" tone="solid" />
          <ul>
            <Line label="Fuel burned">
              <span className="num">{litres(t.litres.value ?? 0)} litres</span>
              <Stamp label={t.litres.label} />
            </Line>
            <Line label="Emissions">
              <span className="num">{tonnes(t.co2e_kg.value ?? 0)} CO2e</span>
              <Stamp label={t.co2e_kg.label} />
            </Line>
            <Line label="Fuel cost">
              <span className="num">{gbpFull(t.cost_gbp.value ?? 0)}</span>
              <Stamp label={t.cost_gbp.label} />
            </Line>
            <Line label="Work done">
              <span className="num">
                {litres(t.jobs)} jobs · {litres(t.hours)} engine hours · {litres(t.area_ha)} hectares
              </span>
            </Line>
          </ul>
        </section>
        )}

        {r.months && (
          <section aria-labelledby="r-months" className={`${section} ${client ? "print:hidden" : ""}`}>
            <SectionHead id="r-months" title="Month by month" tone="dashed" />
            <ul>
              {r.months.map((m) => (
                <Line key={m.month} label={monthName(m.month)}>
                  <span className="num">
                    {litres(m.litres.value ?? 0)} L · {tonnes(m.co2e_kg.value ?? 0)} CO2e
                  </span>
                  <Stamp label={m.co2e_kg.label} />
                </Line>
              ))}
            </ul>
          </section>
        )}

        {r.by_site && (
          <section aria-labelledby="r-sites" className={section}>
            <SectionHead id="r-sites" title="By site" tone="dashed" />
            <ul>
              {r.by_site.map((s) => (
                <Line key={s.key} label={s.name}>
                  <span className="num">
                    {litres(s.litres.value ?? 0)} L · {tonnes(s.co2e_kg.value ?? 0)} CO2e
                  </span>
                  <Stamp label={s.litres.label} />
                </Line>
              ))}
            </ul>
          </section>
        )}

        {r.by_client && (
          <section aria-labelledby="r-clients" className={section}>
            <SectionHead id="r-clients" title="By client farm" tone="dashed" />
            <ul>
              {r.by_client.map((c) => (
                <Line key={c.client_id} label={c.name}>
                  <span className="num">
                    {litres(c.litres.value ?? 0)} L · {tonnes(c.co2e_kg.value ?? 0)} CO2e
                  </span>
                  <Stamp label={c.litres.label} />
                </Line>
              ))}
              {r.overhead && (
                <Line label="Company overhead (not charged to a client)">
                  <span className="num">{litres(r.overhead.litres.value ?? 0)} L</span>
                  <Stamp label={r.overhead.litres.label} />
                </Line>
              )}
              {r.unmatched_jobs && (
                <Line label={`Jobs with no matched field (${r.unmatched_jobs.jobs} jobs)`}>
                  <span className="num">{litres(r.unmatched_jobs.litres.value ?? 0)} L</span>
                  <Stamp label={r.unmatched_jobs.litres.label} />
                </Line>
              )}
            </ul>
          </section>
        )}

        {r.findings && (
          <section aria-labelledby="r-findings" className={section}>
            <SectionHead id="r-findings" title="Worth a look" tone="mark" note="to investigate, not proof of a fault" />
            <ul>
              {r.findings.map((f) => (
                <Line key={f.title} label={f.title}>
                  <span className="num">{litres(f.litres.value ?? 0)} {f.litres.unit}</span>
                  <Stamp label={f.litres.label} />
                </Line>
              ))}
            </ul>
          </section>
        )}

        {r.ideas && (
          <section aria-labelledby="r-ideas" className={section}>
            <SectionHead id="r-ideas" title="Ideas that suit the fleet" tone="solid" note="ranges from research · never added together" />
            <ul className="space-y-4">
              {r.ideas.map((i) => (
                <li key={i.intervention_id} className="border-b border-rule pb-4 last:border-b-0">
                  <div className="flex flex-wrap items-center gap-3">
                    <h3 className="font-display text-2xl font-semibold leading-tight">{i.name}</h3>
                    <StrengthTag robustness={i.robustness} n={i.n_sources} />
                    {i.litres_saved && <Stamp label={i.litres_saved.label} />}
                  </div>
                  <p className="num mt-2">
                    {litresText(i.litres_saved)} a year · {co2Text(i.co2e_avoided_kg)} a year
                  </p>
                </li>
              ))}
            </ul>
          </section>
        )}

        <section aria-labelledby="r-limits" className={section}>
          <SectionHead id="r-limits" title={client ? "What this statement does not cover" : "What we do not know"} tone="muted" />
          <ul className="list-disc space-y-2 pl-5">
            {(s?.limits ?? r.limits).map((l) => (
              <li key={l} className="max-w-[70ch]">
                {l}
              </li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="r-labels" className={section}>
          <SectionHead id="r-labels" title="What the labels mean" tone="dashed" />
          <ul className="space-y-3">
            {r.labels.map((l) => (
              <li key={l.label} className="flex flex-wrap items-center gap-4">
                <Stamp label={l.label} />
                <span className="max-w-[65ch]">{l.meaning}</span>
              </li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="r-method" className={section}>
          <SectionHead id="r-method" title="How it was worked out" tone="solid" />
          <Rich text={r.method} />
        </section>

        <section aria-labelledby="r-sources" className={section}>
          <SectionHead id="r-sources" title="Sources" tone="dashed" />
          <ul className="space-y-3">
            {r.sources.map((s) => (
              <li key={s.source_id} className="text-sm">
                <span className="font-bold">{s.title}</span>
                <span className="block text-ink-soft">
                  {[s.publisher_or_authors, s.year].filter(Boolean).join(", ")} · {linkText(s.link_status)}
                </span>
                {s.url && <span className="block break-all">{s.url}</span>}
              </li>
            ))}
          </ul>
          <p className="mt-4 max-w-[75ch] text-sm text-ink-soft">{r.attribution}</p>
        </section>
      </article>
    </>
  );
}
