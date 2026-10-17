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

export type Verdict = "reaches" | "might_reach" | "falls_short";

export interface LedgerAction {
  intervention_id: string;
  name: string;
  state: "feasible" | "needs_info";
  robustness: "strong" | "moderate" | "limited";
  co2e_avoided_t: Figure;
  gbp_per_tco2e: Figure | null;
  gbp_per_tco2e_note: string;
}

export interface Ledger {
  emitted: Figure;
  sites: { site_id: string; name: string; co2e_t: Figure; kg_per_ha: Figure; covered_by_evidence: boolean }[];
  avoidable: {
    top_action: LedgerAction;
    combined: Figure;
    actions: LedgerAction[];
    covered_emitted_t: Figure;
    covered_share_pct: number;
    not_covered: string;
  };
  proven: Figure;
  proven_changes: { action_id: string; name: string }[];
  goal: {
    target_pct: number;
    target_co2e: Figure;
    top_action_pct: Figure;
    combined_pct: Figure;
    top_action_verdict: Verdict;
    combined_verdict: Verdict;
  };
}

export type ActionStatus = "reduction_shown" | "increase_shown" | "cant_tell_yet" | "not_enough_jobs";

export interface ActionImpact {
  action: {
    action_id: string;
    name: string;
    site_name: string;
    machines: string[];
    start_date: string;
    what_changed: string;
    is_illustrative: boolean;
  };
  status: ActionStatus;
  headline: string;
  jobs: { changed_before: number; changed_after: number; others_before: number; others_after: number };
  change_pct: Figure | null;
  changed_change_pct: Figure | null;
  others_change_pct: Figure | null;
  litres_avoided: Figure | null;
  co2e_avoided_t: Figure | null;
  operations: string[];
  caveats: string[];
  what_would_improve: string;
}

export interface ActionImpactResult {
  actions: ActionImpact[];
  proven_co2e_t: Figure;
  method: string;
}

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

export type Scenario = "implement_not_working" | "peer_outliers" | "hvo";

export interface WhatIf {
  available: boolean;
  is_scenario: true;
  reason?: string;
  scenario?: string;
  assumption?: string;
  litres_saved?: Figure;
  co2e_avoided_kg?: Figure;
  cost_saved_gbp?: Figure;
}

export interface ReportSource {
  source_id: string;
  title: string;
  publisher_or_authors: string | null;
  year: number | null;
  url: string | null;
  link_status: string;
}

export interface FleetReport {
  meta: { title: string; period: string; demo_data: boolean; statement: string; generated_at: string; client: string | null };
  totals: { litres: Figure; co2e_kg: Figure; cost_gbp: Figure; jobs: number; hours: number; area_ha: number };
  by_site?: { key: string; name: string; litres: Figure; co2e_kg: Figure; share_pct: number }[];
  by_client?: { client_id: string; name: string; litres: Figure; co2e_kg: Figure }[];
  overhead?: { litres: Figure; breakdown: { key: string; name: string; litres: Figure }[] } | null;
  unmatched_jobs?: { litres: Figure; jobs: number } | null;
  findings?: { title: string; severity: Severity; litres: Figure }[];
  ideas?: { intervention_id: string; name: string; robustness: "strong" | "moderate" | "limited"; n_sources: number; litres_saved: Figure | null; co2e_avoided_kg: Figure | null }[];
  months?: ClientMonth[];
  limits: string[];
  labels: { label: Figure["label"]; meaning: string }[];
  method: string;
  attribution: string;
  sources: ReportSource[];
}

// Delivery notes read by Gemini, checked against the fuel log by code (GET /api/fleet/delivery-notes).
export interface NoteFinding {
  kind: "entered_twice" | "note_not_in_log" | "litres_differ" | "price_differs" | "date_differs" | "log_row_without_note" | "note_needs_review";
  severity: Severity;
  doc_no: string;
  title: string;
  figure: Figure | null; // litres, or GBP for a price difference; null when there is nothing to quantify
  reasons?: string[];
  on_note?: number | string;
  in_log?: number | string;
}

export interface DeliveryNotes {
  data_source: string;
  notes: number;
  log_rows: number;
  notes_matching_log: number;
  litres_on_notes: Figure;
  litres_in_log: Figure;
  findings: NoteFinding[];
  note: string;
}

export interface TrustCheck {
  group: string;
  question: string;
  result: string;
  detail: string;
  status: "pass" | "partial" | "not_run";
}

export interface TrustScoreboard {
  available: boolean;
  message?: string;
  updated?: string;
  checks: TrustCheck[];
  limits: string[];
}
