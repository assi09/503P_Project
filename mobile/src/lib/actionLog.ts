import type { HealthAction, HealthLog } from '@/api/types';

type FoodLog = Extract<HealthLog, { kind: 'food' }>;
type WorkoutLog = Extract<HealthLog, { kind: 'workout' }>;

export const MEALS: Record<FoodLog['mealType'], string> = {
  BREAKFAST: 'Breakfast',
  LUNCH: 'Lunch',
  DINNER: 'Dinner',
  SNACK: 'Snack',
};

export const WORKOUTS: Record<WorkoutLog['exerciseType'], string> = {
  RUNNING: 'Run',
  WALKING: 'Walk',
  BIKING: 'Ride',
  AEROBIC_WORKOUT: 'Workout',
};

export const STATUS: Record<HealthAction['status'], string> = {
  draft: 'Draft',
  executing: 'Checking',
  succeeded: 'Logged',
  failed: 'Not logged',
  unknown: 'Checking',
  cancelled: 'Cancelled',
  undoing: 'Removing',
  undone: 'Removed',
};

// The same limits as the backend (backend/app/actions/schemas.py), so mistakes show while typing.
const MAX_KCAL = 5000;
const MAX_MACRO_G = 500;
const MAX_WORKOUT_S = 24 * 3600;
const MAX_DISTANCE_KM = 300;
const MAX_SPEED_KMH: Partial<Record<WorkoutLog['exerciseType'], number>> = {
  RUNNING: 25,
  WALKING: 10,
  BIKING: 80,
};
const FUTURE_GRACE_MS = 15 * 60_000;

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

interface Wall {
  date: string; // 2026-10-24
  time: string; // 13:00
  offset: string; // +03:00
}

/** The date and time as the person entered them, in the entry's own time zone. */
function wall(iso: string): Wall {
  const match = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})(?::\d{2}(?:\.\d+)?)?(Z|[+-]\d{2}:\d{2})$/.exec(
    iso,
  );
  if (!match) throw new Error('Use a date and time with a timezone.');
  return { date: match[1], time: match[2], offset: match[3] === 'Z' ? '+00:00' : match[3] };
}

function dayLabel(date: string): string {
  const [year, month, day] = date.split('-').map(Number);
  const weekday = new Date(Date.UTC(year, month - 1, day)).getUTCDay();
  return `${DAYS[weekday]} ${day} ${MONTHS[month - 1]}`;
}

export function duration(seconds: number): string {
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  return minutes % 60 ? `${hours} h ${minutes % 60} min` : `${hours} h`;
}

function grams(value: number): string {
  return `${Math.round(value * 10) / 10} g`;
}

/** "Lunch · Chicken salad", or "Run". */
export function logTitle(log: HealthLog): string {
  return log.kind === 'food'
    ? `${MEALS[log.mealType]} · ${log.foodName}`
    : WORKOUTS[log.exerciseType];
}

/** The parts of the summary line, e.g. ["Sat 24 Oct, 13:00", "550 kcal", "P 40 g · C 30 g"]. */
export function logDetails(log: HealthLog): string[] {
  if (log.kind === 'food') {
    const at = wall(log.consumedAt);
    const macros = [
      log.proteinG != null && `P ${grams(log.proteinG)}`,
      log.carbohydrateG != null && `C ${grams(log.carbohydrateG)}`,
      log.fatG != null && `F ${grams(log.fatG)}`,
    ].filter(Boolean);
    return [
      `${dayLabel(at.date)}, ${at.time}`,
      ...(log.energyKcal != null ? [`${Math.round(log.energyKcal)} kcal`] : []),
      ...(macros.length ? [macros.join(' · ')] : []),
    ];
  }
  const start = wall(log.startTime);
  const end = wall(log.endTime);
  return [
    `${dayLabel(start.date)}, ${start.time}–${end.time}`,
    duration(log.activeSeconds),
    ...(log.distanceKm != null ? [`${Math.round(log.distanceKm * 100) / 100} km`] : []),
  ];
}

