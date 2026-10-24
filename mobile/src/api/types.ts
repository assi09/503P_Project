// The contract between the app and the backend API.
// `Evidence` and `Window` mirror the backend models in backend/app/analysis/evidence.py.

export type ISODate = string; // "2026-10-19"
export type ISODateTime = string; // "2026-10-19T08:30:00Z"

export interface Window {
  start: ISODate;
  end: ISODate; // inclusive
}

export interface Evidence {
  id: string;
  tool: string; // "compare_windows", "trend", "correlate", ...
  metrics: string[];
  windows: Window[];
  n: number;
  sufficient: boolean; // false: too few days for the statistics to be trusted
  stats: Record<string, number | string | null | Record<string, unknown> | unknown[]>;
}

export interface Point {
  date: ISODate;
  value: number | null; // null on days without data
}

export type Direction = 'up' | 'down' | 'none';

export interface Finding {
  id: string;
  title: string; // "Sleep efficiency dropped"
  summary: string; // one or two sentences; every number in it comes from `evidenceIds`
  metric: string; // daily table column, e.g. "sleep_efficiency"
  unit: string; // "%", "min", "bpm"
  direction: Direction;
  change: string; // short label shown on the card, e.g. "-6%"
  series: Point[]; // the metric over the report's range, for the chart
  highlight?: Window; // the part of the series the finding is about
  evidenceIds: string[];
}

export interface ContextQuestion {
  id: string;
  prompt: string; // "Something changed around Sep 28. What was it?"
  date: ISODate;
  options: string[]; // ["Travel", "Work schedule", "Training", "Illness", "Nothing"]
  answer: string | null;
}

export interface Report {
  id: string;
  period: Window;
  createdAt: ISODateTime;
  headline: string;
  findings: Finding[];
  questions: ContextQuestion[];
  evidence: Record<string, Evidence>; // by id
}

export type ChatRole = 'user' | 'assistant';

/** The specialists that answer questions; each owns a set of metrics (docs/product.md). */
export type Expert = 'sleep' | 'recovery' | 'activity' | 'nutrition';

/** Who a question goes to: `auto` lets the router pick the expert. */
export type ExpertChoice = 'auto' | Expert;

/** How much work the expert may do: `deep` allows more tool calls and consulting other experts. */
export type Depth = 'quick' | 'deep';

/** Context the user attached to a question. */
export type Attachment = { kind: 'finding'; id: string } | { kind: 'metric'; metric: string };

export interface SendOptions {
  expert: ExpertChoice;
  depth: Depth;
  attachment?: Attachment;
}

export interface ChatMessage {
  id: string;
  role: ChatRole;
  text: string;
  actionIds?: string[]; // owned logging drafts to review; never statistical evidence
  evidenceIds: string[]; // what the assistant's statements are based on
  attachment?: Attachment; // what a user message asked about, if anything
  answeredBy?: Expert | 'general'; // assistant only; absent on refusals
  routed?: boolean; // assistant only: true if the router chose the expert, false if the user did
  consulted?: Expert[]; // other experts the answering expert asked
  refused?: boolean; // the request was out of scope, e.g. medical advice
  createdAt: ISODateTime;
}

export type ReminderStatus = 'proposed' | 'active' | 'declined' | 'muted';

export interface Reminder {
  id: string;
  title: string; // "Wind down"
  message: string; // the notification text
  schedule: string; // human-readable, e.g. "Weeknights at 23:00"
  reason: string; // why the agent proposed it
  findingId: string | null;
  status: ReminderStatus;
}

export interface NotificationSettings {
  quietHours: { start: string; end: string } | null; // "22:00".."07:00", local time; null = off
  maxPerDay: number;
}

export interface MetricCoverage {
  metric: string;
  label: string;
  fractionPresent: number; // 0..1 over the report period
}

export interface DataStatus {
  source: 'takeout' | 'google_health' | 'none';
  lastSync: ISODateTime | null;
  range: Window | null;
  coverage: MetricCoverage[];
  lowWearDays: ISODate[];
}

