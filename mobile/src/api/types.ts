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
/** The middle half of the 28 days before a day: what is usual for this person. */
export interface Usual {
  median: number;
  low: number; // 25th percentile
  high: number; // 75th percentile
  days: number;
}

export interface DayMetric {
  metric: string;
  value: number | null;
  usual: Usual | null; // null with fewer than 7 days to compare with
  recent: (number | null)[]; // the 14 days ending with this one, oldest first
}

/** One day's numbers, for Today. */
export interface DaySummary {
  date: ISODate;
  partial: boolean; // today, still filling in
  lowWear: boolean; // under 10 hours of wear: activity totals are not representative
  first: ISODate; // the days there is data for
  last: ISODate;
  metrics: DayMetric[];
  recovery?: Recovery | null; // our own estimate, with at least two of its three inputs
  strain?: Strain | null; // load from time in heart-rate zones (docs/scores.md)
  stress?: Stress | null; // with 4 hours of still, awake wear that day
}

/** Where last night's HRV, resting heart rate and sleep sit among the 28 days before (0–100). */
export interface Recovery {
  score: number;
  parts: Record<string, number>; // each input's share of the 28 days before that it beat
}

/** The day's load from minutes in Fitbit's heart-rate zones, on a 0–21 scale. */
export interface Strain {
  score: number;
  band: 'light' | 'moderate' | 'high' | 'all_out';
  load: number; // weighted zone minutes
  method: 'zones' | 'active_zone_minutes'; // the second is an estimate without zone minutes
}

/** Physical signs of stress against the 28 days before (0–100; 50 is a typical day). */
export interface Stress {
  score: number;
  parts: Record<string, number>; // each input's share of the 28 days before that it beat
}

/** A workout the tracker or an app recorded, with its summary. */
export interface Workout {
  id: string;
  exerciseType: string;
  name: string;
  start: ISODateTime;
  end: ISODateTime;
  activeSeconds: number | null;
  steps?: number | null;
  distanceKm?: number | null;
  caloriesKcal?: number | null;
  averageHeartRate?: number | null;
  activeZoneMinutes?: number | null;
  zoneSeconds?: Partial<Record<'light' | 'moderate' | 'vigorous' | 'peak', number>> | null;
  source?: string | null;
}

export interface DayWorkouts {
  available: boolean; // false without a Google Health connection
  workouts: Workout[];
}

export interface HourlySteps {
  available: boolean;
  steps: (number | null)[]; // 24 local hours
}

export const CHECKIN_TAGS = [
  'hard_training',
  'alcohol',
  'late_meal',
  'stress',
  'travel',
  'feeling_sick',
] as const;

/** The morning "how do you feel?" rating, 1 to 5, with optional tags. */
export interface CheckIn {
  day: ISODate;
  rating: number;
  tags: (typeof CHECKIN_TAGS)[number][];
}

export interface MetricSeries {
  metric: string;
  points: Point[];
  usual: Usual | null; // before the last day
}

export type Attachment = { kind: 'finding'; id: string } | { kind: 'metric'; metric: string };

export interface SendOptions {
  expert: ExpertChoice;
  depth: Depth;
  attachment?: Attachment;
  conversationId?: string; // without one: the latest conversation
  replaces?: string; // editing or retrying: this question and what followed it are replaced
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
  conversationId?: string;
  createdAt: ISODateTime;
}