/** The edit form's fields: plain text, local date and time, duration as h:mm. */
export type LogForm = Record<string, string>;

export function formFromLog(log: HealthLog): LogForm {
  if (log.kind === 'food') {
    const at = wall(log.consumedAt);
    return {
      foodName: log.foodName,
      mealType: log.mealType,
      date: at.date,
      time: at.time,
      energyKcal: log.energyKcal?.toString() ?? '',
      proteinG: log.proteinG?.toString() ?? '',
      carbohydrateG: log.carbohydrateG?.toString() ?? '',
      fatG: log.fatG?.toString() ?? '',
    };
  }
  const start = wall(log.startTime);
  const minutes = Math.round(log.activeSeconds / 60);
  return {
    exerciseType: log.exerciseType,
    date: start.date,
    time: start.time,
    duration: `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')}`,
    distanceKm: log.distanceKm?.toString() ?? '',
  };
}

function amount(text: string, what: string): number | undefined {
  if (!text.trim()) return undefined; // left empty: unknown, never zero
  const value = Number(text.replace(',', '.'));
  if (!Number.isFinite(value) || value < 0) throw new Error(`Enter ${what} as a number.`);
  return value;
}

/** "1:30" (h:mm) or "90" (minutes) to seconds. */
function parseDuration(text: string): number {
  const clock = /^(\d{1,2}):([0-5]\d)$/.exec(text.trim());
  const minutes = clock ? Number(clock[1]) * 60 + Number(clock[2]) : Number(text.trim());
  if (!Number.isFinite(minutes) || minutes <= 0) {
    throw new Error('Enter the duration as h:mm, such as 1:30, or in minutes.');
  }
  return Math.round(minutes * 60);
}

function instant(date: string, time: string, offset: string): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date.trim())) throw new Error('Enter the date as YYYY-MM-DD.');
  if (!/^\d{1,2}:\d{2}$/.test(time.trim())) throw new Error('Enter the time as HH:MM.');
  const [hours, minutes] = time.trim().split(':');
  const iso = `${date.trim()}T${hours.padStart(2, '0')}:${minutes}:00${offset}`;
  if (!Number.isFinite(Date.parse(iso))) throw new Error('That date or time does not exist.');
  return iso;
}

/** The edited entry, keeping the original's time zone; throws a message to show if invalid. */
export function logFromForm(original: HealthLog, form: LogForm): HealthLog {
  if (original.kind === 'food') {
    const offset = wall(original.consumedAt).offset;
    const log: FoodLog = {
      kind: 'food',
      foodName: (form.foodName ?? '').trim(),
      mealType: form.mealType as FoodLog['mealType'],
      consumedAt: instant(form.date ?? '', form.time ?? '', offset),
      energyKcal: amount(form.energyKcal ?? '', 'calories'),
      proteinG: amount(form.proteinG ?? '', 'protein'),
      carbohydrateG: amount(form.carbohydrateG ?? '', 'carbohydrates'),
      fatG: amount(form.fatG ?? '', 'fat'),
      provenance: 'user_entered',
    };
    for (const key of ['energyKcal', 'proteinG', 'carbohydrateG', 'fatG'] as const) {
      if (log[key] === undefined) delete log[key];
    }
    validateLog(log);
    return log;
  }
  const offset = wall(original.startTime).offset;
  const startTime = instant(form.date ?? '', form.time ?? '', offset);
  const activeSeconds = parseDuration(form.duration ?? '');
  const end = new Date(Date.parse(startTime) + activeSeconds * 1000);
  const log: WorkoutLog = {
    kind: 'workout',
    exerciseType: form.exerciseType as WorkoutLog['exerciseType'],
    startTime,
    endTime: withOffset(end, offset),
    activeSeconds,
    distanceKm: amount(form.distanceKm ?? '', 'the distance'),
    provenance: 'user_entered',
  };
  if (log.distanceKm === undefined) delete log.distanceKm;
  validateLog(log);
  return log;
}

