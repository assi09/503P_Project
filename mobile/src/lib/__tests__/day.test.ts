import type { DayMetric, DaySummary } from '@/api/types';

import {
  bigValue,
  compare,
  dayTitle,
  rangeText,
  shiftDate,
  stages,
  usualLine,
  valueText,
  wakeHour,
} from '../day';

const usual = { median: 60, low: 58, high: 62, days: 28 };
const metric = (name: string, value: number | null, u = usual): DayMetric => ({
  metric: name,
  value,
  usual: u,
  recent: [],
});

describe('days', () => {
  it('moves by calendar days across months and years', () => {
    expect(shiftDate('2026-10-31', 1)).toBe('2026-11-01');
    expect(shiftDate('2026-01-01', -1)).toBe('2025-12-31');
    expect(shiftDate('2028-02-28', 1)).toBe('2028-02-29');
  });

  it('names days relative to the latest one', () => {
    expect(dayTitle('2026-10-25', '2026-10-25')).toBe('Today');
    expect(dayTitle('2026-10-24', '2026-10-25')).toBe('Yesterday');
    expect(dayTitle('2026-10-21', '2026-10-25')).toBe('Wednesday');
    expect(dayTitle('2026-10-12', '2026-10-25')).toBe('Mon 12 Oct');
  });
});

describe('comparing with the usual range', () => {
  it('places a value against the middle half of the weeks before', () => {
    expect(compare(63, usual)).toBe('above');
    expect(compare(57, usual)).toBe('below');
    expect(compare(58, usual)).toBe('usual');
    expect(compare(null, usual)).toBeNull();
    expect(compare(60, null)).toBeNull();
  });

  it("writes a short line, and never calls today's running totals low", () => {
    expect(usualLine(metric('resting_hr', 64))).toBe('Above usual · 58–62 bpm');
    expect(
      usualLine(metric('steps', 1200, { median: 9000, low: 8000, high: 10000, days: 28 }), true),
    ).toBe('So far · usual 8,000–10,000 steps');
    expect(usualLine(metric('resting_hr', 60, null as never))).toMatch('Not enough days');
  });

  it('formats ranges and values the same way as the large figures', () => {
    expect(rangeText('sleep_minutes', { median: 450, low: 425, high: 470, days: 28 })).toBe(
      '7h 05m–7h 50m',
    );
    expect(rangeText('sleep_efficiency', { median: 97, low: 96, high: 98.3, days: 28 })).toBe(
      '96–98.3%',
    );
    expect(
      rangeText('moderately_active_minutes', { median: 40, low: 31, high: 89, days: 28 }),
    ).toBe('31–89 min');
    expect(valueText('sleep_minutes', 489)).toBe('8h 09m');
    expect(valueText('deep_sleep_minutes', 45)).toBe('45 min');
    expect(valueText('resting_hr', 61)).toBe('61 bpm');
    expect(valueText('skin_temp_variation_c', 0.4)).toBe('+0.4 °C');
    expect(bigValue('steps', null)).toEqual({ value: '–' });
  });
});

describe('the night', () => {
  it('works out the wake time from bedtime and time in bed', () => {
    expect(wakeHour(-0.5, 480)).toBe(7.5); // 23:30 + 8 h
    expect(wakeHour(1.5, 600)).toBe(11.5);
    expect(wakeHour(null, 480)).toBeNull();
  });

  it('splits the night into shares of each stage, or none without all four', () => {
    const day = (values: Record<string, number | null>): DaySummary => ({
      date: '2026-10-25',
      partial: false,
      lowWear: false,
      first: '2026-07-01',
      last: '2026-10-25',
      metrics: Object.entries(values).map(([name, value]) => metric(name, value)),
    });
    const night = stages(
      day({
        deep_sleep_minutes: 60,
        light_sleep_minutes: 240,
        rem_sleep_minutes: 90,
        awake_in_bed_minutes: 10,
      }),
    )!;
    expect(night.map((s) => s.key)).toEqual(['awake', 'rem', 'light', 'deep']);
    expect(night.reduce((sum, s) => sum + s.share, 0)).toBeCloseTo(1);
    expect(night[2].share).toBeCloseTo(0.6);
    expect(stages(day({ deep_sleep_minutes: 60, light_sleep_minutes: null }))).toBeNull();
  });
});
