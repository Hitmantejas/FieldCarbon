import { useEffect, useRef, useState } from "react";
import type { Figure } from "../api";
import { fetchBriefing } from "../fleetApi";
import type { Briefing as BriefingData, StatementLanguage } from "../fleetApi";
import { litres } from "../format";
import { litresText } from "../ranges";
import { AuditBadge } from "./AuditBadge";
import { SeverityTag } from "./FindingList";
import { SectionHead } from "./SectionHead";
import { Stamp } from "./Stamp";

const LANGUAGES: { code: StatementLanguage; name: string }[] = [
  { code: "en", name: "English" },
  { code: "de", name: "Deutsch" },
  { code: "es", name: "Español" },
  { code: "hi", name: "हिन्दी (Hindi)" },
];

// Link text names the screen, so it makes sense read on its own.
const SCREENS: Record<string, string> = { "#/control": "Fuel control", "#/opportunities": "Opportunities", "#/sites": "Sites", "#/jobs": "Jobs", "#/overview": "Overview" };

// One value or a low-high range, in the figure's own unit.
const shown = (f: Figure) => {
  if (f.unit === "L per year") return `${litresText(f)} a year`;
  if (f.value === null) return "not worked out";
  if (f.unit === "h") return `${f.value.toLocaleString("en-GB", { maximumFractionDigits: 1 })} hours`;
  if (f.unit === "GBP") return `£${f.value.toFixed(2)}`;
  return `${litres(f.value)} ${f.unit}`;
};

// F6: the three things to look at first. Code chooses the items; Gemini may only write the intro, on request.
export function Briefing({ onOpen }: { onOpen: (title: string, shown: string, f: Figure) => void }) {
  const running = useRef<AbortController | null>(null);
  const [language, setLanguage] = useState<StatementLanguage>("en");
  const [data, setData] = useState<BriefingData | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = async (narrate: boolean) => {
    running.current?.abort();
    const ac = new AbortController();
    running.current = ac;
    setError(null);
    setBusy(narrate ? "Gemini is writing the intro... this can take up to a minute." : "Choosing the items...");
    try {
      setData(await fetchBriefing(language, narrate, ac.signal));
    } catch (e) {
      if (!ac.signal.aborted) setError(e instanceof Error ? e.message : "The briefing could not be loaded.");
    } finally {
      if (!ac.signal.aborted) setBusy(null);
    }
  };

  useEffect(() => {
    void load(false);
    return () => running.current?.abort();
  }, [language]);

  return (
    <section className="px-6" aria-labelledby="h-briefing">
      <SectionHead id="h-briefing" title={data?.heading ?? "Week summary"} tone="mark" note={data?.period ?? "company year to date"} />
      <div className="mb-4 flex flex-wrap items-end gap-4">
        <label className="flex flex-col gap-2 text-sm text-ink-soft">
          Intro language
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value as StatementLanguage)}
            className="min-h-11 min-w-44 border-2 border-ink bg-paper px-2 font-sans text-base text-ink"
          >
            {LANGUAGES.map((l) => (
              <option key={l.code} value={l.code} lang={l.code}>
                {l.name}
              </option>
            ))}
          </select>
        </label>
        {data && data.intro.narrative_source === "template" && (
          <button
            onClick={() => void load(true)}
            disabled={busy !== null}
            className="btn-outline min-h-11 border-2 border-ink px-4 text-sm font-bold disabled:opacity-60"
          >
            Ask Gemini to write an intro
          </button>
        )}
      </div>

      <div role="status" aria-live="polite" className="font-mono text-xs uppercase tracking-widest text-ink-soft">
        {busy}
      </div>
      {error && (
        <p role="alert" className="max-w-[70ch] rounded-2xl border-2 border-clay p-3 font-bold">
          {error}
        </p>
      )}

      {data && (
        <>
          <div className="mb-4 space-y-2">
            <p className="max-w-[70ch]" lang={data.intro.narrative_language}>
              {data.intro.text}
            </p>
            <AuditBadge narrative={data.intro} />
            {data.intro.error && <p className="text-sm text-ink-soft">{data.intro.error}</p>}
          </div>
          <ol className="grid gap-3 lg:grid-cols-3">
            {data.items.map((i, n) => (
              <li key={i.id} className="flex flex-col gap-3 rounded-2xl border-2 border-ink p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs uppercase tracking-widest text-ink-soft">Item {n + 1}</span>
                  <SeverityTag severity={i.severity} />
                </div>
                <h3 className="font-bold">{i.title}</h3>
                <button
                  onClick={() => onOpen(i.title, shown(i.figure), i.figure)}
                  className="btn-link flex min-h-11 flex-wrap items-center gap-3 text-left"
                  aria-label={`${shown(i.figure)}, ${i.figure.label}. Show how it was worked out.`}
                >
                  <span className="num text-xl underline underline-offset-4">{shown(i.figure)}</span>
                  <Stamp label={i.figure.label} />
                </button>
                <p className="text-sm">
                  <span className="font-bold">Why it matters: </span>
                  {i.why_it_matters}
                </p>
                <p className="text-sm">
                  <span className="font-bold">Next step: </span>
                  {i.next_step}
                </p>
                <a href={i.link} className="btn-link inline-flex min-h-11 items-center text-sm font-bold underline underline-offset-4">
                  Open {SCREENS[i.link] ?? "the screen"}
                </a>
                <details className="text-sm">
                  <summary className="min-h-11 cursor-pointer py-2 font-bold">What would improve this</summary>
                  <p>{i.would_improve}</p>
                </details>
              </li>
            ))}
          </ol>
          <p className="mt-2 text-sm text-ink-soft">
            {data.intro.narrative_source === "gemini"
              ? "Items chosen by fixed rules. Intro written by Gemini and checked by code."
              : "Items chosen by fixed rules. Standard wording."}{" "}
            {data.rules}
          </p>
        </>
      )}
    </section>
  );
}
