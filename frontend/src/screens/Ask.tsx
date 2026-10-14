import { useRef, useState } from "react";
import { Bold } from "../components/Rich";
import { SectionHead } from "../components/SectionHead";

interface Answer {
  question: string;
  answer: string;
  attempts: number;
  audit: { faithful: boolean; numbers_checked: number; untraced: string[] };
  tools_called: { name: string; args: Record<string, unknown> }[];
}

const SUGGESTED = [
  "How much fuel did the fleet use, by site?",
  "Does our fuel add up this year, or is some missing?",
  "Which tractor burns more fuel than the others on the same job?",
  "How much CO2 did our work for each client farm produce?",
  "What should the arable site change first to save fuel?",
  "How sure are you about these numbers?",
];

// What each tool looked at, in words a manager uses.
const LOOKED_AT: Record<string, string> = {
  fleet_summary: "Fuel, emissions and cost totals",
  emissions_per_client: "Emissions for each client farm",
  data_quality: "How far to trust the data",
  reconcile_fuel: "Fuel handed out against fuel burned, and depot stock",
  check_delivery_notes: "Delivery notes against the fuel log",
  detect_anomalies: "Odd jobs and recorders",
  benchmark_peers: "Machines compared with similar machines",
  fleet_opportunities: "Ideas from research",
  what_if: "A what-if scenario",
  fleet_jobs: "The job list",
  fleet_report: "The report",
};

// The model writes short paragraphs, "* " bullets and **bold**; show them as such, never as raw markdown.
function AnswerText({ text }: { text: string }) {
  const blocks: { bullets: boolean; lines: string[] }[] = [];
  for (const line of text.split("\n").map((l) => l.trim()).filter(Boolean)) {
    const bullet = /^[*-]\s+/.test(line);
    const last = blocks[blocks.length - 1];
    if (last && last.bullets === bullet && bullet) last.lines.push(line.replace(/^[*-]\s+/, ""));
    else blocks.push({ bullets: bullet, lines: [bullet ? line.replace(/^[*-]\s+/, "") : line] });
  }
  return (
    <div className="space-y-3">
      {blocks.map((b, i) =>
        b.bullets ? (
          <ul key={i} className="list-disc space-y-1 pl-5">
            {b.lines.map((l, j) => (
              <li key={j} className="max-w-[70ch]">
                <Bold text={l} />
              </li>
            ))}
          </ul>
        ) : (
          <p key={i} className="max-w-[70ch]">
            <Bold text={b.lines[0]} />
          </p>
        ),
      )}
    </div>
  );
}

function Exchange({ a }: { a: Answer }) {
  const { audit } = a;
  return (
    <li className="space-y-4 border-t-2 border-dashed border-rule py-6">
      <p className="font-display text-2xl font-extrabold uppercase leading-none tracking-wide">{a.question}</p>
      <AnswerText text={a.answer} />
      <p className={`border-l-4 pl-3 font-mono text-xs uppercase tracking-widest ${audit.faithful ? "border-mark" : "border-ink font-bold"}`}>
        {audit.numbers_checked === 0
          ? "No figures in this answer."
          : audit.faithful
            ? `Checked: all ${audit.numbers_checked} numbers trace to a calculation.`
            : `Care needed: ${audit.untraced.join(", ")} could not be traced to a calculation.`}
      </p>
      {a.tools_called.length > 0 && (
        <details>
          <summary className="min-h-11 font-mono text-xs uppercase tracking-widest">What I looked at</summary>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ink-soft">
            {a.tools_called.map((t, i) => (
              <li key={i}>
                {LOOKED_AT[t.name] ?? t.name}
                {Object.keys(t.args).length > 0 && ` (${Object.entries(t.args).map(([k, v]) => `${k.replace(/_/g, " ")}: ${String(v)}`).join(", ")})`}
              </li>
            ))}
          </ul>
        </details>
      )}
    </li>
  );
}

export function Ask() {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Answer[]>([]);
  const box = useRef<HTMLTextAreaElement>(null);

  const send = async (question: string) => {
    if (busy || question.trim().length < 3) return;
    setBusy(true);
    setError(null);
    try {
      const r = await fetch("/api/agent/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }) });
      if (!r.ok) throw new Error(r.status === 502 || r.status === 429 ? ((await r.json()).detail as string) : `The analyst answered ${r.status}`);
      const answer = (await r.json()) as Answer;
      setAnswers((a) => [answer, ...a]);
      setText("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-8 pb-10">
      <section className="px-6 pt-6" aria-labelledby="h-ask">
        <h1 id="h-ask" className="print font-display text-6xl font-extrabold uppercase leading-[0.95] tracking-wide" style={{ "--i": 1 } as React.CSSProperties}>
          Ask the analyst
        </h1>
        <p className="mt-3 max-w-[70ch] text-ink-soft">
          Ask about the fleet's fuel, emissions, clients or fuel control in your own words, in any language. The analyst looks up the answer in
          the same calculations as every other screen. It never works out a figure itself, and every number in its answer is checked against
          the calculation it came from.
        </p>
      </section>

      <section className="px-6" aria-labelledby="h-q">
        <SectionHead id="h-q" title="Your question" tone="mark" />
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void send(text);
          }}
          className="space-y-3"
        >
          <label className="block">
            <span className="sr-only">Your question</span>
            <textarea
              ref={box}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send(text);
                }
              }}
              rows={2}
              maxLength={1000}
              placeholder="For example: which client farm used the most fuel?"
              className="w-full max-w-[70ch] border-2 border-ink bg-paper p-3 text-ink"
            />
          </label>
          <div className="flex flex-wrap items-center gap-3">
            <button type="submit" disabled={busy || text.trim().length < 3} className="btn-solid min-h-11 border-2 border-ink bg-ink px-5 font-mono text-sm uppercase tracking-widest text-paper disabled:opacity-40">
              {busy ? "Looking at the data..." : "Ask"}
            </button>
            {busy && <span className="font-mono text-xs uppercase tracking-widest text-ink-soft" role="status">This takes about ten seconds.</span>}
          </div>
        </form>
        {error && (
          <p role="alert" className="mt-3 max-w-[70ch] border-2 border-ink p-3 font-bold">
            {error}
          </p>
        )}
        <div className="mt-5">
          <p className="mb-2 font-mono text-xs uppercase tracking-widest text-ink-soft">Or try one of these</p>
          <ul className="flex flex-wrap gap-2">
            {SUGGESTED.map((q) => (
              <li key={q}>
                <button
                  onClick={() => {
                    setText(q);
                    void send(q);
                  }}
                  disabled={busy}
                  className="btn-outline min-h-11 border-2 border-ink px-3 text-left text-sm disabled:opacity-40"
                >
                  {q}
                </button>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {answers.length > 0 && (
        <section className="px-6" aria-labelledby="h-answers" aria-live="polite">
          <SectionHead id="h-answers" title="Answers" tone="solid" />
          <ul>
            {answers.map((a, i) => (
              <Exchange key={`${a.question}-${i}`} a={a} />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
