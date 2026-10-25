// In-memory stand-in for the backend, used until the API exists. All values are made up.
import { logSignature, validateLog } from '@/lib/actionLog';
import { expertForMetric } from '@/lib/experts';
import { shortDate } from '@/lib/format';

import { ApiError } from './http';
import { getToken } from './token';
import type {
  AccessRequest,
  Account,
  ApiClient,
  Attachment,
  ChatMessage,
  ContextQuestion,
  DataStatus,
  Depth,
  Evidence,
  Expert,
  Finding,
  GoogleStatus,
  HealthAction,
  HealthLog,
  ISODate,
  NotificationSettings,
  Point,
  Reminder,
  Report,
  SendOptions,
  SignedIn,
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
  ev_hrv: {
    id: 'ev_hrv',
    tool: 'compare_windows',
    metrics: ['hrv_ms'],
    windows: [recent, baseline],
    n: 26,
    sufficient: true,
    stats: { mean_recent: 48.2, mean_baseline: 55.9, difference: -7.7, pct_change: -13.8, cliffs_delta: -0.52, p_value: 0.011 },
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

let notificationSettings: NotificationSettings = {
  quietHours: { start: '22:00', end: '07:00' },
  maxPerDay: 2,
};

const MEDICAL = /\b(diagnos|disease|illness|sick|medic|medication|doctor|symptom|treat|apnea|afib|heart attack)/i;

// Stand-in for the router: keywords per expert. Ties go to the earlier expert in this list.
const TOPICS: [Expert, RegExp][] = [
  ['recovery', /recover|hrv|heart|resting|readiness|breath|respirat|temperature|tired/i],
  ['sleep', /sleep|bed|nap|\brem\b|deep|awake|efficien|night/i],
  ['activity', /step|walk|activ|exercise|workout|train|cardio|\brun|zone/i],
  ['nutrition', /\beat|food|meal|protein|carb|macro|nutri|diet/i],
];

/** Experts a question is about, most likely first. */
export function routeQuestion(text: string): Expert[] {
  return TOPICS.map(([expert, pattern]) => ({
    expert,
    hits: text.match(new RegExp(pattern.source, 'gi'))?.length ?? 0,
  }))
    .filter(({ hits }) => hits > 0)
    .sort((a, b) => b.hits - a.hits)
    .map(({ expert }) => expert);
}

function attachmentExpert(attachment: Attachment | undefined): Expert | undefined {
  if (!attachment) return undefined;
  const metric =
    attachment.kind === 'metric'
      ? attachment.metric
      : findings.find((f) => f.id === attachment.id)?.metric;
  return metric ? expertForMetric(metric) : undefined;
}

type Answer = Pick<ChatMessage, 'text' | 'evidenceIds'>;

function answerAbout(topic: Expert, depth: Depth, consulted: Expert[]): Answer {
  if (topic === 'sleep') {
    return depth === 'deep'
      ? {
          text: 'Sleep efficiency fell from 92% to 86% between the two halves of the last four weeks. Over the same period your bedtime moved about 50 minutes later, and nights with later bedtimes had lower efficiency. That is a correlation in your data, not proof that bedtime is the cause.',
          evidenceIds: ['ev_eff', 'ev_bed', 'ev_corr'],
        }
      : {
          text: 'Sleep efficiency fell from 92% to 86% over the last two weeks, while your bedtime moved about 50 minutes later.',
          evidenceIds: ['ev_eff', 'ev_bed'],
        };
  }
  if (topic === 'recovery') {
    const answer = {
      text: 'Your HRV averaged 48 ms over the last two weeks, down from 56 ms in the two weeks before.',
      evidenceIds: ['ev_hrv'],
    };
    if (consulted.includes('sleep')) {
      answer.text +=
        ' Over the same weeks your bedtime moved about 50 minutes later. Both changed together; the data does not show which caused which.';
      answer.evidenceIds.push('ev_bed');
    }
    return answer;
  }
  if (topic === 'activity') {
    return {
      text: 'Your steps have been rising steadily, by about 60 a day over four weeks, which adds up to around 1,650 more steps per day.',
      evidenceIds: ['ev_steps'],
    };
  }
  return {
    text: "I can't see any nutrition data yet. Once nutrition from Cronometer is imported, I can look at it alongside your sleep and activity.",
    evidenceIds: [],
  };
}

function reply(text: string, options: SendOptions): Omit<ChatMessage, 'id' | 'createdAt'> {
  // The scope check runs whatever expert was chosen, so choosing one cannot skip it.
  if (MEDICAL.test(text)) {
    return {
      role: 'assistant',
      text: "I can describe patterns in your Fitbit data, but I can't diagnose or give medical advice. For health concerns, please talk to a doctor.",
      evidenceIds: [],
      refused: true,
    };
  }
  // An attachment decides the topic; otherwise the question's keywords do.
  const fromAttachment = attachmentExpert(options.attachment);
  const topics = fromAttachment ? [fromAttachment] : routeQuestion(text);
  const chosen = options.expert === 'auto' ? undefined : options.expert;
  const lead = chosen ?? topics[0];

  if (!lead) {
    return {
      role: 'assistant',
      text: 'I can look into trends, changes between periods, and how your metrics relate, for example sleep, activity, heart rate or recovery. What would you like to know?',
      evidenceIds: [],
      answeredBy: 'general',
      routed: true,
    };
  }
  // The lead consults the other experts the question touches; a quick answer consults none.
  const consulted = options.depth === 'deep' ? topics.filter((t) => t !== lead) : [];
  // A chosen expert asked about another expert's metrics answers with what it consulted.
  const topic = chosen && topics.length > 0 && !topics.includes(chosen) ? topics[0] : lead;
  if (topic !== lead && !consulted.includes(topic)) consulted.push(topic);
  const unavailable = lead === 'nutrition';
  return {
    role: 'assistant',
    ...answerAbout(topic, options.depth, consulted),
    answeredBy: unavailable ? 'general' : lead,
    routed: !chosen,
    ...(consulted.length > 0 && { consulted }),
  };
}

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(structuredClone(value)), LATENCY_MS));
}

