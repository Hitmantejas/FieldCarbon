import { useEffect, useState } from "react";

export type Label = "measured" | "allocated" | "estimated" | "excluded";

export interface Figure {
  value: number | null;
  unit: string;
  label: Label;
  how: string;
  low: number | null;
  high: number | null;
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
  reference: { low: number; typical: number; high: number; band_pct: number; source_ids: string[] } | null;
  litres_at_stake_low: number;
  litres_at_stake_high: number;
  match_quality: "direct" | "closest" | "composite" | "none";
  label: Label;
  how: string;
}

export interface PainPoints {
  ratings: Rating[];
  above_range: { count: number; litres_low: number; litres_high: number };
  not_working: { litres: number; total_litres: number; share_pct: number; label: Label };
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
