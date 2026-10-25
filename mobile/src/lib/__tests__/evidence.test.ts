import type { Evidence } from '@/api/types';

import { answer, certainty, chartPlan, figures, method, periods, question } from '../evidence';

const window = (start: string, end: string) => ({ start, end });

const compare: Evidence = {
  id: 'ev_1',
  tool: 'compare_windows',
  metrics: ['sleep_minutes'],
  windows: [window('2026-10-12', '2026-10-25'), window('2026-09-14', '2026-10-11')],
  n: 42,
  sufficient: true,
  stats: {
    mean_recent: 452,
    mean_baseline: 430,
    cliffs_delta: 0.4,
    p_value: 0.016,
    p_value_run_adjusted: 0.096,
    tests_in_run: 6,
  },
};

const day: Evidence = {
  id: 'ev_2',
  tool: 'compare_day',
  metrics: ['resting_hr'],
  windows: [window('2026-10-25', '2026-10-25'), window('2026-09-27', '2026-10-24')],
  n: 28,
  sufficient: true,
  stats: {
    value: 66,
    usual_median: 60,
    usual_low: 59,
    usual_high: 61,
    usual_days: 28,
    position: 'above',
  },
};

it('asks and answers in plain words, judged on the corrected p-value', () => {
  expect(question(compare)).toBe('Did time asleep change?');
  expect(answer(compare).tone).toBe('unclear');
  expect(answer(compare).text).toMatch('6 checks');
  expect(certainty(compare)).toBe(
    'p = 0.096 after counting the 6 checks in this answer (0.016 on its own): not below 0.05.',
  );
  expect(question(day)).toBe('How was resting heart rate that day, against your usual?');
  expect(answer(day)).toEqual({ text: 'Above your usual range', tone: 'clear' });
  expect(certainty(day)).toBeNull(); // a description, not a test
  expect(answer({ ...day, sufficient: false }).text).toBe('Too few days to tell');
});

it('shows the figures that answer the question, formatted like the rest of the app', () => {
  expect(figures(compare)).toEqual([
    { label: 'Recent average', value: '7h 32m' },
    { label: 'Before', value: '7h 10m' },
    { label: 'Size of the difference', value: 'medium' },
  ]);
  expect(figures(day)).toEqual([
    { label: 'That day', value: '66 bpm' },
    { label: 'Usual range', value: '59–61 bpm' },
    { label: 'Usual (median)', value: '60 bpm' },
  ]);
  expect(method(day)).toMatch('not a test');
  expect(periods(day)).toBe('Oct 25, against Sep 27 – Oct 24');
});

it('charts the days the evidence covers, with its part highlighted', () => {
  expect(chartPlan(compare)).toEqual({
    metrics: ['sleep_minutes'],
    end: '2026-10-25',
    days: 42,
    highlight: compare.windows[0],
  });
  const plan = chartPlan(day)!;
  expect(plan.marker).toBe('2026-10-25');
  expect(plan.usual).toEqual({ median: 60, low: 59, high: 61, days: 28 });
  expect(plan.days).toBe(29);
  const coverage = { ...compare, tool: 'coverage', stats: { fraction_present: {} } };
  expect(chartPlan(coverage)).toBeNull();
});