function message(fields: Omit<ChatMessage, 'id' | 'createdAt'>): ChatMessage {
  return { ...fields, id: `m${chat.length + 1}`, createdAt: new Date().toISOString() };
}

// Accounts work like the backend's: sign-ups wait for approval, and the made-up demo owner can
// sign in and approve them.
export const DEMO_OWNER = { email: 'demo@patterns.app', password: 'demo-password' };

interface MockAccount extends Account {
  id: string;
  password: string;
  requestedAt: string;
}

let accounts: MockAccount[] = [
  {
    id: 'u1',
    ...DEMO_OWNER,
    status: 'approved',
    isAdmin: true,
    requestedAt: new Date().toISOString(),
  },
];
const sessions = new Map<string, string>(); // token -> account id

function publicAccount({ email, status, isAdmin }: MockAccount): Account {
  return { email, status, isAdmin };
}

function signedIn(account: MockAccount): SignedIn {
  const token = `mock-token-${sessions.size + 1}-${Math.random().toString(36).slice(2)}`;
  sessions.set(token, account.id);
  return { token, account: publicAccount(account) };
}

function currentAccount(): MockAccount {
  const id = sessions.get(getToken() ?? '');
  const account = accounts.find((a) => a.id === id);
  if (!account) throw new ApiError('Sign in to continue.', 'signed_out', 401);
  return account;
}

function adminAccount(): MockAccount {
  const account = currentAccount();
  if (!account.isAdmin) throw new ApiError("Only the app's owner can do this.", 'forbidden', 403);
  return account;
}

/** Waits like a network call, then runs `action`; a thrown error becomes a rejection. */
async function later<T>(action: () => T): Promise<T> {
  await delay(null);
  return structuredClone(action());
}

let google: GoogleStatus = {
  status: 'none',
  syncing: false,
  lastSync: null,
  lastError: null,
  missingScopes: [],
};

function startMockSync() {
  google = { ...google, syncing: true };
  setTimeout(() => {
    google = { ...google, syncing: false, lastSync: new Date().toISOString() };
  }, 3000);
}

