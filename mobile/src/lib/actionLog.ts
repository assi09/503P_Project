import type { HealthLog } from '@/api/types';

/** Form strings become explicit units; empty optional values stay unknown, never zero. */
export function editLog(original: HealthLog, fields: Record<string, string>): HealthLog {
  const numeric = new Set(['energyKcal', 'proteinG', 'carbohydrateG', 'fatG', 'activeSeconds', 'distanceKm']);
  const result = { ...original } as unknown as Record<string, unknown>;
  for (const [key, text] of Object.entries(fields)) {
    if (numeric.has(key)) {
      if (!text.trim()) {
        if (key === 'activeSeconds') throw new Error('Enter the active duration in seconds.');
        delete result[key];
      } else {
        const number = Number(text);
        if (!Number.isFinite(number) || number < 0) throw new Error('Enter a valid nonnegative number.');
        result[key] = number;
      }
    } else {
      result[key] = text.trim();
    }
  }
  const log = result as unknown as HealthLog;
  validateLog(log);
  return log;
}

export function validateLog(log: HealthLog): void {
  function time(value: string): number {
    if (!/(Z|[+-]\d\d:\d\d)$/.test(value) || !Number.isFinite(Date.parse(value))) {
      throw new Error('Use a date and time with a timezone, such as 2026-10-24T12:00:00+03:00.');
    }
    return Date.parse(value);
  }
  if (log.kind === 'food') {
    if (!log.foodName.trim() || log.foodName.length > 160) throw new Error('Enter a food name.');
    time(log.consumedAt);
    if (!['BREAKFAST', 'LUNCH', 'DINNER', 'SNACK'].includes(log.mealType)) throw new Error('Choose BREAKFAST, LUNCH, DINNER or SNACK.');
    const values = [log.energyKcal, log.proteinG, log.carbohydrateG, log.fatG].filter((v) => v != null);
    if (!values.length || values.some((n) => !Number.isFinite(n) || n < 0 || n > 100000)) {
      throw new Error('Enter at least one energy or macro value within the supported range.');
    }
  } else {
    if (!['RUNNING', 'WALKING', 'BIKING', 'AEROBIC_WORKOUT'].includes(log.exerciseType)) throw new Error('Choose a supported workout type.');
    const elapsed = (time(log.endTime) - time(log.startTime)) / 1000;
    if (!Number.isInteger(log.activeSeconds) || log.activeSeconds <= 0 || log.activeSeconds > elapsed) {
      throw new Error('Active seconds must be positive and fit within the workout.');
    }
    if (log.distanceKm != null && (!Number.isFinite(log.distanceKm) || log.distanceKm < 0)) throw new Error('Enter a valid distance in km.');
  }
}

/** Same explicit entry at the same instant is a duplicate, even with another timezone offset. */
export function logSignature(log: HealthLog): string {
  const source = log as unknown as Record<string, unknown>;
  const keys = log.kind === 'food' ? ['kind', 'foodName', 'consumedAt'] : ['kind', 'exerciseType', 'startTime', 'endTime'];
  const canonical = Object.fromEntries(keys.map((key) => [key, source[key]]));
  for (const key of ['consumedAt', 'startTime', 'endTime']) {
    if (typeof canonical[key] === 'string') canonical[key] = new Date(canonical[key]).toISOString();
  }
  if (typeof canonical.foodName === 'string') canonical.foodName = canonical.foodName.trim().toLowerCase().replace(/\s+/g, ' ');
  return JSON.stringify(canonical, Object.keys(canonical).sort());
}