export type AccountStatus = 'pending' | 'approved' | 'rejected';

export interface Account {
  email: string;
  status: AccountStatus; // a sign-up waits for the owner's approval
  isAdmin: boolean; // may approve sign-ups
}

export interface Credentials {
  email: string;
  password: string;
}

export interface SignedIn {
  token: string; // sent as `Authorization: Bearer <token>`
  account: Account;
}

export interface AccessRequest {
  id: string;
  email: string;
  requestedAt: ISODateTime;
}

export interface GoogleStatus {
  status: 'none' | 'active' | 'reconnect_needed'; // reconnect: Google's sign-in expired
  syncing: boolean;
  lastSync: ISODateTime | null; // the last successful sync
  lastError: string | null; // why the latest sync failed, safe to show
  missingScopes: string[]; // permissions the person unticked on Google's page
}

export interface ApiClient {
  getActions(): Promise<HealthAction[]>;
  getAction(id: string): Promise<HealthAction>;
  proposeAction(requestKey: string, log: HealthLog): Promise<HealthAction>;
  reviseAction(id: string, version: number, log: HealthLog): Promise<HealthAction>;
  cancelAction(id: string, version: number): Promise<HealthAction>;
  confirmAction(id: string, version: number): Promise<HealthAction>;
  undoAction(id: string, version: number): Promise<HealthAction>;
  signUp(credentials: Credentials): Promise<SignedIn>;
  logIn(credentials: Credentials): Promise<SignedIn>;
  logOut(): Promise<void>;
  getAccount(): Promise<Account>;
  getAccessRequests(): Promise<AccessRequest[]>; // admins only
  decideAccessRequest(id: string, approve: boolean): Promise<Account>; // admins only
  getGoogleStatus(): Promise<GoogleStatus>;
  connectGoogle(capability?: 'food_logging' | 'workout_logging'): Promise<{ url: string }>; // Google's sign-in page; it returns to /data
  syncGoogle(): Promise<GoogleStatus>;
  disconnectGoogle(): Promise<GoogleStatus>; // the synced days are kept
  getLatestReport(): Promise<Report>;
  getEvidence(id: string): Promise<Evidence>; // any evidence a finding or chat answer cites
  answerQuestion(questionId: string, answer: string): Promise<ContextQuestion>;
  getChat(): Promise<ChatMessage[]>;
  sendMessage(text: string, options: SendOptions): Promise<ChatMessage[]>; // returns the new messages
  getReminders(): Promise<Reminder[]>;
  setReminderStatus(id: string, status: ReminderStatus): Promise<Reminder>;
  getNotificationSettings(): Promise<NotificationSettings>;
  updateNotificationSettings(settings: NotificationSettings): Promise<NotificationSettings>;
  getDataStatus(): Promise<DataStatus>;
}

export type HealthLog = {
  kind: 'food';
  foodName: string;
  consumedAt: ISODateTime;
  mealType: 'BREAKFAST' | 'LUNCH' | 'DINNER' | 'SNACK';
  energyKcal?: number | null;
  proteinG?: number | null;
  carbohydrateG?: number | null;
  fatG?: number | null;
  provenance: 'user_entered';
} | {
  kind: 'workout';
  exerciseType: 'RUNNING' | 'WALKING' | 'BIKING' | 'AEROBIC_WORKOUT';
  startTime: ISODateTime;
  endTime: ISODateTime;
  activeSeconds: number;
  distanceKm?: number | null;
  provenance: 'user_entered';
};

export type HealthActionStatus = 'draft' | 'executing' | 'succeeded' | 'failed' | 'unknown'
  | 'cancelled' | 'undoing' | 'undone';

export interface HealthAction {
  id: string;
  version: number;
  status: HealthActionStatus;
  log: HealthLog;
  error: string | null;
  pendingOperation: 'create' | 'delete' | null;
  createdAt: ISODateTime;
  updatedAt: ISODateTime;
}
