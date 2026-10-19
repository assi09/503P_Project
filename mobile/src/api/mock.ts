// In-memory stand-in for the backend, used until the API exists. All values are made up.
import { shortDate } from '@/lib/format';

import type {
  ApiClient,
  ChatMessage,
  ContextQuestion,
  DataStatus,
  Evidence,
  Finding,
  ISODate,
  Point,
  Reminder,
  Report,
} from './types';

const DAYS = 28;
const LATENCY_MS = 400;

function isoDate(daysAgo: number): ISODate {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() - daysAgo);
  return date.toISOString().slice(0, 10);
}

// Small deterministic PRNG so the charts look the same on every reload.
function random(seed: number): () => number {
  let state = seed;
  return () => {
    state = (state * 1664525 + 1013904223) % 2 ** 32;
    return state / 2 ** 32;
  };
}

function series(seed: number, base: number, noise: number, shift: number, shiftDay: number): Point[] {
  const next = random(seed);
  return Array.from({ length: DAYS }, (_, i) => {
    const daysAgo = DAYS - 1 - i;
    const value = base + (next() - 0.5) * 2 * noise + (daysAgo < shiftDay ? shift : 0);
    return { date: isoDate(daysAgo), value: Math.round(value * 10) / 10 };
  });
}

const recent = { start: isoDate(13), end: isoDate(0) };
const baseline = { start: isoDate(27), end: isoDate(14) };

const evidence: Record<string, Evidence> = {
  ev_eff: {
    id: 'ev_eff',
    tool: 'compare_windows',
    metrics: ['sleep_efficiency'],
    windows: [recent, baseline],
    n: 27,
    sufficient: true,
    stats: { mean_recent: 86.1, mean_baseline: 91.6, difference: -5.5, pct_change: -6.0, cliffs_delta: -0.71, p_value: 0.0008 },
  },
  ev_bed: {
    id: 'ev_bed',
    tool: 'compare_windows',
    metrics: ['bedtime_hour'],
    windows: [recent, baseline],
    n: 27,
    sufficient: true,
    stats: { mean_recent: 0.4, mean_baseline: -0.45, difference: 0.85, cliffs_delta: 0.64, p_value: 0.002 },
  },
  ev_corr: {
    id: 'ev_corr',
    tool: 'correlate',
    metrics: ['bedtime_hour', 'sleep_efficiency'],
    windows: [{ start: isoDate(27), end: isoDate(0) }],
    n: 27,
    sufficient: true,
    stats: { lags_tested: 3, best_lag: 0, rho: -0.58, p_value: 0.0015, p_value_adjusted: 0.0045 },
  },
  ev_steps: {
    id: 'ev_steps',
    tool: 'trend',
    metrics: ['steps'],
    windows: [{ start: isoDate(27), end: isoDate(0) }],
    n: 28,
    sufficient: true,
    stats: { slope_per_day: 61.2, slope_low: 22.5, slope_high: 98.0, change_over_window: 1652, kendall_tau: 0.33, p_value: 0.013 },
  },
};

const findings: Finding[] = [
  {
    id: 'f_eff',
    title: 'Sleep efficiency dropped',
    summary: 'Your sleep efficiency averaged 86% over the last two weeks, down from 92% the two weeks before.',
    metric: 'sleep_efficiency',
    unit: '%',
    direction: 'down',
    change: '-6%',
    series: series(1, 91.5, 2.5, -5.5, 14),
    highlight: recent,
    evidenceIds: ['ev_eff'],
  },
  {
    id: 'f_bed',
    title: 'Bedtime moved later',
    summary:
      'You went to bed about 50 minutes later on average, and later nights went with lower sleep efficiency.',
    metric: 'bedtime_hour',
    unit: 'h',
    direction: 'up',
    change: '+50 min',
    series: series(2, -0.45, 0.5, 0.85, 14),
    highlight: recent,
    evidenceIds: ['ev_bed', 'ev_corr'],
  },
  {
    id: 'f_steps',
    title: 'Steps trending up',
    summary: 'Daily steps rose by about 60 a day over the last four weeks, around 1,650 more per day overall.',
    metric: 'steps',
    unit: 'steps',
    direction: 'up',
    change: '+1,650/day',
    series: series(3, 8200, 1400, 0, 0).map((point, i) => ({ ...point, value: Math.round((point.value ?? 0) + i * 61) })),
    evidenceIds: ['ev_steps'],
  },
];

let questions: ContextQuestion[] = [
  {
    id: 'q_shift',
    prompt: `Your bedtime shifted around ${shortDate(isoDate(14))}. Did something change?`,
    date: isoDate(14),
    options: ['Travel', 'Work schedule', 'Exams', 'Training', 'Nothing'],
    answer: null,
  },
];

