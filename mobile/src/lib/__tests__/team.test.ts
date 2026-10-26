import type { Evidence, TeamReport } from '@/api/types';
import { changeRows, levelMark, shortChange, signedChange, weekdayBars } from '@/lib/team';

function evidence(id: string, stats: Evidence['stats'], sufficient = true): Evidence {
  return { id, tool: 'team_change', metrics: [], windows: [], n: 6, sufficient, stats };
}

describe('team report figures', () => {
  it('writes signed changes in each metric’s unit', () => {
    expect(signedChange('sleep_minutes', -64)).toBe('−1 h 4 min');
    expect(signedChange('sleep_minutes', 12)).toBe('+12 min');
    expect(signedChange('bedtime_hour', 0.2)).toBe('+12 min');
    expect(signedChange('steps', -1148.4)).toBe('−1,148 steps');
    expect(signedChange('resting_hr', 0)).toBe('±0 bpm');
    expect(shortChange('steps', -1310)).toBe('−1.3k steps');
    expect(shortChange('steps', 610)).toBe('+610 steps');
    expect(shortChange('steps', -1310)).toBe('−1.3k steps');
    expect(shortChange('steps', 610)).toBe('+610 steps');
  });

  it('puts changes first and reads the counts from each section’s evidence', () => {
    const report = {
      minimumMembers: 5,
      sections: [
        { metric: 'steps', status: 'steady', text: 'Steps…', evidenceId: 'a' },
        { metric: 'stress_score', status: 'steady', text: 'Stress…', evidenceId: 'c' },
        { metric: 'sleep_minutes', status: 'changed', text: 'Sleep…', evidenceId: 'b' },
      ],
      evidence: {
        a: evidence('a', { members: 6, members_up: 1, members_down: 5, median_change: -1148 }),
        b: evidence('b', { members: 6, members_up: 0, members_down: 6, median_change: -64 }),
        c: evidence('c', { members: 3, minimum_members: 5 }, false),
      },
    } as unknown as TeamReport;
    const rows = changeRows(report);
    expect(rows.map((r) => [r.metric, r.status])).toEqual([
      ['sleep_minutes', 'changed'],
      ['steps', 'steady'],
      ['stress_score', 'not_enough_data'],
    ]);
    expect(rows[0]).toMatchObject({
      label: 'Time asleep',
      up: 0,
      down: 6,
      members: 6,
      median: -64,
    });
    expect(rows[2]).toMatchObject({ members: 3, minimum: 5, median: null });
  });

  it('scales weekday bars to the largest and marks the highest and lowest day', () => {
    const medians = {
      monday: -6,
      tuesday: -11,
      wednesday: -20,
      thursday: 0,
      friday: 4,
      saturday: 40,
      sunday: 22,
    };
    const bars = weekdayBars(evidence('w', { median_deviation_by_weekday: medians }))!;
    expect(bars.map((b) => b.short)).toEqual(['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']);
    expect(bars[5]).toMatchObject({ size: 1, highest: true, lowest: false });
    expect(bars[2]).toMatchObject({ size: 0.5, lowest: true });
    expect(bars.filter((b) => b.highest || b.lowest)).toHaveLength(2);
  });

  it('draws no weekday chart without every day or with too few people', () => {
    expect(weekdayBars(undefined)).toBeNull();
    expect(weekdayBars(evidence('w', { median_deviation_by_weekday: { monday: 1 } }))).toBeNull();
    const all = Object.fromEntries(
      ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'].map((d) => [
        d,
        1,
      ]),
    );
    expect(weekdayBars(evidence('w', { median_deviation_by_weekday: all }, false))).toBeNull();
  });

  it('reads levels with a word, not color alone', () => {
    expect(levelMark('above').word).toBe('Above');
    expect(levelMark('below').icon).toBe('arrow-down');
    expect(levelMark(null).word).toBe('Too few days');
  });
});
