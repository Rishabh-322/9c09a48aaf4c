export type Period = {
  time: string; label: string; forecast_mw: number | null; actual_mw: number | null;
  error_mw: number | null; published_at: string | null; actual_half_hours_mw: [number | null, number | null];
  status: 'matched' | 'forecast-only' | 'actual-only' | 'incomplete-actual' | 'missing';
};

export type Stats = {
  mae: number | null; rmse: number | null; bias: number | null; mape: number | null; n: number;
  coverage_pct: number; matched_periods: number; total_periods: number;
  forecast_periods?: number; actual_periods?: number; period_minutes: number; raw_actual_half_hours?: number; absolute_error_mwh?: number;
  forecast_energy_mwh?: number | null; actual_energy_mwh?: number | null; direction?: string; energy_basis?: string;
};

export type DecisionBrief = {
  net_energy_error_mwh: number | null;
  largest_miss: {time_utc: string; hour_uk: string; error_mw: number} | null;
  distinct_publications: number; latest_publication_utc: string | null;
  status: 'complete' | 'partial' | 'unavailable'; limitation: string;
};

export type DataOrigin = 'synthetic' | 'local_snapshot' | 'api_or_cache';

export type Report = {
  delivery_date: string; decision_date: string; cutoff_uk: string; cutoff_utc: string;
  timezone: string; source: string; data_origin: DataOrigin; statistics: Stats; periods: Period[]; decision_brief: DecisionBrief;
};

export type Month = {
  source: string; cutoff_uk: string; statistics: Stats;
  days: (Stats & {delivery_date: string})[];
};

export type View = 'overview' | 'explorer' | 'accuracy' | 'methodology';

export type CutoffComparison = {
  delivery_date: string; source: string; data_origin: DataOrigin;
  common_comparison: {matched_hours: number; early_mae_mw: number | null; late_mae_mw: number | null; delta_mae_mw: number | null; outcome: 'unavailable' | 'later_worse' | 'later_better' | 'unchanged'; method: string};
  early: {cutoff_uk: string; statistics: Stats};
  late: {cutoff_uk: string; statistics: Stats};
  comparable_forecast_hours: number; revised_hours: number;
  net_forecast_change_mwh: number | null; largest_revision_mw: number; note: string;
};
