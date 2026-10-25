// Plain words for a piece of evidence: the question it answers, its answer, the figures that
// matter, how it was computed and what to chart. The numbers come only from the evidence.
import type { Evidence, ISODate, Window } from '@/api/types';
import { rangeText, valueText } from '@/lib/day';
import { formatP, metricLabel, shortDate, strength, verdict, windowLabel } from '@/lib/format';

const num = (evidence: Evidence, key: string): number | null => {
  const value = evidence.stats[key];
  return typeof value === 'number' ? value : null;
};

function lower(metric: string): string {
  const label = metricLabel(metric);
  return label.charAt(0).toLowerCase() + label.slice(1);
}

/** The question the computation answers, e.g. "Did time asleep change?". */
export function question(evidence: Evidence): string {
  const [a, b] = evidence.metrics;
  switch (evidence.tool) {
    case 'compare_windows':
      return `Did ${lower(a)} change?`;
    case 'compare_day':
      return `How was ${lower(a)} that day, against your usual?`;
    case 'trend':
      return `Is ${lower(a)} drifting over time?`;
    case 'change_point':
      return `Did ${lower(a)} shift to a new level?`;
    case 'correlate':
      return `Do ${lower(a)} and ${lower(b)} move together?`;
    case 'weekday_split':
      return `Is ${lower(a)} different on weekends?`;
    case 'coverage':
      return 'How complete is your data?';
    default:
      return metricLabel(a ?? '');
  }
}

export interface Answer {
  text: string;
  tone: 'clear' | 'unclear' | 'neutral'; // clear: a significant result, or a day outside usual
}

/** The short answer to the question, in large type. */
export function answer(evidence: Evidence): Answer {
  if (!evidence.sufficient) return { text: 'Too few days to tell', tone: 'unclear' };
  if (evidence.tool === 'compare_day') {
    const position = evidence.stats.position;
    if (position === 'above') return { text: 'Above your usual range', tone: 'clear' };
    if (position === 'below') return { text: 'Below your usual range', tone: 'clear' };
    return { text: 'Within your usual range', tone: 'neutral' };
  }
  if (evidence.tool === 'coverage') {
    const low = (evidence.stats.low_wear_days as unknown[] | undefined)?.length ?? 0;
    return {
      text: low ? `${low} low-wear day${low === 1 ? '' : 's'} in this period` : 'Complete',
      tone: 'neutral',
    };
  }
  const result = verdict(evidence);
  if (result) return { text: result.text, tone: result.clear ? 'clear' : 'unclear' };
  const mean = num(evidence, 'mean');
  return {
    text: mean === null ? 'A summary' : `Averaged ${valueText(evidence.metrics[0], mean)}`,
    tone: 'neutral',
  };
}

export interface Figure {
  label: string;
  value: string;
}

/** The two to four numbers that answer the question. */
export function figures(evidence: Evidence): Figure[] {
  const metric = evidence.metrics[0];
  const value = (key: string) => {
    const n = num(evidence, key);
    return n === null ? null : valueText(metric, n);
  };
  const out: (Figure | null)[] = [];
  const add = (label: string, text: string | null) =>
    out.push(text ? { label, value: text } : null);
  switch (evidence.tool) {
    case 'compare_windows': {
      add('Recent average', value('mean_recent'));
      add('Before', value('mean_baseline'));
      const delta = num(evidence, 'cliffs_delta');
      add('Size of the difference', delta === null ? null : `${strength(delta)}`);
      break;
    }
    case 'compare_day': {
      add('That day', value('value'));
      const low = num(evidence, 'usual_low');
      const high = num(evidence, 'usual_high');
      add(
        'Usual range',
        low !== null && high !== null
          ? rangeText(metric, { low, high, median: low, days: 0 })
          : null,
      );
      add('Usual (median)', value('usual_median'));
      break;
    }
    case 'trend':
      add('Change over the period', value('change_over_window'));
      add('Per day', value('slope_per_day'));
      break;
    case 'change_point': {
      add('Before', value('mean_before'));
      add('After', value('mean_after'));
      const date = evidence.stats.change_date;
      add('From', typeof date === 'string' ? shortDate(date) : null);
      break;
    }
    case 'correlate': {
      const rho = num(evidence, 'rho');
      add('Strength', rho === null ? null : `${strength(rho)} (${rho.toFixed(2)})`);
      add(
        'Direction',
        rho === null ? null : rho > 0 ? 'Rise together' : 'One rises as the other falls',
      );
      const lag = num(evidence, 'best_lag');
      add(
        'Delay',
        lag === null ? null : lag === 0 ? 'Same day' : `${lag} day${lag > 1 ? 's' : ''}`,
      );
      break;
    }
    case 'weekday_split':
      add('Weekends', value('mean_weekend'));
      add('Weekdays', value('mean_weekday'));
      break;
    case 'describe':
      add('Average', value('mean'));
      add('Lowest', value('min'));
      add('Highest', value('max'));
      break;
  }
  return out.filter((f): f is Figure => f !== null);
}

