import { useRef, useState } from "react";
import { Bold } from "../components/Rich";
import { SCREENS } from "../components/Shell";
import { SectionHead } from "../components/SectionHead";
import { askedFrom, type ScreenId } from "../route";

// One number in the answer, and the calculation (tool) it traced to: "question" if the user gave it, null if untraced.
interface CheckedNumber {
  text: string;
  tool: string | null;
  label: string | null;
}

interface Answer {
  question: string;
  answer: string;
  attempts: number;
  audit: { faithful: boolean; numbers_checked: number; untraced: string[]; numbers?: CheckedNumber[] };
  tools_called: { name: string; args: Record<string, unknown> }[];
  session_id: string;
  new_session: boolean;
  session_note: string | null;
}

// Questions about the screen the analyst was opened from (#/ask?from=control); each one the tools can answer.
const SUGGESTED_FOR: Partial<Record<ScreenId, string[]>> = {
  overview: ["What should I look at first?", "How much fuel did the fleet use, by site?", "How sure are you about these numbers?"],
  sites: ["Which tractor burns more fuel than the others on the same job?", "How much fuel did each machine at the arable site use?", "Which site used the most fuel?"],
  jobs: ["Which jobs used the most fuel in October?", "Which fields used the most fuel?", "How much fuel went on ploughing?"],
  opportunities: ["What should the arable site change first to save fuel?", "How strong is the research behind these ideas?", "How much could the vineyard site save?"],
  control: ["Does our fuel add up this year, or is some missing?", "Do the delivery notes match the fuel log?", "Why could the largest fuel gap have happened?"],
  whatif: ["What if the arable site switched to HVO?", "What if machines above their peers came halfway back to typical?", "What if half the fuel burned with a tool attached but not working was saved?"],
  clients: ["How much CO2 did our work for each client farm produce?", "What is the CO2 per hectare of our work for client farm C03?", "Which client farm had the most fuel burned for it?"],
  reports: ["What is in the company report, and what does it not cover?", "What is the carbon statement for client farm C09?", "How sure are you about these numbers?"],
};

const SUGGESTED = [
  "How much fuel did the fleet use, by site?",
  "Does our fuel add up this year, or is some missing?",
  "Which tractor burns more fuel than the others on the same job?",
  "How much CO2 did our work for each client farm produce?",
  "What should the arable site change first to save fuel?",
  "How sure are you about these numbers?",
  "What if the arable site switched to HVO?",
  "Wie viel Diesel hat die Flotte insgesamt verbraucht?",
];

