import type { DayMetric, DaySummary, ISODate, Usual } from '@/api/types';
import { formatValue } from '@/lib/format';

const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function parts(date: ISODate): [number, number, number] {
  const [year, month, day] = date.split('-').map(Number);
  return [year, month, day];
}

/** The date `days` later (or earlier, when negative), by calendar, not by clock. */
export function shiftDate(date: ISODate, days: number): ISODate {
  const [year, month, day] = parts(date);
  return new Date(Date.UTC(year, month - 1, day + days)).toISOString().slice(0, 10);
}

/** "Today", "Yesterday", a weekday within the week, otherwise "Sat 24 Oct". */
export function dayTitle(date: ISODate, today: ISODate): string {
  const [year, month, day] = parts(date);
  const back = Math.round((Date.parse(today) - Date.parse(date)) / 86_400_000);
  if (back === 0) return 'Today';
  if (back === 1) return 'Yesterday';
  const weekday = new Date(Date.UTC(year, month - 1, day)).getUTCDay();
  if (back > 1 && back < 7) return WEEKDAYS[weekday];
  return `${WEEKDAYS[weekday].slice(0, 3)} ${day} ${MONTHS[month - 1]}`;
}

/** "Saturday 24 October 2026" style, short: "Sat 24 Oct 2026". */
export function fullDate(date: ISODate): string {
  const [year, month, day] = parts(date);
  const weekday = new Date(Date.UTC(year, month - 1, day)).getUTCDay();
  return `${WEEKDAYS[weekday].slice(0, 3)} ${day} ${MONTHS[month - 1]} ${year}`;
}

export type Comparison = 'above' | 'below' | 'usual';

/** Where a value sits against the middle half of the weeks before; null without both. */
export function compare(value: number | null, usual: Usual | null): Comparison | null {
  if (value === null || !usual) return null;
  if (value > usual.high) return 'above';
  if (value < usual.low) return 'below';
  return 'usual';
}

export const COMPARISON_TEXT: Record<Comparison, string> = {
  above: 'Above usual',
  below: 'Below usual',
  usual: 'Within usual',
};

/** A usual range short enough for a phone: "7h 05m–7h 50m", "10.6–11.3 breaths/min". */
export function rangeText(metric: string, usual: Usual): string {
  const { value: low } = bigValue(metric, usual.low);
  const { value: high, unit } = bigValue(metric, usual.high);
  return `${low}–${high}${joinUnit(unit)}`;
}

/** A unit after a number: "98%" but "61 bpm". */
export function joinUnit(unit?: string): string {
  if (!unit) return '';
  return unit === '%' ? unit : ` ${unit}`;
}

/** A value as one string in the same style as the large figures: "8h 09m", "98%", "61 bpm". */
export function valueText(metric: string, value: number | null): string {
  const { value: text, unit } = bigValue(metric, value);
  return value === null ? text : `${text}${joinUnit(unit)}`;
}

const SLEEP_DURATIONS = new Set([
  'sleep_minutes',
  'time_in_bed',
  'deep_sleep_minutes',
  'light_sleep_minutes',
  'rem_sleep_minutes',
  'awake_in_bed_minutes',
  'wear_minutes',
]);

/** "Above usual · 00:52–01:30", or "Not enough days to compare yet". */
export function usualLine(metric: DayMetric, partial = false): string {
  if (!metric.usual) return 'Not enough days to compare yet';
  const range = rangeText(metric.metric, metric.usual);
  // Today's activity is still adding up, so "below" would mislead before the day ends.
  if (partial && ACCUMULATING.has(metric.metric)) return `So far · usual ${range}`;
  const comparison = compare(metric.value, metric.usual);
  return comparison ? `${COMPARISON_TEXT[comparison]} · ${range}` : `Usual ${range}`;
}

/** Totals that grow through the day; today's value is not comparable with whole days. */
export const ACCUMULATING = new Set([
  'steps',
  'calories',
  'distance_km',
  'active_zone_minutes',
  'lightly_active_minutes',
  'moderately_active_minutes',
  'very_active_minutes',
  'strain',
  'stress_score', // the daytime part adds up through the day
]);

/** WHOOP's bands for strain on its 0–21 scale. */
export const STRAIN_BANDS: Record<'light' | 'moderate' | 'high' | 'all_out', string> = {
  light: 'Light',
  moderate: 'Moderate',
  high: 'High',
  all_out: 'All out',
};

/** A value split for large figures: 452 sleep minutes -> { value: "7h 32m" }, steps -> "9,214". */
export function bigValue(metric: string, value: number | null): { value: string; unit?: string } {
  if (value === null) return { value: '–' };
  const minutes = metric.endsWith('_minutes') || metric === 'time_in_bed';
  // Sleep reads as hours and minutes; activity stays in minutes ("31–89 min", not "31–1h 29m").
  const sleep = SLEEP_DURATIONS.has(metric);
  if (sleep && value >= 60) {
    const rounded = Math.round(value);
    return { value: `${Math.floor(rounded / 60)}h ${String(rounded % 60).padStart(2, '0')}m` };
  }
  if (minutes) return { value: String(Math.round(value)), unit: 'min' };
  if (metric === 'recovery_score' || metric === 'stress_score') {
    return { value: String(Math.round(value)) };
  }
  if (metric === 'strain') return { value: value.toFixed(1) };
  const units: Record<string, string> = {
    steps: 'steps',
    resting_hr: 'bpm',
    hrv_ms: 'ms',
    respiratory_rate: 'breaths/min',
    calories: 'kcal',
    distance_km: 'km',
    sleep_efficiency: '%',
    skin_temp_variation_c: '°C',
  };
  const text =
    metric === 'skin_temp_variation_c' && value > 0
      ? `+${formatValue(metric, value)}`
      : formatValue(metric, value);
  return { value: text, unit: units[metric] };
}

/** Wake time as hours after midnight, from bedtime (hours, negative before midnight) and time in bed. */
export function wakeHour(bedtimeHour: number | null, timeInBed: number | null): number | null {
  if (bedtimeHour === null || timeInBed === null) return null;
  return (((bedtimeHour + timeInBed / 60) % 24) + 24) % 24;
}

export interface Stage {
  key: 'deep' | 'light' | 'rem' | 'awake';
  label: string;
  minutes: number;
  share: number; // of the time in bed, 0..1
}

/** Sleep stages as shares of the night, in the order they are drawn; null without stages. */
export function stages(day: DaySummary): Stage[] | null {
  const value = (metric: string) => day.metrics.find((m) => m.metric === metric)?.value ?? null;
  const minutes = {
    deep: value('deep_sleep_minutes'),
    light: value('light_sleep_minutes'),
    rem: value('rem_sleep_minutes'),
    awake: value('awake_in_bed_minutes'),
  };
  if (Object.values(minutes).some((m) => m === null)) return null;
  const total = Object.values(minutes).reduce<number>((sum, m) => sum + (m ?? 0), 0);
  if (total <= 0) return null;
  const labels = { deep: 'Deep', light: 'Light', rem: 'REM', awake: 'Awake' };
  return (['awake', 'rem', 'light', 'deep'] as const).map((key) => ({
    key,
    label: labels[key],
    minutes: minutes[key] ?? 0,
    share: (minutes[key] ?? 0) / total,
  }));
}

export function metricOf(day: DaySummary, metric: string): DayMetric {
  return (
    day.metrics.find((m) => m.metric === metric) ?? { metric, value: null, usual: null, recent: [] }
  );
}