const METHODS: Record<string, string> = {
  compare_windows:
    'The days of the recent period were compared with the days before (a Mann-Whitney test). ' +
    'The size says how much the two periods overlap: small means they mostly overlap.',
  compare_day:
    'That day was placed against the middle half of your 28 days before it. This describes ' +
    'the day; it is not a test of a change.',
  trend: 'A line was fitted through the period (Theil-Sen, which ignores single odd days).',
  change_point:
    'Every possible day was tried as the start of a new level, and a shuffle test checked ' +
    'whether the best one could happen by chance.',
  correlate:
    'Whether the two rise and fall together day by day (Spearman), also with a delay of a few ' +
    'days. This shows they move together, not that one causes the other.',
  weekday_split: 'Weekend days were compared with weekdays (a Mann-Whitney test).',
  describe: 'A summary of the days in the period.',
  coverage: 'How many days had data for each metric, and which days the tracker was barely worn.',
};

export function method(evidence: Evidence): string {
  return METHODS[evidence.tool] ?? 'A computation on your own data.';
}

/** How sure the result is, in words, with the p-value it was judged on; null for descriptions. */
export function certainty(evidence: Evidence): string | null {
  const raw = num(evidence, 'p_value');
  if (raw === null) return null;
  const run = num(evidence, 'p_value_run_adjusted');
  const tests = num(evidence, 'tests_in_run');
  const judged = run ?? num(evidence, 'p_value_adjusted') ?? raw;
  const across =
    run !== null && tests
      ? ` after counting the ${tests} checks in this answer (${formatP(raw)} on its own)`
      : judged !== raw
        ? ` after counting the report's other checks (${formatP(raw)} on its own)`
        : '';
  const clear = judged < 0.05 ? 'below 0.05, so it is unlikely to be chance' : 'not below 0.05';
  return `p = ${formatP(judged)}${across}: ${clear}.`;
}

/** The periods in words, e.g. "Oct 12 – Oct 25 against Sep 14 – Oct 11". */
export function periods(evidence: Evidence): string {
  if (evidence.tool === 'compare_day' && evidence.windows.length === 2) {
    return `${shortDate(evidence.windows[0].start)}, against ${windowLabel(evidence.windows[1])}`;
  }
  return evidence.windows.map(windowLabel).join(' against ');
}

export interface ChartPlan {
  metrics: string[]; // one chart each
  end: ISODate;
  days: number; // 7..366
  highlight?: Window;
  marker?: ISODate;
  usual?: { median: number; low: number; high: number; days: number };
}

/** What to chart: the days the evidence covers, with the part it is about highlighted. */
export function chartPlan(evidence: Evidence): ChartPlan | null {
  if (evidence.tool === 'coverage' || !evidence.windows.length || !evidence.metrics.length) {
    return null;
  }
  const starts = evidence.windows.map((w) => w.start).sort();
  const ends = evidence.windows.map((w) => w.end).sort();
  const start = starts[0];
  const end = ends[ends.length - 1];
  const span = Math.round((Date.parse(end) - Date.parse(start)) / 86_400_000) + 1;
  const days = Math.min(366, Math.max(7, span));
  const plan: ChartPlan = { metrics: evidence.metrics.slice(0, 2), end, days };
  if (evidence.tool === 'compare_windows') plan.highlight = evidence.windows[0];
  if (evidence.tool === 'change_point' && typeof evidence.stats.change_date === 'string') {
    plan.highlight = { start: evidence.stats.change_date, end };
  }
  if (evidence.tool === 'compare_day') {
    plan.marker = evidence.windows[0].start;
    const [median, low, high] = ['usual_median', 'usual_low', 'usual_high'].map((k) =>
      num(evidence, k),
    );
    if (median !== null && low !== null && high !== null) {
      plan.usual = { median, low, high, days: num(evidence, 'usual_days') ?? 0 };
    }
  }
  return plan;
}
