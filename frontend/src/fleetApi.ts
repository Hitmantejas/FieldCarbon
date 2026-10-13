import type { Figure, Intervention } from "./api";

export interface GroupRow {
  key: string;
  name: string;
  litres: Figure;
  co2e_kg: Figure;
  cost_gbp: Figure;
  hours: number;
  area_ha: number;
  jobs: number;
  share_pct: number;
  site_id?: string; // machine rows
  data_kind?: string; // site rows
}

export interface DataQuality {
  measured_share_pct: Figure;
  unassigned_litres: Figure;
  frozen_hours: Figure;
  jobs_without_area: Figure;
}

export interface FleetSummary {
  group_by: string;
  rows: GroupRow[];
  totals: { litres: Figure; co2e_kg: Figure; cost_gbp: Figure; hours: number; area_ha: number; jobs: number };
}

export type Severity = "high" | "medium" | "low";

// Anomalies and reconciliation findings share the fields the overview needs.
export interface Finding {
  kind: string;
  severity: Severity;
  title: string;
  litres: Figure;
  site_id: string;
}

export interface Anomalies {
  findings: Finding[];
}

export interface MachineMonth {
  machine_id: string;
  machine: string;
  month: string;
  dispensed_l: number;
  burned_l: number;
  ratio: number | null;
  flagged: boolean;
}

export interface DepotMonth {
  depot_id: string;
  depot: string;
  month_end: string;
  book_l: number;
  measured_l: number;
  gap_l: number;
}

interface Checked<T> {
  label: Figure["label"];
  source_ids: string[];
  how: string;
  rows: T[];
}

export interface Reconciliation {
  findings: Finding[];
  machine_months: Checked<MachineMonth>;
  depots: Checked<DepotMonth>;
  settings: { ratio_limit: number; min_litres: number; stock_tolerance_l: number };
}

export type FleetIdea = Intervention;

export interface FleetOpportunities {
  scope: { site_ids: string[]; litres?: number };
  ideas: FleetIdea[];
  reason: string | null;
}

export interface PeerRow {
  machine_id: string;
  machine: string;
  jobs: number;
  hectares: number;
  litres: number;
  l_per_ha: Figure;
  difference_pct: number;
  above_peers: boolean;
  litres_at_stake: Figure;
}

export interface PeerGroup {
  site_id: string;
  site: string;
  operation_code: string;
  operation: string;
  median_l_per_ha: Figure;
  caveat: string;
  litres_at_stake: Figure;
  peers: PeerRow[];
}

export interface Benchmark {
  groups: PeerGroup[];
  skipped: { site_id: string; operation_code: string; operation: string; reason: string }[];
  settings: { min_machines: number; min_jobs: number; flag_pct: number };
}

export interface ClientMonth {
  client_id: string;
  client: string;
  month: string;
  litres: Figure;
  co2e_kg: Figure;
}

interface Slice {
  litres: Figure;
  co2e_kg: Figure;
  cost_gbp: Figure;
}

export interface ClientEmissions {
  rows: (GroupRow & { client_id: string })[];
  months: ClientMonth[];
  // Fuel that belongs to no client: burned outside jobs, and jobs whose field was not matched.
  overhead: (Slice & { hours: number; breakdown: { key: string; name: string; litres: Figure }[] }) | null;
  unmatched_jobs: (Slice & { jobs: number; area_ha: number }) | null;
  total: Figure | null;
}

export interface JobRow {
  job_id: string;
  date: string;
  month: string;
  site_id: string;
  machine_id: string;
  machine: string;
  operation_code: string;
  operation: string;
  client_id: string | null;
  client: string | null;
  field_id: string | null;
  field: string | null;
  hours: number;
  area_ha: number | null;
  litres: Figure;
  co2e_kg: Figure;
  cost_gbp: Figure;
  l_per_ha: Figure | null;
}

export interface Jobs {
  total_jobs: number;
  offset: number;
  limit: number;
  rows: JobRow[];
  totals: { litres: Figure; co2e_kg: Figure; cost_gbp: Figure } | null;
}