/** An instant written in a given offset, e.g. 2026-10-24T11:00:00+03:00. */
function withOffset(moment: Date, offset: string): string {
  const sign = offset.startsWith('-') ? -1 : 1;
  const [hours, minutes] = offset.slice(1).split(':').map(Number);
  const local = new Date(moment.getTime() + sign * (hours * 60 + minutes) * 60_000);
  return `${local.toISOString().slice(0, 19)}${offset}`;
}

export function validateLog(log: HealthLog, now: number = Date.now()): void {
  function time(value: string): number {
    if (!/(Z|[+-]\d\d:\d\d)$/.test(value) || !Number.isFinite(Date.parse(value))) {
      throw new Error('Use a date and time with a timezone, such as 2026-10-24T12:00:00+03:00.');
    }
    const at = Date.parse(value);
    if (at > now + FUTURE_GRACE_MS) throw new Error('A log cannot be in the future.');
    return at;
  }
  if (log.kind === 'food') {
    if (!log.foodName.trim() || log.foodName.length > 160) throw new Error('Enter a food name.');
    time(log.consumedAt);
    if (!(log.mealType in MEALS)) throw new Error('Choose a meal.');
    const macros = [log.proteinG, log.carbohydrateG, log.fatG].filter((v) => v != null);
    if (log.energyKcal == null && !macros.length) {
      throw new Error('Enter the calories or at least one macronutrient.');
    }
    if (log.energyKcal != null && log.energyKcal > MAX_KCAL) {
      throw new Error(`One entry can have at most ${MAX_KCAL} kcal.`);
    }
    if (macros.some((grams) => grams > MAX_MACRO_G)) {
      throw new Error(`One entry can have at most ${MAX_MACRO_G} g of each macronutrient.`);
    }
    return;
  }
  if (!(log.exerciseType in WORKOUTS)) throw new Error('Choose a workout type.');
  const elapsed = (time(log.endTime) - time(log.startTime)) / 1000;
  if (
    !Number.isInteger(log.activeSeconds) ||
    log.activeSeconds <= 0 ||
    log.activeSeconds > elapsed
  ) {
    throw new Error('The active time must fit within the workout.');
  }
  if (elapsed > MAX_WORKOUT_S) throw new Error('One workout can last at most 24 hours.');
  if (log.distanceKm != null) {
    if (!Number.isFinite(log.distanceKm) || log.distanceKm < 0) {
      throw new Error('Enter a valid distance in km.');
    }
    if (log.distanceKm > MAX_DISTANCE_KM) {
      throw new Error(`One workout can cover at most ${MAX_DISTANCE_KM} km.`);
    }
    const limit = MAX_SPEED_KMH[log.exerciseType];
    if (limit && log.distanceKm / (log.activeSeconds / 3600) > limit) {
      throw new Error('That distance is too far for the time.');
    }
  }
}

/** Same explicit entry at the same instant is a duplicate, even with another timezone offset. */
export function logSignature(log: HealthLog): string {
  const source = log as unknown as Record<string, unknown>;
  const keys =
    log.kind === 'food'
      ? ['kind', 'foodName', 'consumedAt']
      : ['kind', 'exerciseType', 'startTime', 'endTime'];
  const canonical = Object.fromEntries(keys.map((key) => [key, source[key]]));
  for (const key of ['consumedAt', 'startTime', 'endTime']) {
    if (typeof canonical[key] === 'string') {
      canonical[key] = new Date(canonical[key] as string).toISOString();
    }
  }
  if (typeof canonical.foodName === 'string') {
    canonical.foodName = canonical.foodName.trim().toLowerCase().replace(/\s+/g, ' ');
  }
  return JSON.stringify(canonical, Object.keys(canonical).sort());
}
