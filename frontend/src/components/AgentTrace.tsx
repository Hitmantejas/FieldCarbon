import { LOOKED_AT, type Row } from "../agentSteps";

const seconds = (ms: number) => (ms < 100 ? "under 0.1 s" : `${(ms / 1000).toFixed(1)} s`);

const argsText = (args: Record<string, unknown>) =>
  Object.entries(args)
    .map(([k, v]) => `${k.replace(/_/g, " ")}: ${String(v)}`)
    .join(", ");

function Line({ row }: { row: Row }) {
  if (row.kind === "tool")
    return (
      <>
        <span className="font-bold">{LOOKED_AT[row.name] ?? row.name}</span>
        {Object.keys(row.args).length > 0 && <span className="text-ink-soft">{` (${argsText(row.args)})`}</span>}
        {": "}
        {row.state === "running" ? "working" : row.state === "failed" ? "failed, the analyst will try again" : `done in ${seconds(row.ms ?? 0)}`}
      </>
    );
  if (row.kind === "rewrite")
    return (
      <>
        <span className="font-bold">Asked the analyst to fix its answer</span>
        {`: ${row.reason}`}
      </>
    );
  const what = row.checked === 1 ? "1 number" : `${row.checked} numbers`;
  return (
    <>
      <span className="font-bold">{row.attempt === 1 ? "Checked the answer" : "Checked the new answer"}</span>
      {row.faithful
        ? `: all ${what} trace to a calculation`
        : `: ${row.untraced.length > 0 ? `${row.untraced.join(", ")} could not be traced` : "a figure is missing its label or source"}`}
      {row.faithful && row.problems > 0 && "; some figures still need a label or source"}
    </>
  );
}

// The analyst's steps in order, so a reader sees what was looked up and how the answer was checked, not only the answer.
export function AgentTrace({ rows }: { rows: Row[] }) {
  return (
    <ol className="space-y-1 border-l-4 border-mark pl-3 text-sm" aria-live="polite">
      {rows.map((row, i) => (
        <li key={i} className="max-w-[70ch]">
          <span className="mr-2 font-mono text-xs text-ink-soft">{i + 1}</span>
          <Line row={row} />
        </li>
      ))}
    </ol>
  );
}