// A made-up tracker reading, as the server would add it: never what the app sent.
function withMockReading(log: HealthLog): HealthLog {
  if (log.kind !== 'workout') return log;
  const minutes = log.activeSeconds / 60;
  return {
    ...log,
    measured: {
      status: 'measured',
      steps: Math.round(minutes * 100),
      distanceKm: Math.round(minutes * 0.08 * 100) / 100,
      caloriesKcal: Math.round(minutes * 5),
      averageHeartRate: 110,
      overlaps: [],
    },
  };
}

function withoutReading(log: HealthLog): HealthLog {
  if (log.kind !== 'workout') return log;
  const { measured: _, ...given } = log;
  return given;
}

const logDrafts: { owner: string; requestKey: string; first: string; action: HealthAction }[] = [];
let nextDraft = 0;

function actionAccount() {
  const account = currentAccount();
  if (account.status !== 'approved')
    throw new ApiError('Your account is waiting for approval.', 'not_approved', 403);
  return account;
}

function ownedDraft(id: string, version?: number) {
  const owner = actionAccount().id;
  const record = logDrafts.find((d) => d.owner === owner && d.action.id === id);
  if (!record) throw new ApiError('No such logging draft.', 'not_found', 404);
  if (version !== undefined && record.action.version !== version)
    throw new ApiError('This draft changed. Review it again.', 'stale_action', 409);
  return record;
}

function transition(id: string, version: number, from: string[], to: HealthAction['status']) {
  const record = ownedDraft(id, version);
  if (!from.includes(record.action.status))
    throw new ApiError('This action is no longer available.', 'stale_action', 409);
  record.action = { ...record.action, status: to, updatedAt: new Date().toISOString() };
  return { ...record.action, log: { ...record.action.log } };
}

