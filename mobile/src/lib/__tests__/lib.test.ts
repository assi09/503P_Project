import type { Evidence, Point } from '@/api/types';

import { chartGeometry } from '../chart';
import { formatP, formatValue, keyStats, shortDate, strength } from '../format';

const points = (values: (number | null)[]): Point[] =>
  values.map((value, i) => ({ date: `2026-10-${String(i + 1).padStart(2, '0')}`, value }));

describe('chartGeometry', () => {
  it('draws one path for a complete series, spanning the box', () => {
    const { paths, min, max } = chartGeometry(points([1, 3, 2]), 100, 50, undefined, 0);
    expect(paths).toEqual(['M0,50 L50,0 L100,25']);
    expect([min, max]).toEqual([1, 3]);
  });

  it('breaks the line at missing days instead of interpolating', () => {
    const { paths } = chartGeometry(points([1, 2, null, 3, 4]), 100, 50);
    expect(paths).toHaveLength(2);
  });

  it('draws a flat series through the middle', () => {
    const { paths } = chartGeometry(points([5, 5]), 100, 50, undefined, 0);
    expect(paths).toEqual(['M0,25 L100,25']);
  });

  it('returns nothing to draw without data', () => {
    expect(chartGeometry(points([null, null]), 100, 50).paths).toEqual([]);
    expect(chartGeometry([], 100, 50).paths).toEqual([]);
  });

  it('shades the highlighted window up to the right edge', () => {
    const { highlight } = chartGeometry(points([1, 2, 3, 4, 5]), 100, 50, {
      start: '2026-10-04',
      end: '2026-10-05',
    }, 0);
    expect(highlight).toEqual({ x: 62.5, width: 37.5 });
  });

  it('ignores a highlight outside the series', () => {
    const { highlight } = chartGeometry(points([1, 2]), 100, 50, { start: '2027-01-01', end: '2027-01-02' });
    expect(highlight).toBeNull();
  });
});

describe('formatting', () => {
  it('formats dates without depending on the timezone', () => {
    expect(shortDate('2026-10-01')).toBe('Oct 1');
  });

  it('shows bedtime as a clock time on either side of midnight', () => {
    expect(formatValue('bedtime_hour', -0.5)).toBe('23:30');
    expect(formatValue('bedtime_hour', 1.25)).toBe('01:15');
  });

  it('rounds large values and keeps one decimal for small ones', () => {
    expect(formatValue('steps', 8234.6)).toBe('8,235');
    expect(formatValue('sleep_efficiency', 86.14)).toBe('86.1');
  });

  it('never shows a p-value of zero', () => {
    expect(formatP(0.0000001)).toBe('< 0.001');
    expect(formatP(0.0123)).toBe('0.012');
  });

  it('labels effect sizes regardless of sign', () => {
    expect(strength(-0.71)).toBe('large');
    expect(strength(0.2)).toBe('small');
    expect(strength(0.05)).toBe('negligible');
  });
});

describe('keyStats', () => {
  const base = { id: 'e', metrics: ['sleep_efficiency'], windows: [], n: 27, sufficient: true };

  it('summarizes a window comparison in plain words', () => {
    const evidence: Evidence = {
      ...base,
      tool: 'compare_windows',
      stats: { mean_recent: 86.1, mean_baseline: 91.6, cliffs_delta: -0.71, p_value: 0.0008 },
    };
    expect(keyStats(evidence)).toEqual([
      { label: 'Recent average', value: '86.1' },
      { label: 'Earlier average', value: '91.6' },
      { label: 'Effect size', value: '-0.71 (large)' },
      { label: 'p-value', value: '< 0.001' },
      { label: 'Days of data', value: '27' },
    ]);
  });

  it('prefers the adjusted p-value when several lags were tried', () => {
    const evidence: Evidence = {
      ...base,
      tool: 'correlate',
      stats: { rho: -0.58, best_lag: 1, p_value: 0.0015, p_value_adjusted: 0.0045 },
    };
    expect(keyStats(evidence)).toContainEqual({ label: 'p-value', value: '0.004' });
    expect(keyStats(evidence)).toContainEqual({ label: 'Delay', value: '1 day' });
  });

  it('skips statistics that are missing', () => {
    const evidence: Evidence = { ...base, tool: 'trend', stats: { slope_per_day: null, p_value: null } };
    expect(keyStats(evidence)).toEqual([{ label: 'Days of data', value: '27' }]);
  });
});
