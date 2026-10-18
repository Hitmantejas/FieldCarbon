// What the analyst does while it answers: each tool it calls, the auditor's verdict, any rewrite. The server streams one
// event per step (POST /api/agent/ask/stream); `fold` keeps them as rows to show, `streamAsk` reads the stream.

export type StepEvent =
  | { step: "tool_call"; name: string; args: Record<string, unknown> }
  | { step: "tool_result"; name: string; error: boolean; ms: number }
  | { step: "audit"; attempt: number; faithful: boolean; numbers_checked: number; untraced: string[]; uncited: number; unlabelled: number; unrounded: number }
  | { step: "rewrite"; reason: string };

export type Row =
  | { kind: "tool"; name: string; args: Record<string, unknown>; state: "running" | "done" | "failed"; ms?: number }
  | { kind: "audit"; attempt: number; faithful: boolean; checked: number; untraced: string[]; problems: number }
  | { kind: "rewrite"; reason: string };

// What each tool looked at, in words a manager uses.
export const LOOKED_AT: Record<string, string> = {
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

export function fold(rows: Row[], e: StepEvent): Row[] {
  switch (e.step) {
    case "tool_call":
      return [...rows, { kind: "tool", name: e.name, args: e.args, state: "running" }];
    case "tool_result": {
      const i = rows.map((r) => r.kind === "tool" && r.name === e.name && r.state === "running").lastIndexOf(true);
      if (i < 0) return rows;
      const done: Row = { ...(rows[i] as Extract<Row, { kind: "tool" }>), state: e.error ? "failed" : "done", ms: e.ms };
      return rows.map((r, j) => (j === i ? done : r));
    }
    case "audit":
      return [...rows, { kind: "audit", attempt: e.attempt, faithful: e.faithful, checked: e.numbers_checked, untraced: e.untraced, problems: e.uncited + e.unlabelled + e.unrounded }];
    case "rewrite":
      return [...rows, { kind: "rewrite", reason: e.reason }];
  }
}

// Reads the event stream of a question. Resolves with the final answer; a failed request or an error event rejects with
// the message to show the user.
export async function streamAsk<T>(body: { question: string; session_id?: string }, onStep: (e: StepEvent) => void): Promise<T> {
  const r = await fetch("/api/agent/ask/stream", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(r.status === 502 || r.status === 429 ? ((await r.json()).detail as string) : `The analyst answered ${r.status}`);
  if (!r.body) throw new Error("The analyst sent no answer.");
  const reader = r.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) throw new Error("The analyst stopped before answering. Please try again.");
    buffer += value;
    let end: number;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const line = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      if (!line.startsWith("data: ")) continue;
      const event = JSON.parse(line.slice(6)) as StepEvent | { step: "answer" } | { step: "error"; message: string };
      if (event.step === "error") throw new Error(event.message);
      if (event.step === "answer") return event as T;
      onStep(event);
    }
  }
}