let reminders: Reminder[] = [
  {
    id: 'r_wind',
    title: 'Wind down',
    message: 'Time to start winding down for bed.',
    schedule: 'Weeknights at 23:00',
    reason: 'Later bedtimes went with lower sleep efficiency over the last four weeks.',
    findingId: 'f_bed',
    status: 'proposed',
  },
  {
    id: 'r_sync',
    title: 'Sync reminder',
    message: "Your data hasn't synced in 3 days.",
    schedule: 'When data is 3 days old',
    reason: 'Analysis needs recent data.',
    findingId: null,
    status: 'active',
  },
];

let chat: ChatMessage[] = [];

const MEDICAL = /\b(diagnos|disease|illness|sick|medic|medication|doctor|symptom|treat|apnea|afib|heart attack)/i;

function reply(text: string, findingId?: string): Omit<ChatMessage, 'id' | 'createdAt'> {
  if (MEDICAL.test(text)) {
    return {
      role: 'assistant',
      text: "I can describe patterns in your Fitbit data, but I can't diagnose or give medical advice. For health concerns, please talk to a doctor.",
      evidenceIds: [],
      refused: true,
    };
  }
  // The attached finding decides the topic; otherwise fall back to keywords in the question.
  const topic = findingId === 'f_steps' ? 'steps' : findingId ? 'sleep' : undefined;
  if (topic === 'sleep' || (!topic && /sleep|efficien|bed|why/i.test(text))) {
    return {
      role: 'assistant',
      text: 'Sleep efficiency fell from 92% to 86% between the two halves of the last four weeks. Over the same period your bedtime moved about 50 minutes later, and nights with later bedtimes had lower efficiency. That is a correlation in your data, not proof that bedtime is the cause.',
      evidenceIds: ['ev_eff', 'ev_bed', 'ev_corr'],
    };
  }
  if (topic === 'steps' || /step|walk|activ/i.test(text)) {
    return {
      role: 'assistant',
      text: 'Your steps have been rising steadily, by about 60 a day over four weeks, which adds up to around 1,650 more steps per day.',
      evidenceIds: ['ev_steps'],
    };
  }
  return {
    role: 'assistant',
    text: 'I can look into trends, changes between periods, and how your metrics relate, for example sleep, activity, heart rate or recovery. What would you like to know?',
    evidenceIds: [],
  };
}

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(structuredClone(value)), LATENCY_MS));
}

function message(fields: Omit<ChatMessage, 'id' | 'createdAt'>): ChatMessage {
  return { ...fields, id: `m${chat.length + 1}`, createdAt: new Date().toISOString() };
}

export const mockClient: ApiClient = {
  getLatestReport: () =>
    delay<Report>({
      id: 'report_latest',
      period: { start: isoDate(27), end: isoDate(0) },
      createdAt: new Date().toISOString(),
      headline: 'Your sleep got less efficient as your bedtime moved later.',
      findings,
      questions,
      evidence,
    }),

  getEvidence: (id) =>
    evidence[id] ? delay(evidence[id]) : Promise.reject(new Error('This evidence no longer exists.')),

  answerQuestion: (questionId, answer) => {
    questions = questions.map((q) => (q.id === questionId ? { ...q, answer } : q));
    const updated = questions.find((q) => q.id === questionId);
    return updated ? delay(updated) : Promise.reject(new Error('Unknown question'));
  },

  getChat: () => delay(chat),

  sendMessage: (text, findingId) => {
    const added = [message({ role: 'user', text, evidenceIds: [], ...(findingId && { findingId }) })];
    chat = [...chat, ...added];
    const answer = message(reply(text, findingId));
    chat = [...chat, answer];
    return delay([...added, answer]);
  },

  getReminders: () => delay(reminders),

  setReminderStatus: (id, status) => {
    reminders = reminders.map((r) => (r.id === id ? { ...r, status } : r));
    const updated = reminders.find((r) => r.id === id);
    return updated ? delay(updated) : Promise.reject(new Error('Unknown reminder'));
  },

  getDataStatus: () =>
    delay<DataStatus>({
      source: 'takeout',
      lastSync: new Date(Date.now() - 2 * 3600_000).toISOString(),
      range: { start: isoDate(110), end: isoDate(0) },
      coverage: [
        { metric: 'steps', label: 'Steps', fractionPresent: 1 },
        { metric: 'sleep_minutes', label: 'Sleep', fractionPresent: 0.96 },
        { metric: 'hrv_ms', label: 'HRV', fractionPresent: 0.93 },
        { metric: 'readiness', label: 'Readiness', fractionPresent: 0.89 },
        { metric: 'skin_temp_variation_c', label: 'Skin temperature', fractionPresent: 0.86 },
      ],
      lowWearDays: [isoDate(40), isoDate(39)],
    }),
};
