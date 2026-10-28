import type { ISODate, ReminderSchedule } from '@/api/types';

/** Monday first, as the backend counts them (0 is Monday). */
export const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] as const;
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "HH:MM" on a 24-hour clock, the only form the backend accepts. */
export function validTime(value: string): boolean {
  return /^([01]\d|2[0-3]):[0-5]\d$/.test(value.trim());
}

/** Accepts "7", "7:5", "0730", "19.30" and returns "07:00", "07:05", "07:30", "19:30", or null. */
export function normalizeTime(value: string): string | null {
  const digits = value.trim().replace(/[.h]/gi, ':');
  const match = /^(\d{1,2})(?::?(\d{1,2}))?$/.exec(digits);
  if (!match) return null;
  const hours = Number(match[1]);
  const minutes = Number(match[2] ?? 0);
  if (hours > 23 || minutes > 59) return null;
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
}

/** Monday-first weekday of an ISO date, read as a calendar day (no time zone shift). */
export function weekdayOf(date: ISODate): number {
  const [y, m, d] = date.split('-').map(Number);
  return (new Date(Date.UTC(y, m - 1, d)).getUTCDay() + 6) % 7;
}

/** The schedule in a few words, as the backend writes it: "Weeknights at 22:30". */
export function describeSchedule(schedule: ReminderSchedule): string {
  const at = schedule.time;
  if (schedule.kind === 'once') {
    const [, m, d] = schedule.date.split('-').map(Number);
    return `Once, ${WEEKDAYS[weekdayOf(schedule.date)]} ${d} ${MONTHS[m - 1]} at ${at}`;
  }
  const days = [...new Set(schedule.weekdays)].sort((a, b) => a - b);
  if (days.length === 7) return `Every day at ${at}`;
  if (days.join() === '0,1,2,3,4') return `${at >= '18:00' ? 'Weeknights' : 'Weekdays'} at ${at}`;
  if (days.join() === '5,6') return `Weekends at ${at}`;
  return `${days.map((d) => WEEKDAYS[d]).join(', ')} at ${at}`;
}

/** The next time a schedule is due after `from`, in the device's own time zone (for the mock). */
export function nextDue(schedule: ReminderSchedule, from: Date = new Date()): Date | null {
  const [hours, minutes] = schedule.time.split(':').map(Number);
  if (schedule.kind === 'once') {
    const [y, m, d] = schedule.date.split('-').map(Number);
    const due = new Date(y, m - 1, d, hours, minutes);
    return due > from ? due : null;
  }
  for (let offset = 0; offset < 8; offset++) {
    const day = new Date(from.getFullYear(), from.getMonth(), from.getDate() + offset);
    const due = new Date(day.getFullYear(), day.getMonth(), day.getDate(), hours, minutes);
    if (schedule.weekdays.includes((day.getDay() + 6) % 7) && due > from) return due;
  }
  return null;
}

/** "in 3 h", "in 2 days", "tomorrow at 07:00": when a reminder comes next. */
export function dueText(nextDueAt: string | null, now: Date = new Date()): string | null {
  if (!nextDueAt) return null;
  const due = new Date(nextDueAt);
  const minutes = Math.round((due.getTime() - now.getTime()) / 60_000);
  if (minutes < 1) return 'now';
  if (minutes < 60) return `in ${minutes} min`;
  if (minutes < 18 * 60) return `in ${Math.round(minutes / 60)} h`;
  const days = Math.round(minutes / (24 * 60));
  return days <= 1 ? 'tomorrow' : `in ${days} days`;
}
