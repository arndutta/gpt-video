import type { Forecast, Recommendation } from './types';

export type OperatingMode = 'supervised' | 'assisted' | 'autonomous';
export type Band = 'auto_approve' | 'review' | 'escalate';
export type RuleEvidence = { rule: string; passed: boolean; actual?: unknown; threshold?: unknown; message?: string };
export type ManagedRecommendation = Recommendation & {
  id: string; run_id: string; revision: number; band: Band;
  band_reasons: { code: string; message: string; actual?: unknown; threshold?: unknown; passed?: boolean }[];
  compliance: { status: 'passed' | 'failed'; rules: RuleEvidence[] };
  compliance_status: string;
  stability: { oscillation?: boolean; damping_applied?: boolean; novel_market?: boolean; cooldown_active?: boolean; convergence_status?: string; [key: string]: unknown };
  status: string; mode_at_decision: OperatingMode; mode_version: number;
  approval?: { kind: 'human' | 'automatic'; actor: string; reason?: string; approved_at?: string } | null;
  hold_until?: string | null; execution?: unknown; executable: boolean;
  rationale?: unknown; citations?: unknown; sources?: unknown; family_id?: string; size?: number;
};
export type LoopState = {
  running: boolean; status: string; session_id?: string; interval_seconds?: number;
  iteration_count?: number; max_iterations?: number | null; next_run_at?: string | null;
  error?: string | null; request?: Record<string, unknown>; last_run_id?: string | null;
  iterations?: LoopIteration[];
};
export type LoopIteration = {
  iteration: number; run_id: string; status: string;
  decisions?: { total: number; auto_approved: number; queued: number; applied: number; unchanged?: number; unknown: number; blocked: number };
};
export type ControlState = {
  mode: OperatingMode; version: number; generation: number; hold_seconds: number;
  loop: LoopState; policy_version?: number;
};
export type ModelMonitor = {
  active_calls?: number; input_tokens?: number; output_tokens?: number;
  estimated_cost_usd?: number; cost_usd?: number; calls?: number; pricing_source?: string;
  cache?: { hits: number; misses: number; exact_hits?: number; semantic_hits?: number; available?: boolean };
  [key: string]: unknown;
};
export type AuditEvent = {
  id?: number | string; event?: string; kind?: string; action?: string; created_at?: string;
  timestamp?: string; actor?: string; run_id?: string; sku?: string;
  details?: Record<string, unknown>; payload?: Record<string, unknown>; [key: string]: unknown;
};
export type Dashboard = {
  scope?: string; horizon_days?: number; recommendations?: number;
  bands?: Partial<Record<Band, number>>;
  decisions?: { approved?: number; rejected?: number; overridden?: number; automatic?: number; total?: number };
  forecast?: { revenue?: number; gross_profit?: number; baseline_revenue?: number; baseline_gross_profit?: number; [key: string]: unknown };
  realized?: { status?: string; revenue?: number | null; gross_profit?: number | null; observed_skus?: number; pending_skus?: number; forecast_error?: number | null; interval_coverage?: number | null; [key: string]: unknown };
  stability?: { oscillating_skus?: number; damped_skus?: number; error_trend?: string; series?: unknown[]; [key: string]: unknown };
  mode_history?: unknown[]; escalation_causes?: unknown; limitations?: string[]; [key: string]: unknown;
};
export type ScenarioRequest = {
  items: { sku: string; candidate_price: string }[];
  horizon_days: number; iterations: number; seed: number;
  stress: 'none' | 'demand_collapse' | 'competitor_undercut' | 'cost_spike';
  narrate?: boolean;
};
export type ScenarioResult = {
  items?: Recommendation[]; recommendations?: Recommendation[]; configuration?: Record<string, unknown>;
  aggregate?: { forecast?: Forecast; [key: string]: unknown }; narrative?: unknown; [key: string]: unknown;
};
export type SavedScenario = { id: string; name: string; created_at: string; request: ScenarioRequest; result?: ScenarioResult };

export function canReview(item: ManagedRecommendation) {
  return ['pending_review', 'escalated', 'hold'].includes(item.status) && item.compliance?.status === 'passed';
}

export function canBulkApprove(item: ManagedRecommendation, threshold = 0.8) {
  return item.band === 'review' && canReview(item) && item.confidence > threshold;
}

export function bandLabel(band?: string) {
  return band === 'auto_approve' ? 'Auto-approve' : band === 'escalate' ? 'Escalate' : band === 'review' ? 'Review' : 'Unassigned';
}