export const mockClient: ApiClient = {
  getActions: () =>
    later(() => {
      const owner = actionAccount().id;
      return logDrafts
        .filter((d) => d.owner === owner)
        .map((d) => ({ ...d.action, log: { ...d.action.log } }));
    }),
  getAction: (id) =>
    later(() => {
      const { action } = ownedDraft(id);
      return { ...action, log: { ...action.log } };
    }),
  proposeAction: (requestKey, given) =>
    later(() => {
      const log = withMockReading(given);
      validateLog(log);
      const owner = actionAccount().id;
      const existing = logDrafts.find((d) => d.owner === owner && d.requestKey === requestKey);
      if (existing) {
        if (existing.first !== JSON.stringify(withoutReading(log)))
          throw new ApiError('Request key already used.', 'request_conflict', 409);
        return { ...existing.action, log: { ...existing.action.log } };
      }
      if (
        logDrafts.some(
          (d) =>
            d.owner === owner &&
            !['cancelled', 'undone'].includes(d.action.status) &&
            logSignature(d.action.log) === logSignature(log),
        )
      )
        throw new ApiError(
          'This entry already has a draft or a logged record.',
          'duplicate_log',
          409,
        );
      const now = new Date().toISOString();
      const action: HealthAction = {
        id: `draft_${++nextDraft}`,
        version: 1,
        status: 'draft',
        log: { ...log },
        error: null,
        pendingOperation: null,
        createdAt: now,
        updatedAt: now,
      };
      logDrafts.push({ owner, requestKey, first: JSON.stringify(withoutReading(log)), action });
      return { ...action, log: { ...action.log } };
    }),
  reviseAction: (id, version, given: HealthLog) =>
    later(() => {
      const log = withMockReading(given);
      validateLog(log);
      const record = ownedDraft(id, version);
      if (log.kind !== record.action.log.kind)
        throw new ApiError('Start a new draft to change the log type.', 'invalid_log', 422);
      if (
        logDrafts.some(
          (d) =>
            d.owner === record.owner &&
            d.action.id !== id &&
            !['cancelled', 'undone'].includes(d.action.status) &&
            logSignature(d.action.log) === logSignature(log),
        )
      )
        throw new ApiError(
          'This entry already has a draft or a logged record.',
          'duplicate_log',
          409,
        );
      transition(id, version, ['draft', 'failed'], 'draft');
      record.action = { ...record.action, log: { ...log }, version: version + 1, error: null };
      return { ...record.action, log: { ...record.action.log } };
    }),
  cancelAction: (id, version) =>
    later(() => transition(id, version, ['draft', 'failed'], 'cancelled')),
  confirmAction: (id, version) =>
    later(() => transition(id, version, ['draft', 'succeeded'], 'succeeded')),
  undoAction: (id, version) =>
    later(() => transition(id, version, ['succeeded', 'undone'], 'undone')),
  signUp: ({ email, password }) =>
    later(() => {
      const normalized = email.trim().toLowerCase();
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(normalized)) {
        throw new ApiError('Enter a valid email address.', 'invalid_email', 422);
      }
      if (password.length < 10) {
        throw new ApiError('Use a password of at least 10 characters.', 'weak_password', 422);
      }
      if (accounts.some((a) => a.email === normalized)) {
        throw new ApiError('An account with this email already exists.', 'email_taken', 409);
      }
      const account: MockAccount = {
        id: `u${accounts.length + 1}`,
        email: normalized,
        password,
        status: 'pending',
        isAdmin: false,
        requestedAt: new Date().toISOString(),
      };
      accounts = [...accounts, account];
      return signedIn(account);
    }),

  logIn: ({ email, password }) =>
    later(() => {
      const account = accounts.find((a) => a.email === email.trim().toLowerCase());
      if (!account || account.password !== password) {
        throw new ApiError('Wrong email or password.', 'invalid_credentials', 401);
      }
      return signedIn(account);
    }),

  logOut: () =>
    later(() => {
      sessions.delete(getToken() ?? '');
    }),

  getAccount: () => later(() => publicAccount(currentAccount())),

  // Google Health: connecting succeeds at once (no Google page) and a sync takes 3 seconds.
  getGoogleStatus: () => later(() => google),
  connectGoogle: () =>
    later(() => {
      google = { ...google, status: 'active', missingScopes: [] };
      startMockSync();
      return { url: '' }; // nothing to open
    }),
  syncGoogle: () =>
    later(() => {
      if (google.status !== 'active') {
        throw new ApiError('Connect Google Health first.', 'not_connected', 409);
      }
      startMockSync();
      return google;
    }),
  disconnectGoogle: () =>
    later(() => {
      google = { ...google, status: 'none', syncing: false };
      return google;
    }),

  getAccessRequests: () =>
    later(() => {
      adminAccount();
      return accounts
        .filter((a) => a.status === 'pending')
        .map<AccessRequest>(({ id, email, requestedAt }) => ({ id, email, requestedAt }));
    }),

  decideAccessRequest: (id, approve) =>
    later(() => {
      adminAccount();
      const account = accounts.find((a) => a.id === id);
      if (!account) throw new ApiError('No such account.', 'not_found', 404);
      account.status = approve ? 'approved' : 'rejected';
      if (!approve) {
        // Like the backend: a rejected person is signed out everywhere.
        for (const [token, owner] of sessions) if (owner === id) sessions.delete(token);
      }
      return publicAccount(account);
    }),

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

  sendMessage: (text, options) => {
    if (options.expert === 'nutrition') {
      return Promise.reject(new Error('The nutrition expert is not available yet.'));
    }
    const { attachment } = options;
    const added = [message({ role: 'user', text, evidenceIds: [], ...(attachment && { attachment }) })];
    chat = [...chat, ...added];
    const answer = message(reply(text, options));
    chat = [...chat, answer];
    return delay([...added, answer]);
  },

  getReminders: () => delay(reminders),

  setReminderStatus: (id, status) => {
    reminders = reminders.map((r) => (r.id === id ? { ...r, status } : r));
    const updated = reminders.find((r) => r.id === id);
    return updated ? delay(updated) : Promise.reject(new Error('Unknown reminder'));
  },

  getNotificationSettings: () => delay(notificationSettings),

  updateNotificationSettings: (settings) => {
    if (!Number.isInteger(settings.maxPerDay) || settings.maxPerDay < 1 || settings.maxPerDay > 5) {
      return Promise.reject(new Error('maxPerDay must be between 1 and 5'));
    }
    notificationSettings = settings;
    return delay(notificationSettings);
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
