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

export interface ChatMessage {
  id: string;
  role: ChatRole;
  text: string;
  evidenceIds: string[]; // what the assistant's statements are based on
  findingId?: string; // the finding a user message asked about, if any
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

export interface ApiClient {
  getLatestReport(): Promise<Report>;
  getEvidence(id: string): Promise<Evidence>; // any evidence a finding or chat answer cites
  answerQuestion(questionId: string, answer: string): Promise<ContextQuestion>;
  getChat(): Promise<ChatMessage[]>;
  sendMessage(text: string, findingId?: string): Promise<ChatMessage[]>; // returns the new messages
  getReminders(): Promise<Reminder[]>;
  setReminderStatus(id: string, status: ReminderStatus): Promise<Reminder>;
  getDataStatus(): Promise<DataStatus>;
}
