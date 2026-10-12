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

export interface Reference {
  low: number;
  typical: number;
  high: number;
  band_pct: number;
  source_ids: string[];
}

export interface Summary {
  farm: { id: string; name: string; tier: number; description: string };
  litres: Figure;
  co2e_kg: Figure;
  cost_gbp: Figure;
  hours: number;
  tractors: string[];
  excluded_hours: number;
  provenance: { dataset: string; licence: string; attribution: string; emission_factors: string; demo_data: boolean };
}

export interface BreakdownRow {
  key: string;
  name: string;
  litres: Figure;
  co2e_kg: Figure;
  cost_gbp: Figure;
  hours: number;
  share_pct: number;
}

export type Band = "below_typical" | "typical" | "above_typical" | "well_above" | "insufficient_data" | "no_reference";

export interface Rating {
  operation_code: string;
  display_name: string;
  band: Band;
  hectares: number;
  litres: number;
  l_per_ha: number | null;
  reference: Reference | null;
  litres_at_stake_low: number;
  litres_at_stake_high: number;
  match_quality: "direct" | "closest" | "composite" | "none";
  label: Label;
  how: string;
  second_opinion: Reference | null;
  sources_agree: boolean | null;
  litres_at_stake_label: Label;
}

export interface PainPoints {
  ratings: Rating[];
  above_range: { count: number; litres_low: number; litres_high: number; count_sources_agree: number; label: Label };
  not_working: { litres: number; total_litres: number; share_pct: number; label: Label };
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
  notes: string;
}

export interface GoalIdea {
  intervention_id: string;
  name: string;
  state: Intervention["state"];
  robustness: Intervention["robustness"];
  n_sources: number;
  missing_inputs: string[];
  verdict: "reaches" | "might_reach" | "falls_short" | "not_applicable";
  reach: Figure | null;
  warning: string | null;
}

// The farmer's answers; an unanswered question is simply missing.
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

export interface Goal {
  target_pct: number;
  suggested_pct: number;
  suggested_how: string;
  target_co2e: Figure;
  target_litres: Figure;
  counts: Record<GoalIdea["verdict"], number>;
  ideas: GoalIdea[];
}

export type State<T> = { data?: T; error?: string };

export function useApi<T>(path: string): State<T> {
  const [state, setState] = useState<State<T>>({});
  useEffect(() => {
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