/** One of the person's chats. Memory is the person's, so every conversation shares it. */
export interface Conversation {
  id: string;
  title: string; // the first question until renamed
  pinned: boolean; // listed first
  messages: number;
  createdAt: ISODateTime;
  updatedAt: ISODateTime;
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
  role: 'member' | 'supervisor'; // a supervisor may create teams (docs/teams.md)
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

/** What joining a team means, shown before the person agrees (docs/teams.md). */
export interface TeamPreview {
  team: string;
  supervisor: string; // their email: who will see the team's figures
  consent: string;
  consentVersion: string;
}

/** A team the person is in. Sharing their own weekly levels is a second, separate consent. */
export interface Membership {
  teamId: string;
  team: string;
  supervisor: string;
  joinedAt: ISODateTime;
  shareLevels: boolean;
  levelsConsent: string;
  levelsConsentVersion: string;
}

/** A supervisor's team: a count of members, never who they are. */
export interface SupervisedTeam {
  id: string;
  name: string;
  inviteCode: string;
  members: number;
  minimumMembers: number; // no team figure is built from fewer
  reportEmail: string | null;
  createdAt: ISODateTime;
}

export interface TeamReportSummary {
  week: Window; // Monday to Sunday
  status: 'ready' | 'withheld'; // withheld: fewer people with data than the minimum
  headline: string;
  membersIncluded: number;
  createdAt: ISODateTime;
}

export interface ReportSection {
  metric: string;
  label?: string | null;
  status?: 'changed' | 'steady' | 'not_enough_data' | null;
  text: string;
  evidenceId: string;
}

export interface NarrativeParagraph {
  text: string;
  kind: 'change' | 'no_change' | 'pattern';
  metric: string;
  evidenceIds: string[];
}

export type TeamLevel = 'below' | 'usual' | 'above';

/** One member who chose to share: their week against their own usual, never against others. */
export interface SharedLevels {
  member: string;
  levels: Record<string, { mean: number | null; level: TeamLevel | null }>;
}

export interface TeamReport extends TeamReportSummary {
  membersTotal: number;
  minimumMembers: number;
  sections: ReportSection[];
  weekdays: ReportSection[];
  narrative: NarrativeParagraph[]; // the model's checked prose; empty when templated
  evidence: Record<string, Evidence>;
  generatedBy: 'template' | 'model';
  levels: SharedLevels[];
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
  decideAccessRequest(id: string, approve: boolean, role?: Account['role']): Promise<Account>; // admins only; role on approval, member by default
  getGoogleStatus(): Promise<GoogleStatus>;
  connectGoogle(capability?: 'food_logging' | 'workout_logging'): Promise<{ url: string }>; // Google's sign-in page; it returns to /settings
  syncGoogle(): Promise<GoogleStatus>;
  disconnectGoogle(): Promise<GoogleStatus>; // the synced days are kept
  getLatestReport(): Promise<Report>;
  getDay(date: ISODate | 'latest'): Promise<DaySummary>;
  getWorkouts(date: ISODate): Promise<DayWorkouts>;
  getHourlySteps(date: ISODate): Promise<HourlySteps>;
  getCheckIn(date: ISODate): Promise<CheckIn | null>;
  saveCheckIn(checkIn: CheckIn): Promise<CheckIn>; // today only
  getMetricSeries(metric: string, options: { end?: ISODate; days: number }): Promise<MetricSeries>;
  getEvidence(id: string): Promise<Evidence>; // any evidence a finding or chat answer cites
  answerQuestion(questionId: string, answer: string): Promise<ContextQuestion>;
  getChat(conversationId?: string): Promise<ChatMessage[]>; // without one: the latest used
  getConversations(): Promise<Conversation[]>; // most recently used first
  createConversation(): Promise<Conversation>;
  updateConversation(id: string, changes: { title?: string; pinned?: boolean }): Promise<Conversation>;
  deleteConversation(id: string): Promise<void>;
  sendMessage(text: string, options: SendOptions): Promise<ChatMessage[]>; // returns the new messages
  getReminders(): Promise<Reminder[]>;
  setReminderStatus(id: string, status: ReminderStatus): Promise<Reminder>;
  getNotificationSettings(): Promise<NotificationSettings>;
  updateNotificationSettings(settings: NotificationSettings): Promise<NotificationSettings>;
  getDataStatus(): Promise<DataStatus>;
  previewTeam(code: string): Promise<TeamPreview>;
  joinTeam(code: string, consentVersion: string): Promise<Membership>;
  getMyTeams(): Promise<Membership[]>;
  shareTeamLevels(teamId: string, share: boolean, consentVersion?: string): Promise<Membership>;
  leaveTeam(teamId: string): Promise<void>;
  getTeams(): Promise<SupervisedTeam[]>; // supervisors only
  createTeam(name: string): Promise<SupervisedTeam>;
  rotateTeamCode(teamId: string): Promise<SupervisedTeam>;
  getTeamReports(teamId: string): Promise<TeamReportSummary[]>; // newest first
  getTeamReport(teamId: string, week: ISODate): Promise<TeamReport>;
  makeTeamReport(teamId: string, week?: ISODate): Promise<TeamReport>; // the last full week
}

export type HealthLog =
  | {
      kind: 'food';
      foodName: string;
      consumedAt: ISODateTime;
      mealType: 'BREAKFAST' | 'LUNCH' | 'DINNER' | 'SNACK';
      energyKcal?: number | null;
      proteinG?: number | null;
      carbohydrateG?: number | null;
      fatG?: number | null;
      provenance: 'user_entered';
    }
  | {
      kind: 'workout';
      exerciseType: string; // any of Google's ExerciseType values, such as TENNIS
      startTime: ISODateTime;
      endTime: ISODateTime;
      activeSeconds: number;
      distanceKm?: number | null;
      provenance: 'user_entered';
      measured?: TrackerReading | null; // added by the server; anything the app sends is replaced
    };

/** What the tracker recorded during a workout, read from Google by the server. */
export interface TrackerReading {
  status: 'measured' | 'no_data' | 'unavailable'; // no_data: not worn, or not synced yet
  steps?: number | null;
  distanceKm?: number | null;
  caloriesKcal?: number | null;
  averageHeartRate?: number | null;
  zoneSeconds?: { light: number; moderate: number; vigorous: number; peak: number } | null;
  activeZoneMinutes?: number | null;
  swimLengths?: number | null;
  overlaps?: {
    exerciseType: string;
    startTime: ISODateTime;
    endTime: ISODateTime;
  }[];
}

export type HealthActionStatus =
  'draft' | 'executing' | 'succeeded' | 'failed' | 'unknown' | 'cancelled' | 'undoing' | 'undone';

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
