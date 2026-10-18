import { useEffect, useState } from "react";

export type Label = "measured" | "allocated" | "estimated" | "excluded";

export interface Figure {
  value: number | null;
  unit: string;
  label: Label;
  how: string;
  source_ids: string[];
  low: number | null;
  high: number | null;
}

export interface SourceInfo {
  source_id: string;
  title: string;
  publisher_or_authors: string | null;
  year: number | null;
  url: string | null;
  evidence_type: string;
  region: string | null;
  is_manufacturer: boolean;
  link_status: string;
}

export interface Evidence {
  coef_id: string;
  source_id: string;
  title: string;
  url: string;
  link_status: string;
  evidence_type: string;
  region: string;
  year: number | null;
  is_manufacturer: boolean;
  low: number;
  high: number;
  unit: string;
  baseline: string;
  value_status: string;
  used_in_range: boolean;
}

export interface PlanFigures {
  litres_saved: Figure | null;
  co2e_avoided_kg: Figure | null;
  fuel_gbp_saved: Figure | null;
  cost: Figure | null;
  payback_years: Figure | null;
  running_cost_change_gbp: Figure | null;
  gbp_per_tco2e?: Figure | null; // fleet ideas only
}

export interface Intervention {
  intervention_id: string;
  name: string;
  state: "feasible" | "needs_info" | "not_feasible";
  reason: string | null;
  missing_inputs: string[];
  robustness: "strong" | "moderate" | "limited";
  n_sources: number;
  label: Label;
  how: string;
  overlaps: string[];
  evidence: Evidence[];
  figures: PlanFigures;
  cost_kind: "capex_one_off" | "running_cost_extra_per_litre" | "operating_cost_per_area_change" | null;
  cost_note: string;
  gbp_per_tco2e_note?: string;
  notes: string;
}

// The user's answers to the Opportunities questions; an unanswered question is simply missing.
export interface Answers {
  tyre_pressure_checked?: boolean;
  has_ctis?: boolean;
  ballast_type?: "liquid" | "none";
}

export function query(params: Record<string, string | number | boolean | undefined>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined) p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

export type State<T> = { data?: T; error?: string };

export function useApi<T>(path: string): State<T> {
  const [state, setState] = useState<State<T>>({});
  useEffect(() => {
    setState({}); // a new path must never show the previous answer
    const ac = new AbortController();
    fetch(path, { signal: ac.signal })
      .then((r) => {
        if (!r.ok) throw new Error(`The API answered ${r.status}`);
        return r.json() as Promise<T>;
      })
      .then((data) => setState({ data }))
      .catch((e: Error) => {
        if (e.name !== "AbortError") setState({ error: e.message });
      });
    return () => ac.abort();
  }, [path]);
  return state;
}
