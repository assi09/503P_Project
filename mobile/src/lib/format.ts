import type { Evidence, ISODate, Window } from '@/api/types';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "2026-10-19" -> "Oct 19". Parsed by hand so the result does not depend on the device timezone. */
export function shortDate(date: ISODate): string {
  const [, month, day] = date.split('-').map(Number);
  return `${MONTHS[month - 1]} ${day}`;
}

export function windowLabel(window: Window): string {
  return `${shortDate(window.start)} – ${shortDate(window.end)}`;
}

export const METRIC_LABELS: Record<string, string> = {
  steps: 'Steps',
  calories: 'Calories',
  distance_km: 'Distance',
  active_zone_minutes: 'Active Zone Minutes',
  cardio_load: 'Cardio load',
  resting_hr: 'Resting heart rate',
  hrv_ms: 'Heart rate variability',
  respiratory_rate: 'Breathing rate',
  readiness: 'Readiness',
  sedentary_minutes: 'Sedentary time',
  lightly_active_minutes: 'Light activity',
  moderately_active_minutes: 'Moderate activity',
  very_active_minutes: 'Vigorous activity',
  wear_minutes: 'Wear time',
  sleep_minutes: 'Time asleep',
  time_in_bed: 'Time in bed',
  sleep_efficiency: 'Sleep efficiency',
  bedtime_hour: 'Bedtime',
  sleep_score: 'Sleep score',
  deep_sleep_minutes: 'Deep sleep',
  light_sleep_minutes: 'Light sleep',
  rem_sleep_minutes: 'REM sleep',
  awake_in_bed_minutes: 'Awake in bed',
  skin_temp_variation_c: 'Skin temperature',
};

export function metricLabel(metric: string): string {
  return METRIC_LABELS[metric] ?? metric.replace(/_/g, ' ');
}

/** Formats a value in the metric's natural unit, e.g. bedtime 0.5 -> "00:30". */
export function formatValue(metric: string, value: number): string {
  if (metric === 'bedtime_hour') {
    const minutes = Math.round(((value % 24) + 24) % 24 * 60);
    const hh = String(Math.floor(minutes / 60) % 24).padStart(2, '0');
    const mm = String(minutes % 60).padStart(2, '0');
    return `${hh}:${mm}`;
  }
  const digits = Math.abs(value) >= 100 ? 0 : 1;
  return value.toLocaleString('en-US', { maximumFractionDigits: digits });
}

const TOOL_LABELS: Record<string, string> = {
  describe: 'Summary',
  coverage: 'Data coverage',
  compare_windows: 'Compared two periods',
  trend: 'Trend over time',
  correlate: 'Relationship between metrics',
};

export function toolLabel(tool: string): string {
  return TOOL_LABELS[tool] ?? tool;
}

/** Tiny p-values show as "< 0.001" rather than 0. */
export function formatP(p: number): string {
  if (p < 0.001) return '< 0.001';
  return p.toFixed(3);
}

/** Strength of a rank-based effect size (Cliff's delta or Spearman rho), by common rules of thumb. */
export function strength(effect: number): 'negligible' | 'small' | 'medium' | 'large' {
  const size = Math.abs(effect);
  if (size < 0.15) return 'negligible';
  if (size < 0.33) return 'small';
  if (size < 0.47) return 'medium';
  return 'large';
}

export interface StatLine {
  label: string;
  value: string;
}

/** The few statistics worth showing for a piece of evidence, in plain words. */
export function keyStats(evidence: Evidence): StatLine[] {
  const s = evidence.stats;
  const num = (key: string) => (typeof s[key] === 'number' ? (s[key] as number) : null);
  const metric = evidence.metrics[0];
  const lines: StatLine[] = [];

  if (evidence.tool === 'compare_windows') {
    const recent = num('mean_recent');
    const baseline = num('mean_baseline');
    const delta = num('cliffs_delta');
    if (recent !== null) lines.push({ label: 'Recent average', value: formatValue(metric, recent) });
    if (baseline !== null) lines.push({ label: 'Earlier average', value: formatValue(metric, baseline) });
    if (delta !== null) lines.push({ label: 'Effect size', value: `${delta.toFixed(2)} (${strength(delta)})` });
  } else if (evidence.tool === 'trend') {
    const slope = num('slope_per_day');
    const change = num('change_over_window');
    if (slope !== null) lines.push({ label: 'Change per day', value: formatValue(metric, slope) });
    if (change !== null) lines.push({ label: 'Change over period', value: formatValue(metric, change) });
  } else if (evidence.tool === 'correlate') {
    const rho = num('rho');
    const lag = num('best_lag');
    if (rho !== null) lines.push({ label: 'Correlation', value: `${rho.toFixed(2)} (${strength(rho)})` });
    if (lag !== null) lines.push({ label: 'Delay', value: lag === 0 ? 'same day' : `${lag} day${lag > 1 ? 's' : ''}` });
  }

  const p = num('p_value_adjusted') ?? num('p_value');
  if (p !== null) lines.push({ label: 'p-value', value: formatP(p) });
  lines.push({ label: 'Days of data', value: String(evidence.n) });
  return lines;
}
