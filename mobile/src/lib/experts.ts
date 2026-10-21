// The experts a question can go to, as the app presents them. Ownership follows docs/product.md.
import type { Ionicons } from '@expo/vector-icons';
import type { ComponentProps } from 'react';

import type { Expert, ExpertChoice } from '@/api/types';
import { metricFamily, type MetricFamily } from '@/theme';

type IconName = ComponentProps<typeof Ionicons>['name'];

export interface ExpertInfo {
  id: ExpertChoice;
  label: string;
  icon: IconName;
  family: MetricFamily | null; // color family; null uses the app accent
  description: string;
  available: boolean;
  suggestions: string[];
}

export const EXPERTS: readonly ExpertInfo[] = [
  {
    id: 'auto',
    label: 'Auto',
    icon: 'sparkles',
    family: null,
    description: 'Picks the right expert for each question',
    available: true,
    suggestions: [
      'What changed most this month?',
      'Why is my sleep worse lately?',
      'Did my late nights affect my recovery?',
    ],
  },
  {
    id: 'sleep',
    label: 'Sleep',
    icon: 'moon',
    family: 'sleep',
    description: 'Duration, stages, efficiency, bedtime',
    available: true,
    suggestions: [
      'Why is my sleep worse lately?',
      'How consistent is my bedtime?',
      'How much deep sleep do I usually get?',
    ],
  },
  {
    id: 'recovery',
    label: 'Recovery',
    icon: 'battery-charging',
    family: 'recovery',
    description: 'Recovery score, HRV, resting heart rate',
    available: true,
    suggestions: [
      'Why was my recovery low this week?',
      'How is my HRV trending?',
      'Did my late nights affect my recovery?',
    ],
  },
  {
    id: 'activity',
    label: 'Activity',
    icon: 'flame',
    family: 'activity',
    description: 'Steps, zone minutes, training load',
    available: true,
    suggestions: [
      'How are my steps trending?',
      'Am I training more than usual?',
      'Which days am I least active?',
    ],
  },
  {
    id: 'nutrition',
    label: 'Nutrition',
    icon: 'nutrition',
    family: 'nutrition',
    description: 'Coming soon: needs nutrition data',
    available: false,
    suggestions: [],
  },
];

export function expertInfo(id: ExpertChoice | 'general'): ExpertInfo {
  return EXPERTS.find((expert) => expert.id === id) ?? EXPERTS[0];
}

/** The expert that owns a metric, e.g. `hrv_ms` -> recovery. */
export function expertForMetric(metric: string): Expert | undefined {
  switch (metricFamily(metric)) {
    case 'sleep':
      return 'sleep';
    case 'activity':
      return 'activity';
    case 'heart':
    case 'recovery':
    case 'temperature':
      return 'recovery';
    case 'nutrition':
      return 'nutrition';
    default:
      return undefined;
  }
}
