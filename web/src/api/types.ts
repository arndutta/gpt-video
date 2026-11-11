export type Envelope<T> = { items: T[]; total: number; as_of?: string };
export type Product = {
  sku: string; name: string; category: string; family_id: string; size: number;
  currency: string; cost: string; current_price: string; map_price: string;
  min_price: string; max_price: string; price_version: number;
};
export type Health = {
  status: string; commerce: { status: string; detail?: string };
  gateway: { configured: boolean; status: string };
  capabilities: { quantitative_preview: boolean; grounded_recommendations: boolean };
  tls_verification_disabled?: boolean;
  mode: string; loop: { running: boolean };
};
export type CatalogSummary = {
  sku_count: number; categories: { name: string; sku_count: number }[]; inventory_units: number;
};
export type Settings = {
  gateway_url: string; gateway_port: number | null; key_configured: boolean;
  verify_tls: boolean; allow_insecure_tls: boolean; models: Record<string, string | null>;
  cache: { hits: number; misses: number; available?: boolean }; mode: string;
};
export type Distribution = { mean?: number; median?: number; lower?: number; upper?: number; variance?: number };
export type Forecast = {
  revenue?: Distribution; gross_profit?: Distribution; margin_rate?: Distribution;
  units?: Distribution; demand?: Distribution; cover_days?: Distribution;
  below_margin_floor_probability?: number; [key: string]: unknown;
};
export type Recommendation = {
  sku: string; name?: string; category?: string; current_price: string | number;
  proposed_price: string | number; delta_pct: number; currency?: string;
  elasticity?: { estimate?: number; lower?: number; upper?: number; sample_size?: number; [key: string]: unknown };
  forecast?: Forecast; confidence: number; confidence_factors?: Record<string, unknown>;
  baseline?: { price?: string | number; forecast?: Forecast };
  competitive_gap_pct?: number; cover_days?: number; status?: string;
  assumptions?: unknown; [key: string]: unknown;
};
export type PreviewResult = {
  kind?: string; type?: string; executable?: boolean;
  recommendations?: Recommendation[]; skipped?: unknown[]; quality?: unknown;
  summary?: Record<string, unknown>; aggregate?: Record<string, unknown>;
  configuration?: Record<string, unknown>; [key: string]: unknown;
};
export type PricingRun = {
  id: string; status: string; stage?: string; created_at: string; completed_at?: string;
  error?: unknown; summary?: Record<string, unknown>; result?: PreviewResult;
  request?: { kind?: string; [key: string]: unknown }; duration_seconds?: number;
  token_cost?: number; metrics?: Record<string, unknown>; nodes?: unknown;
};