// What each tool looked at, in words a manager uses.
const LOOKED_AT: Record<string, string> = {
  carbon_ledger: "Tonnes emitted, avoidable and proven",
  action_impact: "Before and after a logged change",
  fleet_summary: "Fuel, emissions and cost totals",
  emissions_per_client: "Emissions for each client farm",
  data_quality: "How far to trust the data",
  reconcile_fuel: "Fuel handed out against fuel burned, and depot stock",
  check_delivery_notes: "Delivery notes against the fuel log",
  detect_anomalies: "Odd jobs and recorders",
  diagnose_anomaly: "Possible causes, tested against the data",
  benchmark_peers: "Machines compared with similar machines",
  fleet_opportunities: "Ideas from research",
  what_if: "A what-if scenario",
  fleet_jobs: "The job list",
  fleet_report: "The report",
  client_statement: "A client farm's carbon statement",
  weekly_briefing: "The three things to look at first",
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

// Whether every number traced to a calculation, in words; opens into the list of numbers and where each came from.
function NumbersChecked({ audit }: { audit: Answer["audit"] }) {
  if (audit.numbers_checked === 0)
    return <p className="border-l-4 border-mark pl-3 font-mono text-xs uppercase tracking-widest">No figures in this answer.</p>;
  const headline = audit.faithful
    ? `Numbers checked by code: all ${audit.numbers_checked} trace to a calculation`
    : `Check needed: ${audit.untraced.join(", ")} could not be traced to a calculation`;
  const numbers = audit.numbers ?? [];
  if (numbers.length === 0)
    return <p className={`border-l-4 pl-3 font-mono text-xs uppercase tracking-widest ${audit.faithful ? "border-mark" : "border-ink font-bold"}`}>{headline}</p>;
  return (
    <details className={`border-l-4 pl-3 ${audit.faithful ? "border-mark" : "border-ink"}`}>
      <summary className={`min-h-11 cursor-pointer py-3 font-mono text-xs uppercase tracking-widest ${audit.faithful ? "" : "font-bold"}`}>
        {headline}
      </summary>
      <ul className="mt-2 space-y-1 text-sm">
        {numbers.map((n, i) => (
          <li key={i} className="max-w-[70ch]">
            <span className="font-bold">{n.text}</span>
            {": "}
            {n.tool === null ? (
              <span className="font-bold">not traced, treat with care</span>
            ) : n.tool === "question" ? (
              "from your question"
            ) : (
              <>
                {LOOKED_AT[n.tool] ?? n.tool}
                {n.label && ` (${n.label})`}
              </>
            )}
          </li>
        ))}
      </ul>
    </details>
  );
}

function Exchange({ a }: { a: Answer }) {
  const { audit } = a;
  return (
    <li className="space-y-4 border-t border-rule py-6">
      {a.session_note && <p className="max-w-[70ch] border-l-4 border-ink pl-3 text-sm font-bold">{a.session_note}</p>}
      <p className="font-display text-2xl font-semibold leading-tight">{a.question}</p>
      <AnswerText text={a.answer} />
      <NumbersChecked audit={audit} />
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
  const [answers, setAnswers] = useState<Answer[]>([]); // the conversation, oldest first
  const [sessionId, setSessionId] = useState<string | null>(null);
  const box = useRef<HTMLTextAreaElement>(null);
  const [from] = useState(askedFrom);
  const suggested = (from && SUGGESTED_FOR[from]) || SUGGESTED;
  const fromName = from ? SCREENS.find((s) => s.id === from)?.name : undefined;

  const startOver = () => {
    setAnswers([]);
    setSessionId(null);
    setError(null);
    box.current?.focus();
  };

  const send = async (question: string) => {
    if (busy || question.trim().length < 3) return;
    setBusy(true);
    setError(null);
    try {
      const r = await fetch("/api/agent/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(sessionId ? { question, session_id: sessionId } : { question }) });
      if (!r.ok) throw new Error(r.status === 502 || r.status === 429 ? ((await r.json()).detail as string) : `The analyst answered ${r.status}`);
      const answer = (await r.json()) as Answer;
      setSessionId(answer.session_id);
      setAnswers((a) => (answer.new_session ? [answer] : [...a, answer]));
      setText("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      // After the button re-enables, so the next question can be typed straight away.
      setTimeout(() => box.current?.focus(), 0);
    }
  };

  return (
    <div className="space-y-8 pb-10">
      <section className="px-6 pt-6" aria-labelledby="h-ask">
        <h1 id="h-ask" className="rise font-display text-5xl font-semibold leading-[1.02] sm:text-6xl tracking-tight" style={{ "--i": 1 } as React.CSSProperties}>
          Ask the analyst
        </h1>
        <p className="mt-3 max-w-[70ch] text-ink-soft">
          Ask about the fleet's fuel, emissions, clients or fuel control in your own words, in any language. The analyst looks up the answer in
          the same calculations as every other screen. It never works out a figure itself, and every number in its answer is checked against
          the calculation it came from.
        </p>
      </section>

      {/* Always mounted, so screen readers announce the first answer too. */}
      <section className="px-6" aria-labelledby={answers.length > 0 ? "h-answers" : undefined} aria-label={answers.length > 0 ? undefined : "Answers"} aria-live="polite">
        {answers.length > 0 && (
          <>
            <SectionHead id="h-answers" title="Conversation" tone="solid" />
            <p className="max-w-[70ch] text-sm text-ink-soft">
              Follow-up questions can refer to earlier answers. The conversation ends after 30 minutes without a question.
            </p>
            <ol>
              {answers.map((a, i) => (
                <Exchange key={`${a.question}-${i}`} a={a} />
              ))}
            </ol>
          </>
        )}
      </section>

      <section className="px-6" aria-labelledby="h-q">
        <SectionHead id="h-q" title={answers.length > 0 ? "Your next question" : "Your question"} tone="mark" />
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
              placeholder={answers.length > 0 ? "Ask a follow-up, for example: and in August?" : "For example: which client farm used the most fuel?"}
              className="w-full max-w-[70ch] border-2 border-ink bg-paper p-3 text-ink"
            />
          </label>
          <div className="flex flex-wrap items-center gap-3">
            <button type="submit" disabled={busy || text.trim().length < 3} className="btn-solid min-h-11 border-2 border-ink bg-ink px-5 text-sm font-bold text-paper disabled:opacity-40">
              {busy ? "Looking at the data..." : "Ask"}
            </button>
            {answers.length > 0 && (
              <button type="button" onClick={startOver} disabled={busy} className="btn-outline min-h-11 border-2 border-ink px-5 text-sm font-bold disabled:opacity-40">
                New conversation
              </button>
            )}
            {busy && <span className="font-mono text-xs uppercase tracking-widest text-ink-soft" role="status">This can take up to a minute: every number is checked before you see it.</span>}
          </div>
        </form>
        {error && (
          <p role="alert" className="mt-3 max-w-[70ch] rounded-2xl border-2 border-clay p-3 font-bold">
            {error}
          </p>
        )}
        <div className="mt-5">
          <p className="mb-2 font-mono text-xs uppercase tracking-widest text-ink-soft">
            {fromName && suggested !== SUGGESTED ? `Or try one of these about ${fromName}` : "Or try one of these"}
          </p>
          <ul className="flex flex-wrap gap-2">
            {suggested.map((q) => (
              <li key={q}>
                <button
                  onClick={() => {
                    setText(q);
                    void send(q);
                  }}
                  disabled={busy}
                  className="btn-outline min-h-11 border-2 border-ink px-4 text-left text-sm disabled:opacity-40"
                >
                  {q}
                </button>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  );
}
