import {
  describeSchedule,
  dueText,
  nextDue,
  normalizeTime,
  validTime,
  weekdayOf,
} from '../reminders';

describe('reminder schedules', () => {
  it('reads like the backend writes them', () => {
    const weekly = (time: string, weekdays: number[]) =>
      describeSchedule({ kind: 'weekly', time, weekdays });
    expect(weekly('07:00', [0, 1, 2, 3, 4, 5, 6])).toBe('Every day at 07:00');
    expect(weekly('22:30', [0, 1, 2, 3, 4])).toBe('Weeknights at 22:30');
    expect(weekly('08:15', [4, 0, 1, 2, 3])).toBe('Weekdays at 08:15');
    expect(weekly('10:00', [6, 5])).toBe('Weekends at 10:00');
    expect(weekly('18:00', [4, 0, 2])).toBe('Mon, Wed, Fri at 18:00');
    expect(describeSchedule({ kind: 'once', date: '2026-10-29', time: '07:00' })).toBe(
      'Once, Thu 29 Oct at 07:00',
    );
  });

  it('understands times as people type them', () => {
    expect(normalizeTime('7')).toBe('07:00');
    expect(normalizeTime('7:5')).toBe('07:05');
    expect(normalizeTime('0730')).toBe('07:30');
    expect(normalizeTime('19.30')).toBe('19:30');
    expect(normalizeTime('24:00')).toBeNull();
    expect(normalizeTime('soon')).toBeNull();
    expect(validTime('22:30')).toBe(true);
    expect(validTime('9:30')).toBe(false);
  });

  it('finds the next due time on the chosen days', () => {
    const wednesdayMorning = new Date(2026, 9, 28, 9, 0); // a Wednesday, local time
    expect(weekdayOf('2026-10-28')).toBe(2);
    const nights = nextDue(
      { kind: 'weekly', time: '22:30', weekdays: [0, 1, 2, 3, 4] },
      wednesdayMorning,
    );
    expect(nights).toEqual(new Date(2026, 9, 28, 22, 30));
    const weekend = nextDue({ kind: 'weekly', time: '10:00', weekdays: [5, 6] }, wednesdayMorning);
    expect(weekend).toEqual(new Date(2026, 9, 31, 10, 0));
    expect(
      nextDue({ kind: 'once', date: '2026-10-27', time: '08:00' }, wednesdayMorning),
    ).toBeNull();
  });

  it('says when a reminder comes next in a few words', () => {
    const now = new Date('2026-10-28T09:00:00Z');
    expect(dueText(null, now)).toBeNull();
    expect(dueText('2026-10-28T09:20:00Z', now)).toBe('in 20 min');
    expect(dueText('2026-10-28T20:30:00Z', now)).toBe('in 12 h');
    expect(dueText('2026-10-29T20:30:00Z', now)).toBe('tomorrow');
    expect(dueText('2026-11-02T20:30:00Z', now)).toBe('in 5 days');
  });
});
