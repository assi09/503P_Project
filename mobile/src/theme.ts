import { createContext, createElement, useContext, type ReactNode } from 'react';
import { useColorScheme } from 'react-native';

// Dark is the primary look; light is derived from the same roles.
const dark = {
  background: '#07080B',
  surface: '#111318',
  surfaceRaised: '#181A21',
  text: '#F3F4F7',
  muted: '#8B91A0',
  faint: '#5A5F6C', // tertiary text, axis labels
  border: '#22252D',
  accent: '#8C9EFF',
  onAccent: '#07080B', // text and icons on accent backgrounds
  accentSoft: '#1B2033',
  danger: '#FF6B6B',
  warning: '#F5B544',
  chart: '#8C9EFF',
  chartHighlight: '#1B2033',
  track: '#1E2028', // empty part of rings and bars
};

const light: typeof dark = {
  background: '#F3F4F7',
  surface: '#FFFFFF',
  surfaceRaised: '#FFFFFF',
  text: '#0B0D12',
  muted: '#5C6270',
  faint: '#9298A6',
  border: '#E3E5EB',
  accent: '#4A5FE8',
  onAccent: '#FFFFFF',
  accentSoft: '#E6E9FD',
  danger: '#D93838',
  warning: '#B26B00',
  chart: '#4A5FE8',
  chartHighlight: '#E6E9FD',
  track: '#E6E8EE',
};

export type Colors = typeof dark;
export type Scheme = 'dark' | 'light';

/** Colors per metric family: a solid color for lines and text, and a gradient pair for rings. */
export const METRIC_COLORS = {
  sleep: { dark: '#9D8CFF', light: '#6A55F0', gradient: ['#6B5BFF', '#C08CFF'] },
  activity: { dark: '#FF9A4D', light: '#E8671A', gradient: ['#FF6A3D', '#FFC24D'] },
  heart: { dark: '#FF5C7A', light: '#E0284D', gradient: ['#FF3D6E', '#FF8FA0'] },
  recovery: { dark: '#3DDC97', light: '#14A86B', gradient: ['#18C487', '#8BEFC2'] },
  temperature: { dark: '#44CFE0', light: '#0E97AB', gradient: ['#1FB6CC', '#8CE9F4'] },
} as const;

export type MetricFamily = keyof typeof METRIC_COLORS;

const FAMILY_BY_METRIC: Record<string, MetricFamily> = {
  sleep_minutes: 'sleep',
  time_in_bed: 'sleep',
  sleep_efficiency: 'sleep',
  sleep_score: 'sleep',
  bedtime_hour: 'sleep',
  deep_sleep_minutes: 'sleep',
  light_sleep_minutes: 'sleep',
  rem_sleep_minutes: 'sleep',
  awake_in_bed_minutes: 'sleep',
  steps: 'activity',
  calories: 'activity',
  distance_km: 'activity',
  active_zone_minutes: 'activity',
  cardio_load: 'activity',
  sedentary_minutes: 'activity',
  lightly_active_minutes: 'activity',
  moderately_active_minutes: 'activity',
  very_active_minutes: 'activity',
  resting_hr: 'heart',
  hrv_ms: 'heart',
  respiratory_rate: 'heart',
  readiness: 'recovery',
  skin_temp_variation_c: 'temperature',
};

export function metricFamily(metric: string): MetricFamily | undefined {
  return FAMILY_BY_METRIC[metric];
}

const ThemeContext = createContext<Scheme>('dark');

/** Dark unless `preference` is 'light', or 'system' and the device is in light mode. */
export function ThemeProvider({
  preference = 'dark',
  children,
}: {
  preference?: Scheme | 'system';
  children: ReactNode;
}) {
  const system = useColorScheme();
  const scheme: Scheme =
    preference === 'system' ? (system === 'light' ? 'light' : 'dark') : preference;
  return createElement(ThemeContext.Provider, { value: scheme }, children);
}

export function useScheme(): Scheme {
  return useContext(ThemeContext);
}

export function useColors(): Colors {
  return useScheme() === 'dark' ? dark : light;
}

/** The metric's solid color in the current scheme, falling back to the accent. */
export function useMetricColor(metric: string): string {
  const scheme = useScheme();
  const colors = useColors();
  const family = metricFamily(metric);
  return family ? METRIC_COLORS[family][scheme] : colors.accent;
}

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 };
export const radius = { sm: 10, md: 14, lg: 20, xl: 28, pill: 999 };

export const fonts = {
  regular: 'Inter_400Regular',
  medium: 'Inter_500Medium',
  semibold: 'Inter_600SemiBold',
  bold: 'Inter_700Bold',
} as const;

/** Text styles; numbers use tabular figures so values do not jump as they change. */
export const type = {
  display: { fontFamily: fonts.bold, fontSize: 34, lineHeight: 40, letterSpacing: -0.6 },
  title: { fontFamily: fonts.bold, fontSize: 24, lineHeight: 30, letterSpacing: -0.4 },
  headline: { fontFamily: fonts.semibold, fontSize: 17, lineHeight: 22, letterSpacing: -0.2 },
  body: { fontFamily: fonts.regular, fontSize: 15, lineHeight: 21 },
  bodyStrong: { fontFamily: fonts.semibold, fontSize: 15, lineHeight: 21 },
  caption: { fontFamily: fonts.medium, fontSize: 13, lineHeight: 17 },
  label: {
    fontFamily: fonts.semibold,
    fontSize: 12,
    lineHeight: 16,
    letterSpacing: 0.6,
    textTransform: 'uppercase' as const,
  },
  number: {
    fontFamily: fonts.bold,
    fontSize: 28,
    lineHeight: 32,
    letterSpacing: -0.5,
    fontVariant: ['tabular-nums' as const],
  },
};
